/* ==========================================================
   STEM Learn LK - Home JS
   ========================================================== */

const API = "";

async function refreshHomeHealth() {
  const pillHome = document.getElementById("health-pill-home");
  if (!pillHome) return;

  try {
    const r = await fetch(`${API}/api/health`);
    const j = await r.json();
    pillHome.textContent = j.index_loaded ? "Ready" : "No index";
    pillHome.className = j.index_loaded ? "stat-value" : "stat-value bad";
  } catch {
    pillHome.textContent = "Offline";
  }
}

// Initial health check on page load
document.addEventListener("DOMContentLoaded", refreshHomeHealth);
