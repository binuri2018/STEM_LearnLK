"use strict";

const assert = require("node:assert/strict");
const { composeRepairBlocks, serverTagsAreCurrent } = require("../frontend/knowledge_maps/repair-state.js");

const blocks = [
  {
    block_id: "B1",
    original_text: "- Photosynthesis happens in mitochondria.\n",
    final_text: "- Photosynthesis happens in chloroplasts.\n",
    status: "repaired",
  },
  {
    block_id: "B2",
    original_text: "- Chlorophyll absorbs light.\n",
    final_text: "- Chlorophyll absorbs light.\n",
    status: "unchanged",
  },
];
const repairs = [{
  repair_id: "R1",
  block_id: "B1",
  block_start: 2,
  block_end: 41,
  proposed_claim: "Photosynthesis happens in chloroplasts.",
  repair_status: "repaired",
}];

assert.equal(
  composeRepairBlocks(blocks, repairs, new Set(["R1"])),
  "- Photosynthesis happens in chloroplasts.\n- Chlorophyll absorbs light.\n",
);
assert.equal(serverTagsAreCurrent(repairs, new Set(["R1"])), true);
assert.equal(serverTagsAreCurrent(repairs, new Set()), false);
assert.equal(
  composeRepairBlocks(blocks, repairs, new Set()),
  "- Chlorophyll absorbs light.\n",
);

// One paragraph block: a mapped `repaired` repair + an unmapped `unresolved` one.
// The verified fix is spliced in; the unresolved sentence is kept as written.
const mixedBlocks = [{
  block_id: "B1",
  block_type: "paragraph",
  original_text:
    "Fructose is the sweetest sugar. Glucose is found in ripe fruits and bee honey.\n",
  final_text:
    "Sucrose forms from a glucose and a fructose molecule. " +
    "Glucose is found in ripe fruits and bee honey.\n",
  status: "repaired",
}];
const mixedRepairs = [
  {
    repair_id: "R1", block_id: "B1", block_start: 0, block_end: 31,
    proposed_claim: "Sucrose forms from a glucose and a fructose molecule.",
    repair_status: "repaired",
  },
  {
    repair_id: "R2", block_id: "B1", block_start: null, block_end: null,
    repair_status: "unresolved",
  },
];

const mixedApplied = composeRepairBlocks(mixedBlocks, mixedRepairs, new Set(["R1"]));
assert.ok(mixedApplied.includes("Sucrose forms from a glucose and a fructose molecule."));
assert.ok(mixedApplied.includes("Glucose is found in ripe fruits and bee honey."));
assert.ok(!mixedApplied.includes("Fructose is the sweetest sugar."));
assert.notEqual(mixedApplied.trim(), "");

const mixedUndone = composeRepairBlocks(mixedBlocks, mixedRepairs, new Set());
assert.ok(mixedUndone.includes("Glucose is found in ripe fruits and bee honey."));
assert.ok(!mixedUndone.includes("Fructose is the sweetest sugar."));

console.log("repair-state tests passed");
