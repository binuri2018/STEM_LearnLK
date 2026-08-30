// d3 is vendored (web/vendor/d3.v7.min.js) and used only by the mind-map
// renderer (web/mindmap-render.js), loaded as classic scripts before this one.

const API = "";
const $ = (id) => document.getElementById(id);

/* ══════════════════════════════════════════════════
   UTILITY
══════════════════════════════════════════════════ */
function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function showEl(id)  { const e = $(id); if (e) { e.hidden = false; e.classList.remove("hidden"); } }
function hideEl(id)  { const e = $(id); if (e) { e.hidden = true;  e.classList.add("hidden"); } }

/* ══════════════════════════════════════════════════
   HEALTH
══════════════════════════════════════════════════ */
async function refreshHealth() {
  const pill = $("health-pill");
  try {
    const r = await fetch(`${API}/api/health`);
    const j = await r.json();
    if (j.index_loaded) {
      pill.textContent = j.openai_configured ? "Index ready · OpenAI on" : "Index ready · Ollama chat";
      pill.className = "health-pill ok";
    } else {
      pill.textContent = "No index — run ingest.py";
      pill.className = "health-pill bad";
    }
  } catch {
    pill.textContent = "API unreachable";
    pill.className = "health-pill bad";
  }
}

/* ══════════════════════════════════════════════════
   MAIN TAB SWITCHING
══════════════════════════════════════════════════ */
const tabButtons = document.querySelectorAll(".tab-nav .tab");
const tabPanels  = document.querySelectorAll(".tab-panel");

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.tab;
    tabButtons.forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    tabPanels.forEach((p) => {
      p.classList.remove("active");
      p.hidden = true;
    });
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
    const panel = $(`tab-${target}`);
    if (panel) { panel.classList.add("active"); panel.hidden = false; }
  });
});

/* ── Sub-tab switching (shared helper) ─────────── */
function wireSubTabs(containerSelector) {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  const btns   = container.querySelectorAll(".sub-tab");
  const panels = container.querySelectorAll(".sub-tab-panel");
  btns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.subtab;
      btns.forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
      panels.forEach((p) => { p.classList.remove("active"); p.hidden = true; });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      const panel = $(`subtab-${target}`);
      if (panel) { panel.classList.add("active"); panel.hidden = false; }
    });
  });
}

wireSubTabs("#verify-result-tabs");
wireSubTabs("#tab-synthesis .panel");

/* ══════════════════════════════════════════════════
   Q&A TAB
══════════════════════════════════════════════════ */
function renderSources(items) {
  const el = $("sources");
  el.innerHTML = "";
  if (!items.length) {
    el.innerHTML = `<p class="source-meta">No chunks retrieved.</p>`;
    return;
  }
  for (const s of items) {
    const card = document.createElement("div");
    card.className = "source-card";
    const title = [s.subject_area, s.topic].filter(Boolean).join(" · ") || "Syllabus excerpt";
    const bits = [];
    if (s.grade != null) bits.push(`Grade ${s.grade}`);
    if (s.document_type) bits.push(s.document_type);
    if (s.source_file) bits.push(s.source_file);
    if (s.page_start != null)
      bits.push(s.page_end != null && s.page_end !== s.page_start
        ? `pp. ${s.page_start}–${s.page_end}` : `p. ${s.page_start}`);
    if (s.score != null) bits.push(`sim. ${s.score.toFixed(3)}`);
    card.innerHTML = `<strong>${escapeHtml(title)}</strong><div class="source-meta">${escapeHtml(bits.join(" · "))}</div>`;
    el.appendChild(card);
  }
}

async function ask() {
  const q = $("question").value.trim();
  const lang = $("lang").value;
  const answerEl = $("answer");
  const btn = $("btn-ask");
  if (!q) {
    answerEl.textContent = "Please type or dictate a question.";
    answerEl.classList.add("muted");
    return;
  }
  btn.disabled = true;
  answerEl.textContent = "Thinking…";
  answerEl.classList.remove("muted");
  $("btn-tts").disabled = true;
  try {
    const r = await fetch(`${API}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, response_language: lang }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || r.statusText);
    }
    const data = await r.json();
    answerEl.textContent = data.answer || "";
    renderSources(data.sources || []);
    $("btn-tts").disabled = !data.answer;
    window.__lastAnswer = data.answer;
    window.__ttsLang = lang;
  } catch (e) {
    answerEl.textContent = `Error: ${e.message}`;
    answerEl.classList.add("muted");
    renderSources([]);
  } finally {
    btn.disabled = false;
  }
}

/* ── Voice input ───────────────────────────────── */
let mediaRecorder = null;
let audioChunks = [];

function pickMime() {
  if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  return "";
}

async function toggleMic() {
  const btn = $("btn-mic");
  const label = $("mic-label");
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = pickMime();
    mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btn.classList.remove("recording");
      label.textContent = "Voice input";
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      await sendTranscribe(blob);
    };
    mediaRecorder.start();
    btn.classList.add("recording");
    label.textContent = "Stop…";
  } catch (e) {
    alert(`Microphone error: ${e.message}`);
  }
}

async function sendTranscribe(blob) {
  const fd = new FormData();
  fd.append("file", blob, "question.webm");
  try {
    const r = await fetch(`${API}/api/transcribe`, { method: "POST", body: fd });
    if (r.status === 501) {
      alert("Whisper needs OPENAI_API_KEY on the server.");
      return;
    }
    if (!r.ok) throw new Error(await r.text());
    const j = await r.json();
    $("question").value = (j.text || "").trim();
  } catch (e) {
    alert(`Transcription failed: ${e.message}`);
  }
}

/* ── TTS ───────────────────────────────────────── */
function browserTts(text, langMode) {
  const u = new SpeechSynthesisUtterance(text);
  if (langMode === "si") u.lang = "si-LK";
  else if (langMode === "en") u.lang = "en-US";
  else u.lang = /[඀-෿]/.test(text) ? "si-LK" : "en-US";
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

async function playTts() {
  const text = window.__lastAnswer;
  if (!text) return;
  const lang = window.__ttsLang || "auto";
  try {
    const r = await fetch(`${API}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (r.ok) {
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play();
      audio.onended = () => URL.revokeObjectURL(url);
      return;
    }
  } catch { /* fall through */ }
  browserTts(text, lang);
}

$("btn-ask").addEventListener("click", ask);
$("btn-mic").addEventListener("click", toggleMic);
$("btn-tts").addEventListener("click", playTts);
$("question").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask(); });

/* ══════════════════════════════════════════════════
   VERIFY NOTES TAB — drop zone + OCR
══════════════════════════════════════════════════ */
const dropZone  = $("drop-zone");
const noteFile  = $("note-file");
const ocrStatus = $("ocr-status");

dropZone.addEventListener("click", () => noteFile.click());
dropZone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") noteFile.click(); });

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer?.files?.[0];
  if (file && file.type.startsWith("image/")) loadImageFile(file);
});

noteFile.addEventListener("change", () => {
  if (noteFile.files?.[0]) loadImageFile(noteFile.files[0]);
});

let selectedImageFile = null;

function loadImageFile(file) {
  selectedImageFile = file;
  const url = URL.createObjectURL(file);
  $("image-preview").src = url;
  $("image-preview-wrap").classList.remove("hidden");
  $("image-preview-wrap").hidden = false;
  ocrStatus.textContent = "Image ready — click Upload & Extract Text";
  ocrStatus.className = "ocr-status";
  $("btn-verify").disabled = false;
  $("btn-correct-note-quick").disabled = false;
}

$("btn-clear-image").addEventListener("click", () => {
  selectedImageFile = null;
  noteFile.value = "";
  $("image-preview").src = "";
  $("image-preview-wrap").classList.add("hidden");
  $("image-preview-wrap").hidden = true;
  $("extracted-text").value = "";
  ocrStatus.textContent = "";
  $("btn-verify").disabled = true;
});

$("btn-upload-ocr").addEventListener("click", uploadAndOcr);

async function uploadAndOcr() {
  if (!selectedImageFile) {
    const text = $("extracted-text").value.trim();
    if (text) {
      $("btn-verify").disabled = false;
      return;
    }
    alert("Please select an image first.");
    return;
  }
  ocrStatus.textContent = "Uploading…";
  ocrStatus.className = "ocr-status loading";
  $("btn-upload-ocr").disabled = true;

  const fd = new FormData();
  fd.append("file", selectedImageFile);

  try {
    const r = await fetch(`${API}/api/upload-ocr`, { method: "POST", body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || r.statusText);
    }
    const data = await r.json();
    $("extracted-text").value = data.text || "";
    if (data.signed_url) {
      $("image-preview").src = data.signed_url;
    }
    ocrStatus.textContent = "Text extracted";
    ocrStatus.className = "ocr-status done";
    $("btn-verify").disabled = false;
    $("btn-correct-note-quick").disabled = false;
  } catch (e) {
    ocrStatus.textContent = `OCR failed: ${e.message}`;
    ocrStatus.className = "ocr-status error";
  } finally {
    $("btn-upload-ocr").disabled = false;
  }
}

/* ── Verify content ────────────────────────────── */
$("btn-verify").addEventListener("click", runVerification);
$("btn-correct-note-quick").addEventListener("click", runCorrectNote);
$("btn-correct-note").addEventListener("click", runCorrectNote);
$("find-videos-btn").addEventListener("click", findVideosByTags);

async function runVerification() {
  const text = $("extracted-text").value.trim();
  if (!text) { alert("Please enter or extract some text first."); return; }
  const lang = $("verify-lang").value;

  $("btn-verify").disabled = true;
  hideEl("verify-placeholder");
  showEl("verify-result-tabs");

  $("claims-list").innerHTML = `<div class="yt-loading"><div class="spinner"></div><span>Verifying…</span></div>`;
  $("corrections-list").innerHTML = `<p class="muted-hint">Running…</p>`;

  try {
    const r = await fetch(`${API}/api/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, response_language: lang }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const data = await r.json();
    renderVerificationResult(data, "score-text", "score-pct", "score-fill", "claims-list");
    renderCorrections(data.claims, "corrections-list");
  } catch (e) {
    $("claims-list").innerHTML = `<p class="muted-hint" style="color:var(--danger)">Error: ${escapeHtml(e.message)}</p>`;
  } finally {
    $("btn-verify").disabled = false;
  }
}

async function runCorrectNote() {
  const text = $("extracted-text").value.trim();
  if (!text) { alert("Please enter or extract some text first."); return; }
  const lang = $("verify-lang").value;

  // Switch to the Corrected Note sub-tab and show loading
  hideEl("verify-placeholder");
  showEl("verify-result-tabs");
  // Activate the corrected-note sub-tab
  document.querySelectorAll("#verify-result-tabs .sub-tab").forEach(b => {
    const active = b.dataset.subtab === "corrected-note";
    b.classList.toggle("active", active);
    b.setAttribute("aria-selected", active);
  });
  document.querySelectorAll("#verify-result-tabs .sub-tab-panel").forEach(p => {
    p.hidden = p.id !== "subtab-corrected-note";
    p.classList.toggle("active", p.id === "subtab-corrected-note");
  });

  $("btn-correct-note-quick").disabled = true;
  $("btn-correct-note").disabled = true;
  showEl("correct-note-loading");
  $("corrected-note-output").innerHTML = "";

  try {
    const r = await fetch(`${API}/api/m4/repair-note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, response_language: lang, preserve_structure: true }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const data = await r.json();
    renderCorrectNote(data);
    if (data.tags && data.tags.length) renderTagChips(data.tags);

    // Also update Verification and Corrections tabs with the same run's data
    renderVerificationResult(data.verification, "score-text", "score-pct", "score-fill", "claims-list");
    renderCorrections(data.verification.claims, "corrections-list");
  } catch (e) {
    $("corrected-note-output").innerHTML =
      `<p class="muted-hint" style="color:var(--danger)">Error: ${escapeHtml(e.message)}</p>`;
  } finally {
    hideEl("correct-note-loading");
    $("btn-correct-note-quick").disabled = false;
    $("btn-correct-note").disabled = false;
  }
}

function renderCorrectNote(data) {
  if (Array.isArray(data.blocks) && Array.isArray(data.repairs)) {
    renderRepairNote(data);
    return;
  }
  renderLegacyCorrectNote(data);
}

function renderLegacyCorrectNote(data) {
  const out = $("corrected-note-output");
  out.innerHTML = "";

  // Sticky-note card with the rewritten note
  const note = document.createElement("div");
  note.className = "sticky-note";
  note.innerHTML = `<div class="sticky-note-label">✦ Corrected Note</div>${escapeHtml(data.corrected_note || "—")}`;
  out.appendChild(note);

  // Dropped claims list (struck-through)
  if (data.dropped_claims && data.dropped_claims.length) {
    const section = document.createElement("div");
    section.className = "dropped-claims-section";
    section.innerHTML = `<h4>Removed (${data.dropped_claims.length} incorrect / incomplete)</h4>`;
    for (const c of data.dropped_claims) {
      const item = document.createElement("div");
      item.className = "dropped-claim-item";
      item.textContent = c.claim;
      section.appendChild(item);
    }
    out.appendChild(section);
  }
  if (data.unresolved_claims && data.unresolved_claims.length) {
    const section = document.createElement("div");
    section.className = "unresolved-claims-section";
    const heading = document.createElement("h4");
    heading.textContent = `Not included (${data.unresolved_claims.length} unresolved)`;
    section.appendChild(heading);
    for (const c of data.unresolved_claims) {
      const item = document.createElement("div");
      item.className = "unresolved-claim-item";
      const reason = c.verdict === "verification_failed"
        ? "verification failed; retry"
        : "not enough evidence";
      item.textContent = `${c.claim} — ${reason}`;
      section.appendChild(item);
    }
    out.appendChild(section);
  }
}

function makeNotePane(label, text, modifier) {
  const pane = document.createElement("section");
  pane.className = `repair-note-pane ${modifier}`;
  const heading = document.createElement("h4");
  heading.textContent = label;
  const content = document.createElement("pre");
  content.className = "repair-note-text";
  content.textContent = text || "—";
  pane.append(heading, content);
  return { pane, content };
}

function renderRepairNote(data) {
  const out = $("corrected-note-output");
  out.innerHTML = "";
  const accepted = new Set(
    data.repairs.filter((repair) => repair.included_by_default).map((repair) => repair.repair_id),
  );

  // The server text is authoritative (built after the independent second pass).
  // Only fall back if it somehow came back blank, so the pane is never a bare "—".
  let repairedText = data.repaired_note;
  if (!repairedText || !repairedText.trim()) {
    repairedText =
      window.RepairState.composeRepairBlocks(data.blocks, data.repairs, accepted)
      || data.original_text;
  }

  const comparison = document.createElement("div");
  comparison.className = "repair-note-comparison";
  const original = makeNotePane("Original note", data.original_text, "original");
  const repaired = makeNotePane("Repaired and re-verified note", repairedText, "repaired");
  comparison.append(original.pane, repaired.pane);
  out.appendChild(comparison);

  const summary = document.createElement("p");
  summary.className = "repair-summary";
  const repairedCount = data.repairs.filter((item) => item.repair_status === "repaired").length;
  const unresolvedCount = data.repairs.filter((item) => ["unresolved", "failed"].includes(item.repair_status)).length;
  summary.textContent = `${repairedCount} claims repaired and re-verified · ${unresolvedCount} unresolved`;
  out.appendChild(summary);

  const refreshNote = () => {
    repaired.content.textContent = window.RepairState.composeRepairBlocks(
      data.blocks, data.repairs, accepted,
    ) || data.original_text;
    if (window.RepairState.serverTagsAreCurrent(data.repairs, accepted)) {
      if (data.tags?.length) renderTagChips(data.tags);
    } else {
      $("tag-chips-container").innerHTML = "";
      hideEl("tags-section");
      hideEl("tag-videos-section");
      hideEl("video-summary-panel");
    }
  };

  const history = document.createElement("section");
  history.className = "repair-history";
  const historyHeading = document.createElement("h4");
  historyHeading.textContent = "Revision history";
  history.appendChild(historyHeading);

  for (const item of data.repairs) {
    const card = document.createElement("article");
    card.className = `repair-history-card ${item.repair_status}`;
    const status = document.createElement("div");
    status.className = "repair-history-status";
    status.textContent = item.repair_status === "not_needed"
      ? "Kept unchanged"
      : item.repair_status === "repaired"
        ? "Repaired and re-verified"
        : item.repair_status === "failed"
          ? "Repair failed"
          : "Unresolved";
    card.appendChild(status);

    const originalClaim = document.createElement("p");
    originalClaim.className = "repair-original-claim";
    originalClaim.textContent = item.original_claim;
    card.appendChild(originalClaim);

    if (item.proposed_claim) {
      const arrow = document.createElement("span");
      arrow.className = "repair-arrow";
      arrow.textContent = "↓";
      const proposal = document.createElement("p");
      proposal.className = "repair-proposed-claim";
      proposal.textContent = item.proposed_claim;
      card.append(arrow, proposal);
    }
    if (item.change_reason) {
      const reason = document.createElement("p");
      reason.className = "repair-change-reason";
      reason.textContent = item.change_reason;
      card.appendChild(reason);
    } else if (item.unresolved_reason) {
      const reason = document.createElement("p");
      reason.className = "repair-change-reason";
      reason.textContent = `Not inserted: ${item.unresolved_reason.replaceAll("_", " ")}.`;
      card.appendChild(reason);
    }

    if (item.confidence) {
      const confidence = buildConfidence({ confidence: item.confidence });
      if (confidence) card.appendChild(confidence);
    }
    if (Array.isArray(item.evidence) && item.evidence.length) {
      const panelId = `repair-evidence-${++evidencePanelSequence}`;
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "evidence-toggle";
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-controls", panelId);
      toggle.textContent = `Second-pass evidence (${item.evidence.length})`;
      const panel = buildEvidencePanel({
        claim: item.proposed_claim || item.original_claim,
        evidence: item.evidence,
        evidence_status: "cited",
      }, panelId);
      toggle.addEventListener("click", () => {
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", String(!expanded));
        panel.hidden = expanded;
      });
      card.append(toggle, panel);
    }

    if (item.repair_status === "repaired") {
      const action = document.createElement("button");
      action.type = "button";
      action.className = "btn ghost btn-sm repair-toggle";
      const updateAction = () => {
        const isAccepted = accepted.has(item.repair_id);
        action.textContent = isAccepted ? "Undo repair" : "Reapply repair";
        action.setAttribute("aria-pressed", String(isAccepted));
        card.classList.toggle("student-rejected", !isAccepted);
      };
      action.addEventListener("click", () => {
        if (accepted.has(item.repair_id)) accepted.delete(item.repair_id);
        else accepted.add(item.repair_id);
        updateAction();
        refreshNote();
      });
      updateAction();
      card.appendChild(action);
    }
    history.appendChild(card);
  }
  out.appendChild(history);
}

/* ── Tag chips ──────────────────────────────────── */

function renderTagChips(tags) {
  const container = $("tag-chips-container");
  container.innerHTML = "";
  for (const tag of tags) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tag-chip selected";
    btn.textContent = tag;
    btn.addEventListener("click", () => btn.classList.toggle("selected"));
    container.appendChild(btn);
  }
  showEl("tags-section");
  hideEl("tag-videos-section");
  hideEl("video-summary-panel");
}

function getSelectedTags() {
  return Array.from(document.querySelectorAll("#tag-chips-container .tag-chip.selected"))
    .map(b => b.textContent.trim())
    .filter(Boolean);
}

async function findVideosByTags() {
  const tags = getSelectedTags();
  if (!tags.length) {
    alert("Select at least one tag to search.");
    return;
  }
  const topic = tags.join(" ");
  const btn = $("find-videos-btn");
  btn.disabled = true;
  showEl("tag-videos-loading");
  hideEl("tag-videos-section");
  hideEl("video-summary-panel");

  try {
    const r = await fetch(`${API}/api/m4/youtube-suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, max_results: 6 }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const data = await r.json();

    const grid = $("tag-videos-grid");
    grid.innerHTML = "";
    if (!data.videos || !data.videos.length) {
      grid.innerHTML = `<p class="muted-hint">No videos found for these topics.</p>`;
    } else {
      for (const v of data.videos) {
        const card = document.createElement("div");
        card.className = "yt-video-card";
        card.title = `Play "${v.title}"`;
        card.innerHTML = `
          <img src="${escapeHtml(v.thumbnail)}" alt="${escapeHtml(v.title)}" loading="lazy">
          <div class="yt-video-card-body">
            <div class="yt-video-card-title">${escapeHtml(v.title)}</div>
            <div class="yt-video-card-channel">${escapeHtml(v.channel)}</div>
            <button type="button" class="btn ghost btn-summarize" data-url="${escapeHtml(v.url)}" data-title="${escapeHtml(v.title)}">
              <span class="btn-icon">⬇</span> Summarize
            </button>
          </div>`;
        // Clicking anywhere on the card (outside the Summarize button) opens
        // and plays the video in a new tab.
        card.addEventListener("click", (e) => {
          if (e.target.closest(".btn-summarize")) return;
          window.open(v.url, "_blank", "noopener");
        });
        grid.appendChild(card);
      }
      grid.querySelectorAll(".btn-summarize").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          summarizeVideo(btn.dataset.url, btn.dataset.title);
        });
      });
    }
    showEl("tag-videos-section");
  } catch (e) {
    $("tag-videos-grid").innerHTML =
      `<p class="muted-hint" style="color:var(--danger)">Error: ${escapeHtml(e.message)}</p>`;
    showEl("tag-videos-section");
  } finally {
    hideEl("tag-videos-loading");
    btn.disabled = false;
  }
}

async function summarizeVideo(url, title) {
  const panel = $("video-summary-panel");
  const content = $("video-summary-content");
  showEl("video-summary-panel");
  showEl("video-summary-loading");
  hideEl("video-summary-content");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const r = await fetch(`${API}/api/m4/video-summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, language: "auto" }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const data = await r.json();

    $("video-summary-title").textContent = title || "Video Summary";
    $("video-summary-text").textContent = data.summary || "";

    const ul = $("video-key-points");
    ul.innerHTML = "";
    for (const pt of (data.key_points || [])) {
      const li = document.createElement("li");
      li.textContent = pt;
      ul.appendChild(li);
    }

    $("add-to-note-btn").onclick = () => appendSummaryToNote(data.summary, data.key_points, title);
    showEl("video-summary-content");
  } catch (e) {
    $("video-summary-title").textContent = "Error";
    $("video-summary-text").textContent = e.message;
    $("video-key-points").innerHTML = "";
    $("add-to-note-btn").onclick = null;
    showEl("video-summary-content");
  } finally {
    hideEl("video-summary-loading");
  }
}

function appendSummaryToNote(summary, keyPoints, title) {
  const out = $("corrected-note-output");
  const divider = document.createElement("hr");
  divider.className = "note-divider";
  out.appendChild(divider);

  const block = document.createElement("div");
  block.className = "video-note-block";
  let html = `<div class="sticky-note-label">▶ Video Summary: ${escapeHtml(title || "YouTube Video")}</div>`;
  html += `<p>${escapeHtml(summary || "")}</p>`;
  if (keyPoints && keyPoints.length) {
    html += `<ul>${keyPoints.map(p => `<li>${escapeHtml(p)}</li>`).join("")}</ul>`;
  }
  block.innerHTML = html;
  out.appendChild(block);
  block.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderVerificationResult(data, scoreTextId, scorePctId, scoreFillId, claimsListId) {
  const summary = data.score_summary || {};
  const total = summary.total_claims ?? data.claims?.length ?? 0;
  const decidable = summary.decidable_claims ?? total;
  const correct = summary.correct ?? data.claims?.filter((c) => c.verdict === "correct").length ?? 0;
  const scored = data.overall_score != null && decidable > 0;
  const pct = scored ? Math.round(data.overall_score * 100) : 0;
  $(scoreTextId).textContent = scored
    ? `${correct} / ${decidable} decidable claims correct`
    : "No decidable claims";
  $(scorePctId).textContent = scored ? `${pct}%` : "Not scored";
  $(scoreFillId).style.width = `${pct}%`;
  const wrap = $(scoreTextId).closest(".score-bar-wrap");
  let coverage = wrap.querySelector(".score-coverage");
  if (!coverage) {
    coverage = document.createElement("div");
    coverage.className = "score-coverage";
    wrap.appendChild(coverage);
  }
  coverage.textContent = `${decidable} of ${total} claims could be assessed`;

  const list = $(claimsListId);
  list.innerHTML = "";
  if (!data.claims?.length) {
    list.innerHTML = `<p class="muted-hint">No claims found.</p>`;
    return;
  }
  for (const c of data.claims) {
    list.appendChild(buildClaimCard(c));
  }
}

let evidencePanelSequence = 0;

function claimHighlightTerms(claim) {
  const words = String(claim || "").match(/[\p{L}\p{N}][\p{L}\p{M}\p{N}]*/gu) || [];
  return new Set(
    words
      .filter((word) => Array.from(word).length >= 3)
      .map((word) => word.toLocaleLowerCase()),
  );
}

function appendHighlightedText(container, text, claim) {
  const terms = claimHighlightTerms(claim);
  const pieces = String(text || "").split(/([\p{L}\p{N}][\p{L}\p{M}\p{N}]*)/gu);
  for (const piece of pieces) {
    if (terms.has(piece.toLocaleLowerCase())) {
      const mark = document.createElement("mark");
      mark.textContent = piece;
      container.appendChild(mark);
    } else {
      container.appendChild(document.createTextNode(piece));
    }
  }
}

function safeEvidenceUrl(item) {
  try {
    const url = new URL(String(item?.url || ""), window.location.origin);
    if (item?.source_type === "web") {
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    }
    const isDocumentRoute = url.pathname.startsWith("/api/m4/documents/");
    return url.origin === window.location.origin && isDocumentRoute ? url.href : null;
  } catch {
    return null;
  }
}

function evidenceMetadata(item) {
  const bits = [];
  if (item.source_type === "web") {
    if (item.domain) bits.push(item.domain);
  } else {
    if (item.grade != null) bits.push(`Grade ${item.grade}`);
    if (item.topic) bits.push(item.topic);
    if (item.subtopic && item.subtopic !== item.topic) bits.push(item.subtopic);
    if (item.pdf_page_start != null) {
      const isRange = item.pdf_page_end != null && item.pdf_page_end !== item.pdf_page_start;
      bits.push(isRange
        ? `PDF pages ${item.pdf_page_start}–${item.pdf_page_end}`
        : `PDF page ${item.pdf_page_start}`);
    }
    const score = Number(item.retrieval_score);
    if (Number.isFinite(score)) bits.push(`Similarity ${score.toFixed(3)}`);
    const rerankerScore = Number(item.reranker_score);
    if (Number.isFinite(rerankerScore)) bits.push(`Reranker relevance ${rerankerScore.toFixed(3)}`);
    if (item.retrieval_method) bits.push(String(item.retrieval_method).replaceAll("_", " "));
  }
  return bits.join(" · ");
}

function buildEvidenceItem(item, claim) {
  const card = document.createElement("article");
  card.className = `evidence-item ${item.source_type === "web" ? "web" : "syllabus"}`;

  const heading = document.createElement("div");
  heading.className = "evidence-item-heading";
  const title = document.createElement("strong");
  title.textContent = item.title || "Evidence source";
  heading.appendChild(title);
  const relation = document.createElement("span");
  relation.className = "evidence-relation";
  relation.textContent = item.relation || "context";
  heading.appendChild(relation);
  card.appendChild(heading);

  const metaText = evidenceMetadata(item);
  if (metaText) {
    const meta = document.createElement("div");
    meta.className = "evidence-meta";
    meta.textContent = metaText;
    card.appendChild(meta);
  }

  const excerpt = document.createElement("p");
  excerpt.className = "evidence-excerpt";
  appendHighlightedText(excerpt, item.excerpt || "", claim);
  card.appendChild(excerpt);

  const actions = document.createElement("div");
  actions.className = "evidence-actions";
  if (String(item.excerpt || "").length > 360) {
    excerpt.classList.add("collapsed");
    const expand = document.createElement("button");
    expand.type = "button";
    expand.className = "evidence-text-toggle";
    expand.textContent = "Show full passage";
    expand.addEventListener("click", () => {
      const isCollapsed = excerpt.classList.toggle("collapsed");
      expand.textContent = isCollapsed ? "Show full passage" : "Show less";
    });
    actions.appendChild(expand);
  }

  const sourceUrl = safeEvidenceUrl(item);
  if (sourceUrl) {
    const link = document.createElement("a");
    link.className = "evidence-open-link";
    link.href = sourceUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = item.source_type === "web" ? "Open source ↗" : "Open PDF page ↗";
    actions.appendChild(link);
  }
  if (actions.childNodes.length) card.appendChild(actions);
  return card;
}

function buildEvidencePanel(c, panelId) {
  const panel = document.createElement("section");
  panel.id = panelId;
  panel.className = "claim-evidence-panel";
  panel.hidden = true;

  const items = Array.isArray(c.evidence) ? c.evidence : [];
  if (!items.length) {
    const message = document.createElement("p");
    message.className = "evidence-status-message";
    message.textContent = c.evidence_status === "not_found"
      ? "No relevant syllabus passage was found for this claim."
      : "Exact citation unavailable: the verifier did not select valid evidence.";
    panel.appendChild(message);
    return panel;
  }

  for (const item of items) panel.appendChild(buildEvidenceItem(item, c.claim));
  return panel;
}

function buildConfidence(c) {
  const info = c.confidence;
  if (!info || info.status === "unavailable" || info.level === "unavailable") return null;
  const wrap = document.createElement("div");
  wrap.className = "claim-confidence";
  const label = document.createElement("button");
  label.type = "button";
  label.className = `confidence-badge ${info.level}`;
  label.setAttribute("aria-expanded", "false");
  label.textContent = info.status === "calibrated" && info.probability != null && Number.isFinite(Number(info.probability))
    ? `Confidence: ${Math.round(Number(info.probability) * 100)}% (${info.level})`
    : `Evidence strength: ${info.level} (provisional)`;
  const reasons = document.createElement("ul");
  reasons.className = "confidence-reasons";
  reasons.hidden = true;
  for (const reason of (Array.isArray(info.reasons) ? info.reasons : [])) {
    const item = document.createElement("li");
    item.textContent = reason;
    reasons.appendChild(item);
  }
  label.addEventListener("click", () => {
    reasons.hidden = !reasons.hidden;
    label.setAttribute("aria-expanded", String(!reasons.hidden));
  });
  wrap.append(label, reasons);
  return wrap;
}

function buildClaimCard(c) {
  const icons = {
    correct: "✅", incorrect: "❌", incomplete: "⚠️",
    insufficient_evidence: "❓", verification_failed: "⛔",
  };
  const div = document.createElement("div");
  div.className = `claim-card ${c.verdict}`;
  const correctedHtml = c.corrected_version && c.verdict !== "correct"
    ? `<p class="claim-corrected">→ ${escapeHtml(c.corrected_version)}</p>` : "";
  const sourceCls = c.source === "web" ? "web" : c.source === "none" ? "none" : "syllabus";
  const sourceLabel = c.source === "web" ? "🌐 Web" : c.source === "none" ? "No decision" : "Syllabus";
  const panelId = `claim-evidence-${++evidencePanelSequence}`;
  div.innerHTML = `
    <div class="claim-header">
      <span class="claim-verdict-icon">${icons[c.verdict] ?? "○"}</span>
      <span class="claim-text">${escapeHtml(c.claim)}</span>
    </div>
    <p class="claim-explanation">${escapeHtml(c.explanation || "")}</p>
    ${correctedHtml}
    <div class="claim-footer">
      <button type="button" class="evidence-toggle" aria-expanded="false" aria-controls="${panelId}">Evidence (${Array.isArray(c.evidence) ? c.evidence.length : 0})</button>
      <span class="source-badge ${sourceCls}">${sourceLabel}</span>
    </div>`;
  const panel = buildEvidencePanel(c, panelId);
  const confidence = buildConfidence(c);
  if (confidence) div.insertBefore(confidence, div.querySelector(".claim-footer"));
  div.appendChild(panel);
  const toggle = div.querySelector(".evidence-toggle");
  toggle.addEventListener("click", () => {
    const willOpen = panel.hidden;
    panel.hidden = !willOpen;
    toggle.setAttribute("aria-expanded", String(willOpen));
  });
  return div;
}

function renderCorrections(claims, listId) {
  const list = $(listId);
  list.innerHTML = "";
  const wrong = (claims || []).filter((c) => ["incorrect", "incomplete"].includes(c.verdict));
  if (!wrong.length) {
    list.innerHTML = `<p class="muted-hint">No corrections needed — everything looks good!</p>`;
    return;
  }
  for (const c of wrong) {
    const card = document.createElement("div");
    card.className = "correction-card";
    card.innerHTML = `
      <p class="correction-original">${escapeHtml(c.claim)}</p>
      <p class="correction-fixed">${escapeHtml(c.corrected_version || "—")}</p>
      <p class="correction-explanation">${escapeHtml(c.explanation || "")}</p>
      ${c.memory_tip ? `<span class="memory-tip">💡 ${escapeHtml(c.memory_tip)}</span>` : ""}`;
    list.appendChild(card);
  }
}

/* ══════════════════════════════════════════════════
   SYNTHESIS TAB
══════════════════════════════════════════════════ */
$("btn-synth-all").addEventListener("click", runSynthesis);

async function runSynthesis() {
  const text = $("synth-text").value.trim();
  if (!text) { alert("Please paste some text to synthesise."); return; }
  const lang = $("synth-lang").value;
  $("btn-synth-all").disabled = true;

  $("flashcard-area").innerHTML = `<div class="yt-loading"><div class="spinner"></div><span>Generating flashcards…</span></div>`;
  $("structured-notes-content").innerHTML = `<div class="yt-loading"><div class="spinner"></div><span>Generating notes…</span></div>`;
  mindMapLoading("mindmap-svg", "Generating mind map…");

  try {
    const [flashRes, mmRes, notesRes] = await Promise.allSettled([
      fetchSynth(text, "flashcards", lang),
      fetchSynth(text, "mindmap", lang),
      fetchSynth(text, "notes", lang),
    ]);

    if (flashRes.status === "fulfilled") renderFlashcards(flashRes.value.flashcards, "flashcard-area");
    else $("flashcard-area").innerHTML = `<p class="muted-hint" style="color:var(--danger)">Flashcard error: ${escapeHtml(flashRes.reason?.message)}</p>`;

    if (mmRes.status === "fulfilled") renderMindMap(mmRes.value, "mindmap-svg");
    else mindMapError("mindmap-svg", `Mind map error: ${escapeHtml(mmRes.reason?.message)}`);

    if (notesRes.status === "fulfilled") renderStructuredNotes(notesRes.value, "structured-notes-content");
    else $("structured-notes-content").innerHTML = `<p class="muted-hint" style="color:var(--danger)">Notes error: ${escapeHtml(notesRes.reason?.message)}</p>`;

  } finally {
    $("btn-synth-all").disabled = false;
  }
}

async function fetchSynth(text, mode, language) {
  const r = await fetch(`${API}/api/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, mode, language }),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

/* ══════════════════════════════════════════════════
   FLASHCARDS + SM-2
══════════════════════════════════════════════════ */
function renderFlashcards(flashcards, containerId) {
  const area = $(containerId);
  area.innerHTML = "";
  if (!flashcards?.length) {
    area.innerHTML = `<p class="muted-hint">No flashcards generated.</p>`;
    return;
  }

  let current = 0;
  const state = flashcards.map((fc, i) => ({
    ...fc,
    id: `fc-${containerId}-${i}`,
    easeFactor: 2.5,
    interval: 1,
    repetitions: 0,
    nextReview: null,
  }));

  function build() {
    area.innerHTML = "";

    const counter = document.createElement("p");
    counter.className = "flashcard-counter";
    counter.textContent = `Card ${current + 1} of ${state.length}`;

    const scene = document.createElement("div");
    scene.className = "flashcard-scene";
    scene.setAttribute("aria-label", "Flashcard — click to flip");

    const card = document.createElement("div");
    card.className = "flashcard";

    const front = document.createElement("div");
    front.className = "flashcard-face front";
    front.innerHTML = `<span class="flashcard-label">Question</span>${escapeHtml(state[current].front)}<span class="flashcard-hint">Click to reveal answer</span>`;

    const back = document.createElement("div");
    back.className = "flashcard-face back";
    back.innerHTML = `<span class="flashcard-label">Answer</span>${escapeHtml(state[current].back)}<span class="flashcard-hint">Rate how well you remembered</span>`;

    card.appendChild(front);
    card.appendChild(back);
    scene.appendChild(card);

    let revealed = false;
    scene.addEventListener("click", () => {
      revealed = !revealed;
      card.classList.toggle("flipped", revealed);
      sm2Buttons.style.visibility = revealed ? "visible" : "hidden";
    });

    const sm2Buttons = document.createElement("div");
    sm2Buttons.className = "sm2-buttons";
    sm2Buttons.style.visibility = "hidden";

    const nextReviewLabel = document.createElement("p");
    nextReviewLabel.className = "sm2-next-review";

    [["Again", "again", 0], ["Hard", "hard", 1], ["Easy", "easy", 2]].forEach(([label, cls, quality]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `btn-sm2 ${cls}`;
      btn.textContent = label;
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const result = sm2(state[current], quality);
        Object.assign(state[current], result);
        const days = result.interval;
        const when = days === 1 ? "Tomorrow" : `In ${days} days`;
        nextReviewLabel.textContent = `Next review: ${when}`;
        if (quality === 0) {
          nextReviewLabel.style.color = "var(--danger)";
        } else if (quality === 1) {
          nextReviewLabel.style.color = "var(--warning)";
        } else {
          nextReviewLabel.style.color = "var(--success)";
        }
        setTimeout(() => {
          if (current < state.length - 1) { current++; build(); }
          else {
            area.innerHTML = `<p class="muted-hint" style="color:var(--success); font-weight:600;">🎉 All cards reviewed!</p>`;
          }
        }, 800);
      });
      sm2Buttons.appendChild(btn);
    });

    const nav = document.createElement("div");
    nav.className = "flashcard-nav";
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "btn ghost";
    prevBtn.textContent = "← Prev";
    prevBtn.disabled = current === 0;
    prevBtn.addEventListener("click", () => { if (current > 0) { current--; build(); } });

    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "btn ghost";
    nextBtn.textContent = "Next →";
    nextBtn.disabled = current === state.length - 1;
    nextBtn.addEventListener("click", () => { if (current < state.length - 1) { current++; build(); } });

    nav.appendChild(prevBtn);
    nav.appendChild(document.createTextNode(`${current + 1} / ${state.length}`));
    nav.appendChild(nextBtn);

    area.appendChild(counter);
    area.appendChild(scene);
    area.appendChild(sm2Buttons);
    area.appendChild(nextReviewLabel);
    area.appendChild(nav);
  }

  build();
}

function sm2(card, quality) {
  let { easeFactor = 2.5, interval = 1, repetitions = 0 } = card;
  if (quality < 1) {
    repetitions = 0;
    interval = 1;
  } else {
    if (repetitions === 0) interval = 1;
    else if (repetitions === 1) interval = 6;
    else interval = Math.round(interval * easeFactor);
    easeFactor = Math.max(1.3, easeFactor + 0.1 - (2 - quality) * (0.08 + (2 - quality) * 0.02));
    repetitions++;
  }
  const nextReview = new Date();
  nextReview.setDate(nextReview.getDate() + interval);
  return { easeFactor, interval, repetitions, nextReview };
}

/* ══════════════════════════════════════════════════
   MIND MAP — radial renderer (web/mindmap-render.js)
══════════════════════════════════════════════════ */
const MMR = () => window.MindMapRender;

function zoomLabelId(svgId) { return "mm-zoom"; }
function toolbarIdFor(svgId) { return "mindmap-toolbar"; }

function legendId(svgId) { return "mindmap-legend"; }

const MM_LEGEND_MAX = 8;

function renderMindMapLegend(svgId, legend, hasCrossLinks) {
  const el = $(legendId(svgId));
  if (!el) return;
  if (!legend || !legend.length) { el.innerHTML = ""; el.hidden = true; return; }
  const shown = legend.slice(0, MM_LEGEND_MAX);
  const items = shown.map((b) =>
    `<span class="mm-legend-item"><span class="mm-legend-dot" style="background:${escapeHtml(b.color || "#888")}"></span>${escapeHtml(b.label)}</span>`
  );
  if (legend.length > shown.length) {
    items.push(`<span class="mm-legend-item mm-legend-note">+${legend.length - shown.length} more</span>`);
  }
  if (hasCrossLinks) items.push(`<span class="mm-legend-item mm-legend-note">┈ related concept</span>`);
  el.innerHTML = items.join("");
  el.hidden = false;
}

function mindMapOptions(svgId) {
  return {
    svgId,
    onConceptClick: (label) => sendToQA(`Explain the concept: ${label}`),
    onZoom: (pct) => { const el = $(zoomLabelId(svgId)); if (el) el.textContent = `${pct}%`; },
    onRendered: (info) => {
      $(toolbarIdFor(svgId))?.querySelectorAll("button[data-mm]").forEach((b) => { b.disabled = false; });
      renderMindMapLegend(svgId, info.legend, info.hasCrossLinks);
    },
  };
}

// Disable the toolbar + clear the legend while there is nothing drawn;
// onRendered re-enables them once a map is on screen.
function mindMapChromeIdle(svgId) {
  $(toolbarIdFor(svgId))?.querySelectorAll("button[data-mm]").forEach((b) => { b.disabled = true; });
  const l = $(legendId(svgId));
  if (l) { l.hidden = true; l.innerHTML = ""; }
  const z = $(zoomLabelId(svgId));
  if (z) z.textContent = "100%";
}

function renderMindMap(data, svgId) {
  mindMapChromeIdle(svgId);
  return MMR()?.render(data, mindMapOptions(svgId));
}

function mindMapLoading(svgId, message) {
  mindMapChromeIdle(svgId);
  MMR()?.showLoading({ svgId, message });
}

function mindMapError(svgId, message) {
  mindMapChromeIdle(svgId);
  MMR()?.showError({ svgId }, message);
}

async function runSynthesisMindMap() {
  const text = $("synth-text").value.trim();
  if (!text) { alert("Paste some text to synthesise first."); return; }
  mindMapLoading("mindmap-svg", "Regenerating mind map…");
  try {
    renderMindMap(await fetchSynth(text, "mindmap", $("synth-lang").value), "mindmap-svg");
  } catch (e) {
    mindMapError("mindmap-svg", `Mind map error: ${e.message}`);
  }
}

function toggleMindMapFullscreen(svgId) {
  const wrap = $(svgId)?.closest(".mindmap-container");
  if (!wrap) return;
  if (document.fullscreenElement) document.exitFullscreen();
  else wrap.requestFullscreen?.().then(() => MMR()?.fit(svgId)).catch(() => {});
}

function wireMindMapToolbar(toolbarId, svgId) {
  const bar = $(toolbarId);
  if (!bar) return;
  const on = (name, fn) => bar.querySelector(`[data-mm="${name}"]`)?.addEventListener("click", fn);
  on("fit", () => MMR()?.fit(svgId));
  on("zoom-in", () => MMR()?.zoomBy(1.25, svgId));
  on("zoom-out", () => MMR()?.zoomBy(0.8, svgId));
  on("collapse", () => MMR()?.collapseAll(svgId));
  on("expand", () => MMR()?.expandAll(svgId));
  on("png", () => MMR()?.exportPNG(svgId));
  on("svg", () => MMR()?.exportSVG(svgId));
  on("json", () => MMR()?.exportJSON(svgId));
  on("regen", () => runSynthesisMindMap());
  on("fullscreen", () => toggleMindMapFullscreen(svgId));

  // keyboard: 0 fit · +/- zoom · f fullscreen
  const wrap = $(svgId)?.closest(".mindmap-container");
  wrap?.addEventListener("keydown", (e) => {
    if (e.target !== wrap) return;
    if (e.key === "0") MMR()?.fit(svgId);
    else if (e.key === "+" || e.key === "=") MMR()?.zoomBy(1.25, svgId);
    else if (e.key === "-") MMR()?.zoomBy(0.8, svgId);
    else if (e.key.toLowerCase() === "f") toggleMindMapFullscreen(svgId);
    else return;
    e.preventDefault();
  });
}

wireMindMapToolbar("mindmap-toolbar", "mindmap-svg");

// A map often renders while its sub-tab is display:none — re-fit when shown.
document.querySelectorAll('[data-subtab$="mindmap"]').forEach((btn) => {
  btn.addEventListener("click", () => {
    requestAnimationFrame(() => MMR()?.fit("mindmap-svg"));
  });
});

function sendToQA(question) {
  document.querySelector('[data-tab="qa"]')?.click();
  const input = $("question");
  if (input) { input.value = question; input.focus(); }
  $("btn-ask")?.click();
}

/* ══════════════════════════════════════════════════
   STRUCTURED NOTES
══════════════════════════════════════════════════ */
function renderStructuredNotes(data, containerId) {
  const el = $(containerId);
  el.innerHTML = "";
  if (!data?.sections?.length) {
    el.innerHTML = `<p class="muted-hint">No notes generated.</p>`;
    return;
  }
  for (const section of data.sections) {
    const div = document.createElement("div");
    div.className = "notes-section";
    const bulletsHtml = (section.bullets || [])
      .map((b) => `<li>${escapeHtml(b)}</li>`).join("");
    const termsHtml = (section.key_terms || [])
      .map((t) => `<span class="key-term">${escapeHtml(t)}</span>`).join("");
    div.innerHTML = `
      <p class="notes-heading">${escapeHtml(section.heading || "")}</p>
      <ul class="notes-bullets">${bulletsHtml}</ul>
      ${termsHtml ? `<div class="key-terms">${termsHtml}</div>` : ""}`;
    el.appendChild(div);
  }
}

/* ══════════════════════════════════════════════════
   BOOT
══════════════════════════════════════════════════ */
refreshHealth();
