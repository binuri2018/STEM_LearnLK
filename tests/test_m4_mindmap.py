"""Mind-map normalisation, hierarchy, and endpoint-contract tests for Member 4.

Run:  .venv/bin/python -m unittest tests.test_m4_mindmap -v
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.components.knowledge_maps.prompts import MINDMAP_TOOL
from backend.components.knowledge_maps.schemas import MindMapResponse
from backend.components.knowledge_maps.synthesis import _derive_tree, _sanitize_mindmap, normalize_mindmap


def _parents(out: dict) -> dict[str, str | None]:
    return {node["id"]: node["parent"] for node in out["nodes"]}


class NormalizeMindmapNodeTests(unittest.TestCase):
    def test_importance_is_clamped_and_defaults_are_filled(self) -> None:
        raw = {
            "root": "a",
            "nodes": [
                {"id": "a", "label": "A", "importance": 5},
                {"id": "b", "label": "B", "importance": -3, "parent": "a"},
                {"id": "c", "label": "C", "importance": "not-a-number", "parent": "a"},
                {"id": "d", "label": "D", "parent": "a"},
            ],
            "edges": [],
        }

        out = normalize_mindmap(raw)
        importance = {n["id"]: n["importance"] for n in out["nodes"]}

        self.assertEqual(importance, {"a": 1.0, "b": 0.0, "c": 0.5, "d": 0.5})
        self.assertTrue(all(n["group"] for n in out["nodes"]))

    def test_duplicate_ids_are_disambiguated(self) -> None:
        raw = {"nodes": [{"id": "x", "label": "One"}, {"id": "x", "label": "Two"}], "edges": []}

        ids = [n["id"] for n in normalize_mindmap(raw)["nodes"]]

        self.assertEqual(len(ids), len(set(ids)))

    def test_bare_string_and_empty_nodes_are_tolerated(self) -> None:
        raw = {"nodes": ["Cell", "Nucleus", {"label": ""}, None], "edges": []}

        labels = [n["label"] for n in normalize_mindmap(raw)["nodes"]]

        self.assertEqual(labels, ["Cell", "Nucleus"])

    def test_slug_style_labels_are_humanised_without_touching_real_labels(self) -> None:
        raw = {
            "root": "photosynthesis",
            "nodes": [
                {"id": "photosynthesis", "label": "Photosynthesis"},
                {"id": "ldr", "label": "light_dependent", "parent": "photosynthesis"},
                {"id": "atp", "label": "atp-nadph", "parent": "photosynthesis"},
                {"id": "abbr", "label": "ATP", "parent": "photosynthesis"},
                {"id": "two", "label": "Calvin Cycle", "parent": "photosynthesis"},
                {"id": "one", "label": "chloroplasts", "parent": "photosynthesis"},
                {"id": "co2", "label": "co2", "parent": "photosynthesis"},
            ],
            "edges": [],
        }

        labels = {n["id"]: n["label"] for n in normalize_mindmap(raw)["nodes"]}

        self.assertEqual(labels["ldr"], "Light Dependent")
        self.assertEqual(labels["atp"], "Atp Nadph")
        self.assertEqual(labels["abbr"], "ATP")            # already mixed-case, untouched
        self.assertEqual(labels["two"], "Calvin Cycle")    # has a space, untouched
        self.assertEqual(labels["one"], "Chloroplasts")    # single lowercase word ≥ 4
        self.assertEqual(labels["co2"], "co2")             # short + has a digit, untouched

    def test_node_count_is_capped(self) -> None:
        raw = {"nodes": [{"id": f"n{i}", "label": f"N{i}"} for i in range(40)], "edges": []}

        self.assertLessEqual(len(normalize_mindmap(raw)["nodes"]), 20)

    def test_every_node_carries_a_parent_key_and_only_the_root_is_none(self) -> None:
        raw = {
            "root": "core",
            "nodes": [
                {"id": "core", "label": "Core", "importance": 1.0},
                {"id": "x", "label": "X", "parent": "core"},
                {"id": "y", "label": "Y", "parent": "x"},
            ],
            "edges": [],
        }

        out = normalize_mindmap(raw)

        self.assertEqual(out["root"], "core")
        parents = _parents(out)
        self.assertIsNone(parents["core"])
        self.assertEqual(parents["x"], "core")
        self.assertEqual(parents["y"], "x")


class NormalizeMindmapEdgeTests(unittest.TestCase):
    def test_cross_link_edges_that_reference_labels_are_recovered(self) -> None:
        raw = {
            "root": "cell",
            "nodes": [
                {"id": "cell", "label": "Cell", "importance": 1.0},
                {"id": "mitochondria", "label": "Mitochondria", "parent": "cell", "importance": 0.7},
                {"id": "atp", "label": "ATP", "parent": "cell", "importance": 0.6},
            ],
            # endpoints given as labels, and the two nodes are siblings (not a
            # parent/child pair) so the recovered edge stays as a cross-link.
            "edges": [{"source": "Mitochondria", "target": "ATP", "relation": "produces"}],
        }

        out = normalize_mindmap(raw)

        self.assertEqual(
            out["edges"], [{"source": "mitochondria", "target": "atp", "relation": "produces"}]
        )

    def test_self_loops_dangling_and_duplicate_edges_are_dropped(self) -> None:
        raw = {
            "root": "a",
            "nodes": [
                {"id": "a", "label": "A", "importance": 1.0},
                {"id": "b", "label": "B", "parent": "a", "importance": 0.5},
                {"id": "c", "label": "C", "parent": "a", "importance": 0.5},
            ],
            "edges": [
                {"source": "b", "target": "b", "relation": "self"},
                {"source": "b", "target": "c", "relation": "keep"},
                {"source": "c", "target": "b", "relation": "duplicate"},
                {"source": "b", "target": "ghost", "relation": "dangling"},
            ],
        }

        out = normalize_mindmap(raw)

        self.assertEqual(out["edges"], [{"source": "b", "target": "c", "relation": "keep"}])

    def test_edges_that_only_restate_the_parent_backbone_are_dropped(self) -> None:
        raw = {
            "root": "p",
            "nodes": [
                {"id": "p", "label": "P", "importance": 1.0},
                {"id": "q", "label": "Q", "parent": "p", "importance": 0.5},
            ],
            "edges": [{"source": "p", "target": "q", "relation": "contains"}],
        }

        self.assertEqual(normalize_mindmap(raw)["edges"], [])


class DeriveTreeTests(unittest.TestCase):
    NODES = [
        {"id": "root", "label": "Root", "group": "g", "importance": 0.9},
        {"id": "a", "label": "A", "group": "g", "importance": 0.6},
        {"id": "b", "label": "B", "group": "g", "importance": 0.4},
    ]

    def test_root_hint_wins_when_valid(self) -> None:
        root, _ = _derive_tree(self.NODES, [], {}, "a", {"root": "root", "a": "a", "b": "b"})
        self.assertEqual(root, "a")

    def test_root_falls_back_to_highest_importance(self) -> None:
        root, _ = _derive_tree(self.NODES, [], {}, "", {})
        self.assertEqual(root, "root")

    def test_valid_parent_hints_are_honoured(self) -> None:
        keys = {"root": "root", "a": "a", "b": "b"}
        root, parents = _derive_tree(self.NODES, [], {"a": "root", "b": "a"}, "root", keys)
        self.assertEqual(root, "root")
        self.assertEqual(parents, {"a": "root", "b": "a"})

    def test_a_parent_cycle_is_broken_and_everything_still_reaches_root(self) -> None:
        keys = {"root": "root", "a": "a", "b": "b"}
        # a -> b -> a is a cycle with no path to root
        _, parents = _derive_tree(self.NODES, [], {"a": "b", "b": "a"}, "root", keys)
        # walk every node up to the root
        for start in ("a", "b"):
            seen, cur = set(), start
            while cur in parents:
                self.assertNotIn(cur, seen)
                seen.add(cur)
                cur = parents[cur]
            self.assertEqual(cur, "root")

    def test_self_parent_hint_is_ignored(self) -> None:
        keys = {"root": "root", "a": "a", "b": "b"}
        _, parents = _derive_tree(self.NODES, [], {"a": "a"}, "root", keys)
        self.assertNotEqual(parents.get("a"), "a")

    def test_edge_graph_fills_parents_when_hints_are_missing(self) -> None:
        edges = [{"source": "root", "target": "a", "relation": "r"},
                 {"source": "a", "target": "b", "relation": "r"}]
        keys = {"root": "root", "a": "a", "b": "b"}
        _, parents = _derive_tree(self.NODES, edges, {}, "root", keys)
        self.assertEqual(parents, {"a": "root", "b": "a"})

    def test_disconnected_node_is_attached_straight_to_root(self) -> None:
        keys = {"root": "root", "a": "a", "b": "b"}
        _, parents = _derive_tree(self.NODES, [], {}, "root", keys)
        self.assertEqual(parents["a"], "root")
        self.assertEqual(parents["b"], "root")


class LegacySanitizeContractTests(unittest.TestCase):
    def test_flat_sanitize_keeps_backbone_edges_and_adds_no_hierarchy(self) -> None:
        # test_m4_local_provider.py depends on this exact behaviour.
        raw = {
            "nodes": [
                {"id": "cell", "label": "Cell", "group": "topic", "importance": 1.7},
                {"id": "atp", "label": "ATP", "group": "energy", "importance": -0.2},
            ],
            "edges": [
                {"source": "cell", "target": "atp", "relation": "uses"},
                {"source": "cell", "target": "missing", "relation": "contains"},
            ],
        }

        result = _sanitize_mindmap(raw)

        self.assertEqual([n["importance"] for n in result["nodes"]], [1.0, 0.0])
        self.assertEqual(result["edges"], [{"source": "cell", "target": "atp", "relation": "uses"}])
        self.assertNotIn("root", result)
        self.assertNotIn("parent", result["nodes"][0])


class NormalizeMindmapConnectivityTests(unittest.TestCase):
    def test_nodes_with_no_edges_still_form_a_rooted_star(self) -> None:
        raw = {
            "nodes": [
                {"id": "sun", "label": "Sun", "importance": 0.95},
                {"id": "earth", "label": "Earth", "importance": 0.4},
                {"id": "moon", "label": "Moon", "importance": 0.3},
            ],
            "edges": [],
        }

        out = normalize_mindmap(raw)

        self.assertEqual(out["root"], "sun")
        self.assertEqual(_parents(out), {"sun": None, "earth": "sun", "moon": "sun"})
        self.assertEqual(out["edges"], [])  # synthetic connectivity links are not cross-links

    def test_orphan_node_is_parented_to_the_root(self) -> None:
        raw = {
            "root": "a",
            "nodes": [
                {"id": "a", "label": "A", "importance": 0.9},
                {"id": "b", "label": "B", "parent": "a", "importance": 0.5},
                {"id": "lonely", "label": "Lonely", "importance": 0.2},
            ],
            "edges": [{"source": "a", "target": "b", "relation": "r"}],
        }

        self.assertEqual(_parents(normalize_mindmap(raw))["lonely"], "a")

    def test_single_node_map(self) -> None:
        out = normalize_mindmap({"nodes": [{"id": "solo", "label": "Solo"}], "edges": []})

        self.assertEqual(out["root"], "solo")
        self.assertEqual(out["nodes"][0]["parent"], None)
        self.assertEqual(out["edges"], [])

    def test_empty_input_returns_a_rootless_empty_graph(self) -> None:
        self.assertEqual(normalize_mindmap({}), {"root": None, "nodes": [], "edges": []})
        self.assertEqual(
            normalize_mindmap({"nodes": None, "edges": None}),
            {"root": None, "nodes": [], "edges": []},
        )


class MindmapPromptSchemaTests(unittest.TestCase):
    def test_tool_schema_asks_for_root_and_node_parent(self) -> None:
        params = MINDMAP_TOOL["function"]["parameters"]
        self.assertIn("root", params["properties"])
        self.assertIn("root", params["required"])
        node_props = params["properties"]["nodes"]["items"]["properties"]
        self.assertIn("parent", node_props)


class SynthesizeMindmapContractTests(unittest.TestCase):
    def test_mindmap_mode_output_validates_and_is_rooted(self) -> None:
        from backend.components.knowledge_maps import synthesis

        model_output = {
            "root": "Cell",
            "nodes": [
                {"id": "Cell", "label": "Cell"},
                {"id": "atp", "label": "ATP", "parent": "Cell"},
                {"id": "dna", "label": "DNA", "parent": "Cell"},
            ],
            "edges": [{"source": "atp", "target": "dna", "relation": "near"}],
        }

        with patch.object(synthesis.llm_client, "chat_with_tools", return_value=model_output):
            out = synthesis.synthesize("some biology text", "mindmap", "en")

        MindMapResponse(**out)  # must not raise
        self.assertEqual(out["root"], "cell")
        self.assertEqual(_parents(out)["atp"], "cell")
        self.assertEqual(out["edges"], [{"source": "atp", "target": "dna", "relation": "near"}])

    def test_degenerate_model_output_still_returns_a_valid_payload(self) -> None:
        from backend.components.knowledge_maps import synthesis

        with patch.object(
            synthesis.llm_client, "chat_with_tools", return_value={"nodes": [], "edges": []}
        ):
            out = synthesis.synthesize("text", "mindmap", "en")

        self.assertEqual(out, {"root": None, "nodes": [], "edges": []})
        MindMapResponse(**out)

    def test_other_modes_are_passed_through_untouched(self) -> None:
        from backend.components.knowledge_maps import synthesis

        payload = {"flashcards": [{"front": "Q", "back": "A"}]}
        with patch.object(synthesis.llm_client, "chat_with_tools", return_value=payload):
            out = synthesis.synthesize("text", "flashcards", "en")

        self.assertIs(out, payload)


if __name__ == "__main__":
    unittest.main()
