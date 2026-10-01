const API_BASE = ""; // mismo origen: FastAPI sirve tanto la API como este frontend

function getToken() {
  return localStorage.getItem("zorros_token");
}

function getRol() {
  return localStorage.getItem("zorros_rol");
}

function getNombre() {
  return localStorage.getItem("zorros_nombre");
}

function setSession(token, rol, nombre) {
  localStorage.setItem("zorros_token", token);
  localStorage.setItem("zorros_rol", rol);
  localStorage.setItem("zorros_nombre", nombre);
}

function clearSession() {
  localStorage.removeItem("zorros_token");
  localStorage.removeItem("zorros_rol");
  localStorage.removeItem("zorros_nombre");
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(API_BASE + path, { ...options, cache: "no-store", headers });

  if (response.status === 401) {
    clearSession();
    window.location.href = "/index.html";
    throw new Error("Sesión expirada");
  }

  if (!response.ok) {
    let detail = "Ocurrió un error";
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch (e) {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

function requireAuth() {
  const token = getToken();
  if (!token) {
    window.location.href = "/index.html";
  }
}

const ENTIDADES_HTML = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

// Escapa datos del servidor antes de interpolarlos en plantillas de innerHTML.
// Sin esto, un nombre de producto con `<img onerror=...>` ejecuta código con la
// sesión del usuario (el token vive en localStorage).
function escapeHtml(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ENTIDADES_HTML[c]);
}

function formatoQ(valor) {
  const num = Number(valor || 0);
  return "Q " + num.toLocaleString("es-GT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function initNav(paginaActual) {
  requireAuth();
  const rol = getRol();

  document.querySelectorAll("[data-nav]").forEach((el) => {
    const activo = el.dataset.nav === paginaActual;
    el.classList.toggle("active", activo);
    if (activo) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });

  document.querySelectorAll("[data-roles]").forEach((el) => {
    const roles = el.dataset.roles.split(",");
    if (!roles.includes(rol)) el.style.display = "none";
  });

  document.querySelectorAll(".topbar-actions").forEach((contenedor) => {
    const visibles = [...contenedor.children].filter((el) => el.style.display !== "none");
    contenedor.classList.toggle("is-single-action", visibles.length === 1);
  });

  const nombreEl = document.getElementById("nombre-usuario");
  const nombre = getNombre() || "Usuario";
  if (nombreEl) nombreEl.textContent = nombre;

  const inicialEl = document.getElementById("user-initial");
  if (inicialEl) inicialEl.textContent = nombre.trim().charAt(0).toUpperCase() || "Z";

  const rolEl = document.getElementById("rol-usuario");
  if (rolEl) rolEl.textContent = rol === "admin" ? "Administrador" : "Cajero";

  const logoutBtn = document.getElementById("btn-logout");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      clearSession();
      window.location.href = "/index.html";
    });
  }
}
