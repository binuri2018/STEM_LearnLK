"use strict";

// Run:  node tests/test_mindmap_model.js
const assert = require("node:assert/strict");
const {
  normalizeGraph,
  buildHierarchy,
  assignBranchColors,
  computeFitTransform,
  resolveViewport,
  radiusFor,
  groupColor,
  slugify,
  BRANCH_COLORS,
  ROOT_COLOR,
} = require("../frontend/knowledge_maps/mindmap-model.js");

/* ── normalizeGraph: shape + guards ─────────────────────────────────────── */

/* 1. Always produces a rooted tree: every non-root node gets a parent. */
{
  const g = normalizeGraph({
    root: "photosynthesis",
    nodes: [
      { id: "photosynthesis", label: "Photosynthesis", importance: 1 },
      { id: "light", label: "Light Reactions", parent: "photosynthesis", importance: 0.8 },
      { id: "calvin", label: "Calvin Cycle", parent: "photosynthesis", importance: 0.8 },
    ],
    edges: [],
  });
  assert.equal(g.ok, true);
  assert.equal(g.root, "photosynthesis");
  const parent = Object.fromEntries(g.nodes.map((n) => [n.id, n.parent]));
  assert.equal(parent.photosynthesis, null);
  assert.equal(parent.light, "photosynthesis");
  assert.equal(parent.calvin, "photosynthesis");
}

/* 2. A cross-link between two siblings (given by label) survives; a link that
      only restates the parent backbone is dropped. */
{
  const g = normalizeGraph({
    root: "cell",
    nodes: [
      { id: "cell", label: "Cell", importance: 1 },
      { id: "mito", label: "Mitochondria", parent: "cell", importance: 0.7 },
      { id: "atp", label: "ATP", parent: "cell", importance: 0.6 },
    ],
    edges: [
      { source: "Mitochondria", target: "ATP", relation: "produces" }, // sibling cross-link
      { source: "cell", target: "mito", relation: "contains" },        // backbone restatement
    ],
  });
  assert.deepEqual(g.edges, [{ source: "mito", target: "atp", relation: "produces" }]);
}

/* 3. Missing root/parent → derived from the highest-importance node + edges. */
{
  const g = normalizeGraph({
    nodes: [
      { id: "a", label: "A", importance: 0.3 },
      { id: "b", label: "B", importance: 0.9 },
      { id: "c", label: "C", importance: 0.2 },
    ],
    edges: [{ source: "b", target: "a" }, { source: "a", target: "c" }],
  });
  assert.equal(g.root, "b");
  const parent = Object.fromEntries(g.nodes.map((n) => [n.id, n.parent]));
  assert.equal(parent.a, "b");
  assert.equal(parent.c, "a");
}

/* 4. Self-loops, duplicates and unknown endpoints never reach the output. */
{
  const g = normalizeGraph({
    root: "a",
    nodes: [
      { id: "a", label: "A", importance: 1 },
      { id: "b", label: "B", parent: "a", importance: 0.5 },
      { id: "c", label: "C", parent: "a", importance: 0.5 },
    ],
    edges: [
      { source: "b", target: "b" },
      { source: "b", target: "c", relation: "keep" },
      { source: "c", target: "b" },
      { source: "b", target: "ghost" },
    ],
  });
  assert.deepEqual(g.edges, [{ source: "b", target: "c", relation: "keep" }]);
  const ids = new Set(g.nodes.map((n) => n.id));
  for (const e of g.edges) { assert.ok(ids.has(e.source)); assert.ok(ids.has(e.target)); }
}

/* 5. Garbage / empty input never throws; ok:false when undrawable. */
{
  const empty = normalizeGraph(null);
  assert.deepEqual(empty.nodes, []);
  assert.deepEqual(empty.edges, []);
  assert.equal(empty.root, null);
  assert.equal(empty.ok, false);

  const one = normalizeGraph({ nodes: ["Cell", null, { label: "" }], edges: ["x", 3] });
  assert.deepEqual(one.nodes.map((n) => n.label), ["Cell"]);
  assert.equal(one.ok, true);
  assert.equal(one.root, "cell");
  assert.equal(one.edges.length, 0);
}

/* 6. Duplicate node ids are disambiguated. */
{
  const g = normalizeGraph({ nodes: [{ id: "x", label: "One" }, { id: "x", label: "Two" }], edges: [] });
  assert.notEqual(g.nodes[0].id, g.nodes[1].id);
}

/* 6b. Slug-style labels are humanised; real labels are left alone. */
{
  const g = normalizeGraph({
    root: "r",
    nodes: [
      { id: "r", label: "Root" },
      { id: "a", label: "light_dependent", parent: "r" },
      { id: "b", label: "atp-nadph", parent: "r" },
      { id: "c", label: "ATP", parent: "r" },
      { id: "d", label: "Calvin Cycle", parent: "r" },
      { id: "e", label: "chloroplasts", parent: "r" },
      { id: "f", label: "co2", parent: "r" },
    ],
    edges: [],
  });
  const labels = Object.fromEntries(g.nodes.map((n) => [n.id, n.label]));
  assert.equal(labels.a, "Light Dependent");
  assert.equal(labels.b, "Atp Nadph");
  assert.equal(labels.c, "ATP");
  assert.equal(labels.d, "Calvin Cycle");
  assert.equal(labels.e, "Chloroplasts");
  assert.equal(labels.f, "co2");
}

/* ── buildHierarchy ────────────────────────────────────────────────────── */

/* 7. Builds a nested tree with depths and importance-sorted children. */
{
  const graph = normalizeGraph({
    root: "r",
    nodes: [
      { id: "r", label: "Root", importance: 1 },
      { id: "big", label: "Big", parent: "r", importance: 0.9 },
      { id: "small", label: "Small", parent: "r", importance: 0.2 },
      { id: "leaf", label: "Leaf", parent: "big", importance: 0.5 },
    ],
    edges: [],
  });
  const tree = buildHierarchy(graph);
  assert.equal(tree.id, "r");
  assert.equal(tree.depth, 0);
  assert.deepEqual(tree.children.map((c) => c.id), ["big", "small"]); // sorted by importance desc
  assert.equal(tree.children[0].children[0].id, "leaf");
  assert.equal(tree.children[0].children[0].depth, 2);
}

/* 8. buildHierarchy tolerates a cycle in parent pointers (no infinite recursion). */
{
  const tree = buildHierarchy({
    root: "r",
    nodes: [
      { id: "r", label: "R", importance: 1 },
      { id: "a", label: "A", parent: "b", importance: 0.5 },
      { id: "b", label: "B", parent: "a", importance: 0.5 },
    ],
    edges: [],
  });
  const seen = new Set();
  (function walk(n) { assert.ok(!seen.has(n.id)); seen.add(n.id); n.children.forEach(walk); })(tree);
  assert.equal(seen.size, 3);
}

/* 9. buildHierarchy(null-ish) returns null. */
{
  assert.equal(buildHierarchy(null), null);
  assert.equal(buildHierarchy({ nodes: [] }), null);
}

/* ── assignBranchColors ────────────────────────────────────────────────── */

/* 10. Root gets ROOT_COLOR; each branch a palette colour inherited by descendants. */
{
  const tree = buildHierarchy(normalizeGraph({
    root: "r",
    nodes: [
      { id: "r", label: "R", importance: 1 },
      { id: "b1", label: "B1", parent: "r", importance: 0.9 },
      { id: "b2", label: "B2", parent: "r", importance: 0.8 },
      { id: "b1a", label: "B1a", parent: "b1", importance: 0.4 },
    ],
    edges: [],
  }));
  const colors = assignBranchColors(tree);
  assert.equal(colors.get("r"), ROOT_COLOR);
  assert.equal(colors.get("b1"), BRANCH_COLORS[0]);
  assert.equal(colors.get("b2"), BRANCH_COLORS[1]);
  assert.equal(colors.get("b1a"), colors.get("b1")); // descendant inherits the branch colour
  // deterministic
  assert.equal(assignBranchColors(tree).get("b2"), BRANCH_COLORS[1]);
}

/* ── computeFitTransform ───────────────────────────────────────────────── */

/* 11. Returns a finite, positive, clamped k and centres the bbox. */
{
  const t = computeFitTransform({ x: -100, y: -50, width: 200, height: 100 }, { width: 800, height: 400 });
  assert.ok(Number.isFinite(t.k) && t.k > 0);
  assert.ok(t.k <= 2.5);
  // bbox centre (0,0) maps to viewport centre (400,200)
  assert.ok(Math.abs(t.x - 400) < 1e-6);
  assert.ok(Math.abs(t.y - 200) < 1e-6);

  const degenerate = computeFitTransform({ x: 0, y: 0, width: 0, height: 0 }, { width: 0, height: 0 });
  assert.ok(Number.isFinite(degenerate.k) && degenerate.k > 0);
}

/* ── unchanged primitives ──────────────────────────────────────────────── */

/* 12. resolveViewport never yields a zero dimension. */
{
  assert.deepEqual(resolveViewport(null, { width: 640, height: 480 }), { width: 640, height: 480 });
  const hidden = { clientWidth: 0, clientHeight: 0, getBoundingClientRect: () => ({ width: 0, height: 0 }) };
  assert.deepEqual(resolveViewport(hidden, { width: 800, height: 500 }), { width: 800, height: 500 });
  const shown = { clientWidth: 1000, clientHeight: 620, getBoundingClientRect: () => ({ width: 1000, height: 620 }) };
  assert.deepEqual(resolveViewport(shown, { width: 800, height: 500 }), { width: 1000, height: 620 });
}

/* 13. radiusFor stays in [10, 28] and tolerates junk. */
{
  assert.equal(radiusFor(0), 10);
  assert.equal(radiusFor(1), 28);
  assert.equal(radiusFor(9), 28);
  assert.equal(radiusFor("nonsense"), 19);
  assert.equal(radiusFor(undefined), 19);
}

/* 14. groupColor is deterministic and returns a hex colour. */
{
  assert.equal(groupColor("process"), groupColor("process"));
  assert.ok(/^#[0-9a-f]{6}$/i.test(groupColor("organelle")));
  assert.ok(/^#[0-9a-f]{6}$/i.test(groupColor(undefined)));
}

/* 15. slugify normalises case / spacing / punctuation. */
{
  assert.equal(slugify("  Light Reaction! "), "light-reaction");
  assert.equal(slugify("ATP"), "atp");
  assert.equal(slugify(""), "");
}

console.log("mindmap-model tests passed");
