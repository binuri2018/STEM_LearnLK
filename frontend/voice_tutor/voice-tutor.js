/* ==========================================================
   STEM Learn LK - Voice Tutor JS
   ========================================================== */

const API = "";

const $ = (id) => document.getElementById(id);

/* ──────────────────────────────────────────────────────────
   HEALTH CHECK
   ────────────────────────────────────────────────────────── */

async function refreshHealth() {
  const pill = $("health-pill");
  try {
    const r = await fetch(`${API}/api/health`);
    const j = await r.json();
    const label = j.index_loaded
      ? j.openai_configured ? "Index ready · OpenAI on" : "Index ready · Ollama"
      : "No index — run ingest.py";
    const cls = j.index_loaded ? "health-pill ok" : "health-pill bad";
    if (pill) {
      pill.textContent = label;
      pill.className = cls;
    }
  } catch {
    if (pill) {
      pill.textContent = "API unreachable";
      pill.className = "health-pill bad";
    }
  }
}

/* ──────────────────────────────────────────────────────────
   VOICE TUTOR — ASK & ANSWER
   ────────────────────────────────────────────────────────── */

function renderSources(items) {
  const el = $("sources");
  if (!el) return;
  el.innerHTML = "";
  if (!items.length) {
    el.innerHTML = "<p class=\"source-meta\">No chunks retrieved.</p>";
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
        ? `pp. ${s.page_start}-${s.page_end}` : `p. ${s.page_start}`);
    if (s.score != null) bits.push(`sim. ${s.score.toFixed(3)}`);
    card.innerHTML = `<strong>${escapeHtml(title)}</strong><div class="source-meta">${escapeHtml(bits.join(" · "))}</div>`;
    el.appendChild(card);
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function renderImages(items) {
  const el = $("textbook-images");
  if (!el) return;
  el.innerHTML = "";
  if (!items || !items.length) {
    el.hidden = true;
    return;
  }
  const heading = document.createElement("h2");
  heading.className = "section-title sources-title";
  heading.textContent = "Textbook Figures";
  el.appendChild(heading);

  const grid = document.createElement("div");
  grid.className = "figures-grid";
  for (const img of items) {
    const card = document.createElement("figure");
    card.className = "figure-card";

    const imgEl = document.createElement("img");
    imgEl.className = "figure-img";
    imgEl.src = img.url;
    imgEl.alt = img.caption || `Textbook figure — p.${img.page}`;
    imgEl.loading = "lazy";
    imgEl.onerror = () => { card.hidden = true; };

    const caption = document.createElement("figcaption");
    caption.className = "figure-caption";
    const capText = img.caption || "";
    const meta = `${img.source ? escapeHtml(img.source.replace(/\.pdf$/i, "")) : ""}  ·  p. ${img.page}`;
    caption.innerHTML = capText
      ? `<span class="cap-text">${escapeHtml(capText)}</span><span class="cap-meta">${escapeHtml(meta)}</span>`
      : `<span class="cap-meta">${escapeHtml(meta)}</span>`;

    card.appendChild(imgEl);
    card.appendChild(caption);
    grid.appendChild(card);
  }
  el.appendChild(grid);
  el.hidden = false;
}

function renderVisualExplanation(visual) {
  const el = $("visual-explanation");
  if (!el) return;
  el.innerHTML = "";
  if (!visual || !visual.image_url) {
    el.hidden = true;
    return;
  }

  const heading = document.createElement("h2");
  heading.className = "section-title sources-title";
  heading.textContent = "Visual Explanation (Internet)";
  el.appendChild(heading);

  const card = document.createElement("div");
  card.className = "visual-card";

  const imgWrapper = document.createElement("div");
  imgWrapper.className = "visual-img-wrap";

  const img = document.createElement("img");
  img.className = "visual-img";
  img.src = visual.image_url;
  img.alt = visual.title || "Visual explanation diagram";
  img.loading = "lazy";
  img.onerror = () => { el.hidden = true; };

  img.addEventListener("click", () => {
    window.open(visual.image_url, "_blank");
  });

  imgWrapper.appendChild(img);

  const metaBox = document.createElement("div");
  metaBox.className = "visual-meta-box";

  const titleEl = document.createElement("div");
  titleEl.className = "visual-title";
  titleEl.textContent = visual.title || "Educational Diagram";

  const confidenceScore = visual.relevance_score ? `${Math.round(visual.relevance_score * 100)}% relevant` : "Verified";
  const badge = document.createElement("span");
  badge.className = "visual-badge";
  badge.textContent = confidenceScore;
  titleEl.appendChild(badge);

  const attrEl = document.createElement("div");
  attrEl.className = "visual-attr";
  const sourceName = escapeHtml(visual.source_name || "Online Resource");
  if (visual.source_url) {
    attrEl.innerHTML = `Source: <a href="${escapeHtml(visual.source_url)}" target="_blank" rel="noopener noreferrer">${sourceName}</a>`;
  } else {
    attrEl.textContent = `Source: ${sourceName}`;
  }

  metaBox.appendChild(titleEl);
  metaBox.appendChild(attrEl);

  card.appendChild(imgWrapper);
  card.appendChild(metaBox);
  el.appendChild(card);
  el.hidden = false;
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
  answerEl.textContent = "Thinking...";
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
    renderImages(data.images || []);
    renderVisualExplanation(data.visual || null);
    $("btn-tts").disabled = !data.answer;
    window.__lastAnswer = data.answer;
    window.__ttsLang = lang;
  } catch (e) {
    answerEl.textContent = `Error: ${e.message}`;
    answerEl.classList.add("muted");
    renderSources([]);
    renderImages([]);
    renderVisualExplanation(null);
  } finally {
    btn.disabled = false;
  }
}

/* ──────────────────────────────────────────────────────────
   VOICE INPUT (Whisper Transcription)
   ────────────────────────────────────────────────────────── */

let mediaRecorder = null;
let chunks = [];

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
    chunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btn.classList.remove("recording");
      label.textContent = "Voice input";
      const blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
      await sendTranscribe(blob);
    };
    mediaRecorder.start();
    btn.classList.add("recording");
    label.textContent = "Stop...";
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
      alert("Whisper needs OPENAI_API_KEY on the server. Type your question or enable the key.");
      return;
    }
    if (!r.ok) throw new Error(await r.text());
    const j = await r.json();
    $("question").value = (j.text || "").trim();
  } catch (e) {
    alert(`Transcription failed: ${e.message}`);
  }
}

/* ──────────────────────────────────────────────────────────
   TTS (Text-to-Speech)
   ────────────────────────────────────────────────────────── */

function browserTts(text, langMode) {
  const u = new SpeechSynthesisUtterance(text);
  if (langMode === "si") u.lang = "si-LK";
  else if (langMode === "en") u.lang = "en-US";
  else {
    const hasSinhala = /[\u0D80-\u0DFF]/.test(text);
    u.lang = hasSinhala ? "si-LK" : "en-US";
  }
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

/* ──────────────────────────────────────────────────────────
   EVENT LISTENERS & INIT
   ────────────────────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  const btnAsk = $("btn-ask");
  const btnMic = $("btn-mic");
  const btnTts = $("btn-tts");
  const questionEl = $("question");

  if (btnAsk) btnAsk.addEventListener("click", ask);
  if (btnMic) btnMic.addEventListener("click", toggleMic);
  if (btnTts) btnTts.addEventListener("click", playTts);
  if (questionEl) {
    questionEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask();
    });
  }

  refreshHealth();
});
