(function mindMapModelModule(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MindMapModel = api;
})(typeof window !== "undefined" ? window : globalThis, function buildMindMapModel() {
  "use strict";

  // Branch palette — distinct hues for the depth-1 branches of the radial map.
  const BRANCH_COLORS = [
    "#3dab9c", "#5b8dee", "#e8a93d", "#e85d5d", "#9b5de5",
    "#3dab6e", "#e85db8", "#5dd5e8", "#e8775d", "#b8e85d",
  ];
  const ROOT_COLOR = "#475569";        // dark slate — never collides with a branch hue, reads on the light canvas
  const GROUP_COLORS = BRANCH_COLORS;  // back-compat export
  const FALLBACK_RELATION = "related to";
  const MAX_NODES = 20;
  const MIN_RADIUS = 10;
  const RADIUS_RANGE = 18;

  /* ── primitives ─────────────────────────────────────────────────────────── */

  function slugify(value) {
    return String(value == null ? "" : value)
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function clampImportance(value) {
    let v = Number(value);
    if (!Number.isFinite(v)) v = 0.5;
    return Math.min(1, Math.max(0, v));
  }

  const SLUG_LABEL_RE = /^[a-z0-9]+(?:[_-][a-z0-9]+)+$/;
  function prettyLabel(value) {
    const label = String(value == null ? "" : value).trim();
    if (SLUG_LABEL_RE.test(label)) {
      return label.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    }
    if (label.length >= 4 && /^[a-z]+$/.test(label)) {
      return label[0].toUpperCase() + label.slice(1);
    }
    return label;
  }

  function radiusFor(importance) {
    return MIN_RADIUS + clampImportance(importance) * RADIUS_RANGE;
  }

  // Deterministic colour for a group name — used for the legend, not the tree.
  function groupColor(group) {
    const key = String(group || "default");
    let hash = 0;
    for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) & 0xffffffff;
    return BRANCH_COLORS[Math.abs(hash) % BRANCH_COLORS.length];
  }

  function pickHub(nodes) {
    return nodes.reduce((best, n) => (n.importance > best.importance ? n : best), nodes[0]);
  }

  /* ── graph normalisation (mirror of app/m4/synthesis.py) ─────────────────── */

  function normalizeNodes(rawNodes, warnings) {
    const nodes = [];
    const keyToId = new Map();       // id | raw id | label (slugified) -> canonical id
    const parentHints = new Map();   // canonical id -> slug(raw parent)
    const usedIds = new Set();

    for (const item of rawNodes) {
      const obj = item && typeof item === "object" ? item : { label: item };
      let label = String(obj.label != null ? obj.label : obj.id != null ? obj.id : "").trim();
      const rawId = String(obj.id != null ? obj.id : "").trim();
      if (!label && !rawId) {
        warnings.push("dropped a node with no id or label");
        continue;
      }
      label = prettyLabel(label || rawId);

      let id = slugify(rawId) || slugify(label) || "node";
      while (usedIds.has(id)) id = id + "-" + usedIds.size;
      usedIds.add(id);

      nodes.push({
        id,
        label,
        group: String(obj.group != null ? obj.group : "").trim() || "default",
        importance: clampImportance(obj.importance),
        parent: null,
      });
      for (const key of [id, slugify(rawId), slugify(label)]) {
        if (key && !keyToId.has(key)) keyToId.set(key, id);
      }
      const parentSlug = slugify(obj.parent);
      if (parentSlug) parentHints.set(id, parentSlug);

      if (nodes.length >= MAX_NODES) {
        warnings.push("node list truncated to " + MAX_NODES);
        break;
      }
    }

    const live = new Set(nodes.map((n) => n.id));
    for (const [k, v] of Array.from(keyToId)) if (!live.has(v)) keyToId.delete(k);
    for (const k of Array.from(parentHints.keys())) if (!live.has(k)) parentHints.delete(k);
    return { nodes, keyToId, parentHints };
  }

  function normalizeEdges(rawEdges, keyToId, liveIds, warnings) {
    const seen = new Set();
    const edges = [];
    for (const item of rawEdges) {
      if (!item || typeof item !== "object") continue;
      const s = keyToId.get(slugify(item.source));
      const t = keyToId.get(slugify(item.target));
      if (!s || !t || s === t || !liveIds.has(s) || !liveIds.has(t)) {
        warnings.push("dropped an edge with an unknown or self endpoint");
        continue;
      }
      const key = s < t ? s + "|" + t : t + "|" + s;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({ source: s, target: t, relation: String(item.relation != null ? item.relation : "").trim() });
    }
    return edges;
  }

  function connectGraph(nodes, edges, warnings) {
    if (nodes.length < 2) return edges;
    const hub = pickHub(nodes);
    if (edges.length === 0) {
      warnings.push("model returned no relations — building a star from the main concept");
      return nodes
        .filter((n) => n.id !== hub.id)
        .map((n) => ({ source: hub.id, target: n.id, relation: FALLBACK_RELATION }));
    }
    const touched = new Set();
    for (const e of edges) { touched.add(e.source); touched.add(e.target); }
    const orphans = nodes.filter((n) => !touched.has(n.id) && n.id !== hub.id);
    if (orphans.length) {
      warnings.push(orphans.length + " unlinked concept(s) attached to the main node");
      for (const n of orphans) edges.push({ source: hub.id, target: n.id, relation: FALLBACK_RELATION });
    }
    return edges;
  }

  function resolveRef(refSlug, liveIds, keyToId) {
    if (!refSlug) return null;
    if (liveIds.has(refSlug)) return refSlug;
    return keyToId.get(refSlug) || null;
  }

  function reaches(start, parents, rootId) {
    const seen = new Set();
    let cur = start;
    while (parents.has(cur)) {
      if (seen.has(cur)) return false;
      seen.add(cur);
      cur = parents.get(cur);
    }
    return cur === rootId;
  }

  // Mirror of synthesis.py::_derive_tree — hint → edge-BFS → straight-to-root.
  function deriveTree(nodes, edges, parentHints, rootHint, keyToId) {
    if (!nodes.length) return { rootId: null, parents: new Map() };
    const ids = nodes.map((n) => n.id);
    const live = new Set(ids);

    let rootId = resolveRef(rootHint, live, keyToId);
    if (!rootId) rootId = pickHub(nodes).id;

    const parents = new Map();
    for (const [child, hint] of parentHints) {
      const p = resolveRef(hint, live, keyToId);
      if (p && p !== child) parents.set(child, p);
    }
    for (const id of ids) {
      if (id === rootId || (parents.has(id) && !reaches(id, parents, rootId))) parents.delete(id);
    }

    const adj = new Map(ids.map((i) => [i, new Set()]));
    for (const e of edges) { adj.get(e.source).add(e.target); adj.get(e.target).add(e.source); }
    const queue = [rootId];
    const visited = new Set([rootId]);
    while (queue.length) {
      const cur = queue.shift();
      for (const nb of adj.get(cur) || []) {
        if (!visited.has(nb)) {
          visited.add(nb);
          if (!parents.has(nb)) parents.set(nb, cur);
          queue.push(nb);
        }
      }
    }
    for (const id of ids) {
      if (id !== rootId && !reaches(id, parents, rootId)) parents.set(id, rootId);
    }
    return { rootId, parents };
  }

  /**
   * Turn whatever the model / API returned into a render-safe rooted radial
   * tree. Mirrors the server pipeline so a stale flat `{nodes,edges}`, a bare
   * `{}`, or the current `{root,nodes,edges}` all normalise identically.
   *
   * Result: `{ root, nodes:[{id,label,group,importance,parent}], edges:[cross-links],
   *            warnings, ok }`. `ok` is false only when there is nothing to draw.
   */
  function normalizeGraph(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const warnings = [];
    const { nodes, keyToId, parentHints } = normalizeNodes(
      Array.isArray(src.nodes) ? src.nodes : [], warnings
    );
    const liveIds = new Set(nodes.map((n) => n.id));
    let edges = normalizeEdges(Array.isArray(src.edges) ? src.edges : [], keyToId, liveIds, warnings);
    edges = connectGraph(nodes, edges, warnings);

    const { rootId, parents } = deriveTree(nodes, edges, parentHints, slugify(src.root), keyToId);
    for (const n of nodes) n.parent = parents.get(n.id) || null;

    const backbone = new Set();
    for (const [c, p] of parents) backbone.add(c < p ? c + "|" + p : p + "|" + c);
    const crossLinks = edges.filter((e) => {
      const key = e.source < e.target ? e.source + "|" + e.target : e.target + "|" + e.source;
      return !backbone.has(key) && e.relation !== FALLBACK_RELATION;
    });

    return { root: rootId, nodes, edges: crossLinks, warnings, ok: nodes.length > 0 };
  }

  /* ── hierarchy + layout helpers ─────────────────────────────────────────── */

  /**
   * Nested `{id,label,group,importance,depth,children:[]}` from a normalised
   * `{root,nodes,edges}`. Falls back to a parent-less node or the most
   * important node when `root` is missing; guarantees a cycle-free tree.
   */
  function buildHierarchy(graph) {
    const nodes = (graph && Array.isArray(graph.nodes) ? graph.nodes : []);
    if (!nodes.length) return null;
    const ids = new Set(nodes.map((n) => n.id));

    let rootId = graph && graph.root && ids.has(graph.root) ? graph.root : null;
    if (!rootId) {
      const orphan = nodes.find((n) => !n.parent || !ids.has(n.parent));
      rootId = orphan ? orphan.id : pickHub(nodes).id;
    }

    const parents = new Map();
    for (const n of nodes) {
      if (n.id === rootId) continue;
      parents.set(n.id, n.parent && ids.has(n.parent) && n.parent !== n.id ? n.parent : rootId);
    }
    for (const id of ids) {
      if (id !== rootId && !reaches(id, parents, rootId)) parents.set(id, rootId);
    }

    const wrap = new Map(
      nodes.map((n) => [n.id, {
        id: n.id, label: n.label, group: n.group,
        importance: clampImportance(n.importance), children: [],
      }])
    );
    for (const [child, parent] of parents) wrap.get(parent).children.push(wrap.get(child));

    const rootNode = wrap.get(rootId);
    (function walk(node, depth) {
      node.depth = depth;
      node.children.sort(
        (a, b) => b.importance - a.importance || String(a.label).localeCompare(String(b.label))
      );
      node.children.forEach((c) => walk(c, depth + 1));
    })(rootNode, 0);
    return rootNode;
  }

  /** `Map<id,colour>` — one palette colour per depth-1 branch, inherited by descendants. */
  function assignBranchColors(rootNode, palette) {
    const colors = new Map();
    if (!rootNode) return colors;
    const pal = Array.isArray(palette) && palette.length ? palette : BRANCH_COLORS;
    colors.set(rootNode.id, ROOT_COLOR);
    (rootNode.children || []).forEach((branch, i) => {
      const c = pal[i % pal.length];
      (function paint(node) {
        colors.set(node.id, c);
        (node.children || []).forEach(paint);
      })(branch);
    });
    return colors;
  }

  /**
   * Zoom transform `{x,y,k}` that frames `bbox` inside `viewport` with padding.
   * Never returns a non-finite or non-positive `k`.
   */
  function computeFitTransform(bbox, viewport, padding) {
    const pad = Number.isFinite(padding) ? padding : 28;
    const bw = Math.max(bbox && bbox.width || 0, 1);
    const bh = Math.max(bbox && bbox.height || 0, 1);
    const vw = Math.max(viewport && viewport.width || 0, 1);
    const vh = Math.max(viewport && viewport.height || 0, 1);

    let k = Math.min((vw - pad * 2) / bw, (vh - pad * 2) / bh);
    if (!Number.isFinite(k) || k <= 0) k = 1;
    k = Math.min(Math.max(k, 0.4), 1.6);

    const cx = (bbox && bbox.x || 0) + bw / 2;
    const cy = (bbox && bbox.y || 0) + bh / 2;
    return { x: vw / 2 - k * cx, y: vh / 2 - k * cy, k };
  }

  /**
   * A never-zero {width,height} for the mind-map viewport. The synthesis panel
   * renders while its sub-tab is display:none (client size 0); this falls back
   * cleanly and lets the renderer re-fit once the panel is shown.
   */
  function resolveViewport(container, fallback) {
    const fb = fallback || {};
    const fw = fb.width > 0 ? fb.width : 800;
    const fh = fb.height > 0 ? fb.height : 500;
    if (!container || typeof container.getBoundingClientRect !== "function") {
      return { width: fw, height: fh };
    }
    const rect = container.getBoundingClientRect() || {};
    const width = Math.round(container.clientWidth || rect.width || 0);
    const height = Math.round(container.clientHeight || rect.height || 0);
    return { width: width > 0 ? width : fw, height: height > 0 ? height : fh };
  }

  return {
    slugify,
    groupColor,
    clampImportance,
    radiusFor,
    normalizeGraph,
    buildHierarchy,
    assignBranchColors,
    computeFitTransform,
    resolveViewport,
    BRANCH_COLORS,
    GROUP_COLORS,
    ROOT_COLOR,
    FALLBACK_RELATION,
  };
});
