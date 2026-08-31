"use strict";

// Run:  node tests/test_mindmap_render_smoke.js
//
// mindmap-render.js is the d3 drawing layer — it is only truly exercised in a
// real browser (no jsdom in this repo). This smoke test just proves the module
// loads headless, exposes the whole public API, and degrades gracefully when
// there is no `window.d3` / DOM instead of throwing.
const assert = require("node:assert/strict");
const R = require("../frontend/knowledge_maps/mindmap-render.js");

const API = [
  "render", "showLoading", "showError",
  "fit", "zoomBy", "zoomReset", "collapseAll", "expandAll",
  "exportSVG", "exportPNG", "exportJSON", "destroy",
];
for (const name of API) {
  assert.equal(typeof R[name], "function", `missing MindMapRender.${name}`);
}

// No window.d3 and no document → render() returns null, never throws.
assert.equal(R.render({ root: "a", nodes: [{ id: "a", label: "A" }], edges: [] }, { svgId: "x" }), null);
assert.equal(R.render(null, {}), null);

// Control calls against an unknown id are no-ops, not exceptions.
for (const name of ["fit", "zoomReset", "collapseAll", "expandAll", "exportSVG", "exportPNG", "exportJSON", "destroy"]) {
  R[name]("does-not-exist");
}
R.zoomBy(1.25, "does-not-exist");
R.showLoading({ svgId: "x" });
R.showError({ svgId: "x" }, "boom");

console.log("mindmap-render smoke tests passed");
