const API = "";

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

async function refreshStatus() {
  const pill = $("health-pill");
  try {
    const r = await fetch(`${API}/api/narrative-learning/status`);
    const j = await r.json();
    pill.textContent = j.status === "ready" ? "Ready" : "Unavailable";
    pill.className = j.status === "ready" ? "health-pill ok" : "health-pill bad";
  } catch {
    pill.textContent = "API offline";
    pill.className = "health-pill bad";
  }
}

async function loadChapters() {
  const r = await fetch(`${API}/api/narrative-learning/chapters`);
  if (!r.ok) throw new Error("Could not load chapters");
  const data = await r.json();
  const books = data.books || {};
  const bookSel = $("book");
  bookSel.innerHTML = "";
  Object.keys(books).forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    bookSel.appendChild(opt);
  });
  bookSel.dataset.chapters = JSON.stringify(books);
  fillTopics();
}

function fillTopics() {
  const bookSel = $("book");
  const books = JSON.parse(bookSel.dataset.chapters || "{}");
  const topics = books[bookSel.value] || [];
  const topicSel = $("topic");
  topicSel.innerHTML = "";
  topics.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    topicSel.appendChild(opt);
  });
}

function renderIntro(intro) {
  if (!intro || !Object.keys(intro).length) {
    $("tell-block").innerHTML = "";
    return;
  }
  let html = "";
  if (intro.concept_statement) {
    html += `<div class="card-note"><strong>The concept</strong>${escapeHtml(intro.concept_statement)}</div>`;
  }
  if (intro.explanation) {
    html += `<div class="card-note why"><strong>Why it works</strong>${escapeHtml(intro.explanation)}</div>`;
  }
  if (intro.equations && intro.equations.length) {
    html += `<div class="card-note eq"><strong>Key equations</strong>${intro.equations.map((e) => `<code>${escapeHtml(e)}</code>`).join(" &nbsp; ")}</div>`;
  }
  if (intro.real_world_note) {
    html += `<div class="card-note world"><strong>Real world</strong>${escapeHtml(intro.real_world_note)}</div>`;
  }
  $("tell-block").innerHTML = html;
}

function renderStudy(data) {
  const eqs = data.key_equations || [];
  const defs = data.key_definitions || [];
  const bullets = data.exam_bullets || [];
  let html = "";
  if (eqs.length) {
    html += `<p class="field-label">Equations</p>`;
    eqs.forEach((eq) => {
      html += `<div class="study-item"><div class="step-cap">${escapeHtml(eq.label || "")}</div><code>${escapeHtml(eq.equation || "")}</code></div>`;
    });
  }
  if (defs.length) {
    html += `<p class="field-label">Definitions</p>`;
    defs.forEach((d) => {
      html += `<div class="study-item"><strong>${escapeHtml(d.term || "")}</strong><div>${escapeHtml(d.definition || "")}</div></div>`;
    });
  }
  if (bullets.length) {
    html += `<p class="field-label">What to write in the exam</p>`;
    bullets.forEach((b, i) => {
      html += `<div class="study-item"><b>${i + 1}.</b> ${escapeHtml(b)}</div>`;
    });
  }
  $("study-block").innerHTML = html || `<p class="step-cap">Study notes will appear here.</p>`;
}

function renderSources(sources) {
  const el = $("sources-block");
  if (!sources || !sources.length) {
    el.innerHTML = `<p class="step-cap">No textbook passages attached.</p>`;
    return;
  }
  el.innerHTML = sources.map((s) => {
    const title = [s.filename, s.chapter].filter(Boolean).join(" · ");
    const meta = [`p. ${s.page || "?"}`, s.similarity || ""].filter(Boolean).join(" · ");
    return `<div class="source-card"><strong>${escapeHtml(title)}</strong><div class="step-cap">${escapeHtml(meta)}</div><div>${escapeHtml(s.snippet || "")}</div></div>`;
  }).join("");
}

async function generateStory() {
  const btn = $("btn-generate");
  const err = $("error-box");
  err.classList.add("hidden");
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "Writing…";
  $("results").classList.add("hidden");

  const body = {
    interest: $("interest").value,
    aspiration: $("aspiration").value,
    struggle_level: $("struggle").value,
    book: $("book").value,
    topic: $("topic").value,
    diagnostic: $("diagnostic").value.trim() || "Explain the core concept in simple terms.",
  };

  try {
    const r = await fetch(`${API}/api/narrative-learning/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || r.statusText);

    $("theme-pill").textContent = `Theme: ${data.theme || "—"}`;
    renderIntro(data.science_intro || {});
    $("story-box").textContent = data.story || "";
    renderStudy(data);
    renderSources(data.sources || []);
    const quizTopic = encodeURIComponent(data.quiz_topic || body.topic);
    $("quiz-link").href = `/adaptive-quiz?topic=${quizTopic}`;
    $("results").classList.remove("hidden");
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    err.textContent = e.message || "Story generation failed.";
    err.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate personalized story";
  }
}

$("book").addEventListener("change", fillTopics);
$("btn-generate").addEventListener("click", generateStory);

refreshStatus();
loadChapters().catch((e) => {
  $("error-box").textContent = e.message;
  $("error-box").classList.remove("hidden");
});
