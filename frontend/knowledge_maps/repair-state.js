(function repairStateModule(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.RepairState = api;
})(typeof window !== "undefined" ? window : globalThis, function buildRepairState() {
  "use strict";

  function composeRepairBlocks(blocks, repairs, acceptedRepairIds) {
    const accepted = acceptedRepairIds instanceof Set
      ? acceptedRepairIds
      : new Set(acceptedRepairIds || []);
    const byBlock = new Map();
    for (const repair of repairs || []) {
      if (!byBlock.has(repair.block_id)) byBlock.set(repair.block_id, []);
      byBlock.get(repair.block_id).push(repair);
    }

    let output = "";
    for (const block of blocks || []) {
      const related = byBlock.get(block.block_id) || [];
      if (block.status === "excluded" && !related.length) continue;

      let text = String(block.original_text || "");
      // Only `repaired` spans are ever rewritten. Unresolved / failed claims are
      // left exactly as written, so the note keeps every original sentence.
      // An accepted repair splices its proposal; an undone one removes just that
      // sentence (README: exclude rather than restore incorrect text).
      const replacements = [];
      for (const repair of related) {
        if (repair.repair_status !== "repaired") continue;
        if (!Number.isInteger(repair.block_start) || !Number.isInteger(repair.block_end)) continue;
        replacements.push([
          repair.block_start,
          repair.block_end,
          accepted.has(repair.repair_id) ? String(repair.proposed_claim || "") : "",
        ]);
      }
      replacements.sort((left, right) => right[0] - left[0]);
      for (const [start, end, replacement] of replacements) {
        text = text.slice(0, start) + replacement + text.slice(end);
      }
      const meaningful = text.replace(/^\s*(?:[-*+]\s*|\d+[.)]\s*)/, "").trim();
      if (meaningful || block.block_type === "heading" || block.block_type === "blank") {
        output += text;
      }
    }
    return output;
  }

  function serverTagsAreCurrent(repairs, acceptedRepairIds) {
    const accepted = acceptedRepairIds instanceof Set
      ? acceptedRepairIds
      : new Set(acceptedRepairIds || []);
    return (repairs || [])
      .filter((repair) => repair.repair_status === "repaired")
      .every((repair) => accepted.has(repair.repair_id));
  }

  return { composeRepairBlocks, serverTagsAreCurrent };
});
