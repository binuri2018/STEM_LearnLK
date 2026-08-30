"""Generate flashcards, mind maps, or structured notes through the selected LLM.

Each mode uses a tool spec with a JSON-schema fallback. The returned dictionary
matches the existing frontend renderers.
"""
from __future__ import annotations

import re
from collections import deque
from typing import Any

from backend.components.knowledge_maps import llm_client
from backend.components.knowledge_maps.prompts import SYNTHESIS_TOOLS, synthesis_user_message
from backend.components.knowledge_maps.schemas import MindMapResponse

_MAX_MINDMAP_NODES = 20
_FALLBACK_RELATION = "related to"


def _slug(value: Any) -> str:
    """Lowercase ``a-z0-9`` slug used to match ids and labels loosely."""
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _clamp_importance(value: Any) -> float:
    try:
        importance = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(1.0, max(0.0, importance))


_SLUG_LABEL_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)+$")


def _pretty_label(value: Any) -> str:
    """Humanise a label the model gave as a raw slug (``light_dependent``).

    Multi-token slugs become Title Case; a single all-lowercase word of 4+
    letters just gets its first letter capitalised (short tokens like ``atp``
    are left alone in case they are acronyms).
    """
    label = str(value or "").strip()
    if _SLUG_LABEL_RE.match(label):
        return re.sub(r"[_-]+", " ", label).title()
    if len(label) >= 4 and label.isalpha() and label.islower():
        return label[:1].upper() + label[1:]
    return label


def _normalize_nodes(
    raw_nodes: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """Return clean node dicts, a slug -> canonical-id lookup, and parent hints.

    The lookup keys the canonical id, the model's raw id, and the label so a
    later reference to any of those resolves to the right node. ``parent_hints``
    maps a canonical id to the *slug* of whatever the model named as its parent
    (resolved to a real id later, in :func:`_derive_tree`).
    """
    nodes: list[dict[str, Any]] = []
    key_to_id: dict[str, str] = {}
    parent_hints: dict[str, str] = {}
    used_ids: set[str] = set()

    for item in raw_nodes:
        if not isinstance(item, dict):
            if item in (None, ""):
                continue
            item = {"label": str(item)}

        label = str(item.get("label") or item.get("id") or "").strip()
        raw_id = str(item.get("id") or "").strip()
        if not label and not raw_id:
            continue
        label = _pretty_label(label or raw_id)

        canonical = _slug(raw_id) or _slug(label) or "node"
        while canonical in used_ids:
            canonical = f"{canonical}-{len(used_ids)}"
        used_ids.add(canonical)

        nodes.append(
            {
                "id": canonical,
                "label": label,
                "group": str(item.get("group") or "").strip() or "default",
                "importance": _clamp_importance(item.get("importance", 0.5)),
            }
        )
        for key in (canonical, _slug(raw_id), _slug(label)):
            if key:
                key_to_id.setdefault(key, canonical)
        parent_slug = _slug(item.get("parent"))
        if parent_slug:
            parent_hints[canonical] = parent_slug

        if len(nodes) >= _MAX_MINDMAP_NODES:
            break

    live_ids = {node["id"] for node in nodes}
    key_to_id = {key: nid for key, nid in key_to_id.items() if nid in live_ids}
    parent_hints = {nid: p for nid, p in parent_hints.items() if nid in live_ids}
    return nodes, key_to_id, parent_hints


def _normalize_edges(raw_edges: list[Any], key_to_id: dict[str, str]) -> list[dict[str, Any]]:
    """Resolve endpoints via the slug lookup; drop self-loops and duplicates."""
    seen_pairs: set[tuple[str, str]] = set()
    edges: list[dict[str, Any]] = []
    for item in raw_edges:
        if not isinstance(item, dict):
            continue
        source = key_to_id.get(_slug(item.get("source")))
        target = key_to_id.get(_slug(item.get("target")))
        if not source or not target or source == target:
            continue
        pair = tuple(sorted((source, target)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": str(item.get("relation") or "").strip(),
            }
        )
    return edges


def _connect_graph(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Guarantee a connected graph: star layout when no edges, else attach orphans."""
    if len(nodes) < 2:
        return edges

    hub = max(nodes, key=lambda n: n["importance"])
    if not edges:
        return [
            {"source": hub["id"], "target": node["id"], "relation": _FALLBACK_RELATION}
            for node in nodes
            if node["id"] != hub["id"]
        ]

    touched = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    edges.extend(
        {"source": hub["id"], "target": node["id"], "relation": _FALLBACK_RELATION}
        for node in nodes
        if node["id"] not in touched and node["id"] != hub["id"]
    )
    return edges


def _resolve_ref(ref_slug: str, live_ids: set[str], key_to_id: dict[str, str]) -> str | None:
    if not ref_slug:
        return None
    if ref_slug in live_ids:
        return ref_slug
    return key_to_id.get(ref_slug)


def _reaches(start: str, parents: dict[str, str], root_id: str) -> bool:
    """Walk parent pointers from ``start``; True iff the chain ends at the root."""
    seen: set[str] = set()
    current = start
    while current in parents:
        if current in seen:
            return False  # cycle
        seen.add(current)
        current = parents[current]
    return current == root_id


def _adjacency(ids: list[str], edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {nid: set() for nid in ids}
    for edge in edges:
        adj[edge["source"]].add(edge["target"])
        adj[edge["target"]].add(edge["source"])
    return adj


def _derive_tree(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    parent_hints: dict[str, str],
    root_hint: str,
    key_to_id: dict[str, str],
) -> tuple[str | None, dict[str, str]]:
    """Turn the connected graph into a rooted tree ``{child_id: parent_id}``.

    Priority: a valid ``root``/``parent`` hint from the model, then a
    breadth-first walk over the (already-connected) edge graph, then a direct
    link to the root for anything still unreached. Cycles from bad hints are
    broken.
    """
    if not nodes:
        return None, {}

    ids = [node["id"] for node in nodes]
    live_ids = set(ids)

    root_id = _resolve_ref(root_hint, live_ids, key_to_id) or max(
        nodes, key=lambda n: n["importance"]
    )["id"]

    # 1. seed from the model's parent hints
    parents: dict[str, str] = {}
    for child, hint in parent_hints.items():
        parent = _resolve_ref(hint, live_ids, key_to_id)
        if parent and parent != child:
            parents[child] = parent
    # 2. drop hint chains that loop or never reach the root
    for child in ids:
        if child == root_id or (child in parents and not _reaches(child, parents, root_id)):
            parents.pop(child, None)

    # 3. fill gaps by walking out from the root over the edge graph
    adjacency = _adjacency(ids, edges)
    queue, visited = deque([root_id]), {root_id}
    while queue:
        current = queue.popleft()
        for neighbour in adjacency.get(current, ()):
            if neighbour not in visited:
                visited.add(neighbour)
                parents.setdefault(neighbour, current)
                queue.append(neighbour)

    # 4. anything still unrooted (disconnected / surviving bad chain) → root
    for child in ids:
        if child != root_id and not _reaches(child, parents, root_id):
            parents[child] = root_id

    return root_id, parents


def _sanitize_mindmap(result: dict[str, Any]) -> dict[str, Any]:
    """Flat graph normalisation (no hierarchy). Stable for older callers/tests.

    Unique clamped nodes, label-recovered + de-duplicated edges, and a
    connectivity fallback so the graph is never a cloud of disconnected dots.
    """
    raw_nodes = result.get("nodes")
    raw_edges = result.get("edges")
    nodes, key_to_id, _ = _normalize_nodes(raw_nodes if isinstance(raw_nodes, list) else [])
    edges = _normalize_edges(raw_edges if isinstance(raw_edges, list) else [], key_to_id)
    edges = _connect_graph(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def normalize_mindmap(result: dict[str, Any]) -> dict[str, Any]:
    """Repair a raw mind map into a render-safe rooted radial tree.

    Builds on :func:`_sanitize_mindmap` (clamped unique nodes, recovered edges,
    connectivity fallback) and then:

    * derives a single ``root`` and a ``parent`` for every other node
      (:func:`_derive_tree`) — from the model's hints where valid, otherwise
      from the edge graph, otherwise straight to the root;
    * keeps ``edges`` for cross-links only — any edge that merely restates a
      parent↔child backbone link is dropped.

    The result always round-trips through :class:`MindMapResponse`.
    """
    raw_nodes = result.get("nodes")
    raw_edges = result.get("edges")
    nodes, key_to_id, parent_hints = _normalize_nodes(
        raw_nodes if isinstance(raw_nodes, list) else []
    )
    edges = _normalize_edges(raw_edges if isinstance(raw_edges, list) else [], key_to_id)
    edges = _connect_graph(nodes, edges)

    root_id, parents = _derive_tree(
        nodes, edges, parent_hints, _slug(result.get("root")), key_to_id
    )
    for node in nodes:
        node["parent"] = parents.get(node["id"])

    backbone = {tuple(sorted((child, parent))) for child, parent in parents.items()}
    cross_links = [
        edge
        for edge in edges
        # keep only genuine relationships: not the parent backbone, and not one
        # of the synthetic links _connect_graph adds purely for connectivity.
        if tuple(sorted((edge["source"], edge["target"]))) not in backbone
        and edge["relation"] != _FALLBACK_RELATION
    ]

    return {"root": root_id, "nodes": nodes, "edges": cross_links}


def synthesize(text: str, mode: str, language: str = "auto") -> dict[str, Any]:
    """Run a synthesis call. Returns the tool's parsed args dict.

    - mode='flashcards' → {"flashcards": [{"front", "back"}, ...]}
    - mode='mindmap'    → {"root", "nodes": [{..., "parent"}], "edges": [cross-links]}
    - mode='notes'      → {"sections": [{"heading", "bullets", "key_terms"}, ...]}

    Raises:
        ValueError: unknown mode
        RuntimeError: provider not configured / structured output missing
    """
    if mode not in SYNTHESIS_TOOLS:
        raise ValueError(f"Unknown synthesis mode: {mode!r}")
    system, tool = SYNTHESIS_TOOLS[mode]
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": synthesis_user_message(text, language)},
    ]
    args = llm_client.chat_with_tools(
        messages=messages,
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
        temperature=0.2,
    )
    if mode == "mindmap":
        return MindMapResponse(**normalize_mindmap(args)).model_dump()
    return args
