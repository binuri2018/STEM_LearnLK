const API = "";

const $ = (id) => document.getElementById(id);

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

function renderSources(items) {
  const el = $("sources");
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
      bits.push(s.page_end != null && s.page_end !== s.page_start ? `pp. ${s.page_start}–${s.page_end}` : `p. ${s.page_start}`);
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

/** ----- Voice input (Whisper) ----- */
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
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btn.classList.remove("recording");
      label.textContent = "Voice input";
      const blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
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

/** ----- TTS ----- */
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
  } catch {
    /* fall through */
  }
  browserTts(text, lang);
}

$("btn-ask").addEventListener("click", ask);
$("btn-mic").addEventListener("click", toggleMic);
$("btn-tts").addEventListener("click", playTts);
$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask();
});

refreshHealth();
