const ICONS_PATH = "/assets/icons.svg";

function iconSvg(nombre, clase = "icon") {
  return `<svg class="${clase}" aria-hidden="true"><use href="${ICONS_PATH}#icon-${nombre}"></use></svg>`;
}

function setButtonLoading(boton, cargando, texto = "Procesando") {
  if (!boton) return;
  if (cargando) {
    boton.dataset.originalContent = boton.innerHTML;
    boton.disabled = true;
    boton.setAttribute("aria-busy", "true");
    boton.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>${escapeHtml(texto)}</span>`;
    return;
  }
  boton.disabled = false;
  boton.removeAttribute("aria-busy");
  boton.innerHTML = boton.dataset.originalContent || boton.innerHTML;
  delete boton.dataset.originalContent;
}

function showToast(mensaje, tipo = "success") {
  const region = document.getElementById("toast-region");
  if (!region) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${tipo}`;
  toast.setAttribute("role", tipo === "error" ? "alert" : "status");
  toast.innerHTML = `${iconSvg(tipo === "error" ? "alert" : "check")}<span>${escapeHtml(mensaje)}</span>`;
  region.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("toast-out");
    window.setTimeout(() => toast.remove(), 220);
  }, 4200);
}

let ultimoFoco = null;

function abrirDialogo(modal) {
  ultimoFoco = document.activeElement;
  document.body.classList.add("modal-open");
  window.requestAnimationFrame(() => {
    const objetivo = modal.querySelector("[autofocus]") ||
      modal.querySelector("input:not([type='hidden']), select, textarea") ||
      modal.querySelector("button");
    objetivo?.focus();
  });
}

function cerrarDialogo(modal) {
  if (document.querySelectorAll(".modal-overlay:not([hidden])").length <= 1) {
    document.body.classList.remove("modal-open");
  }
  ultimoFoco?.focus?.();
}

function atraparFoco(evento, modal) {
  const selectores = "button:not([disabled]), input:not([disabled]):not([type='hidden']), select:not([disabled]), textarea:not([disabled]), a[href]";
  const elementos = [...modal.querySelectorAll(selectores)].filter((el) => !el.hidden);
  if (!elementos.length) return;
  const primero = elementos[0];
  const ultimo = elementos[elementos.length - 1];
  if (evento.shiftKey && document.activeElement === primero) {
    evento.preventDefault();
    ultimo.focus();
  } else if (!evento.shiftKey && document.activeElement === ultimo) {
    evento.preventDefault();
    primero.focus();
  }
}

function cerrarModalVisible(modal) {
  const botonCerrar = modal.querySelector("[data-modal-close], .modal-header .btn-icon");
  botonCerrar?.click();
}

function initModales() {
  document.querySelectorAll(".modal-overlay").forEach((modal) => {
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    new MutationObserver(() => (modal.hidden ? cerrarDialogo(modal) : abrirDialogo(modal)))
      .observe(modal, { attributes: true, attributeFilter: ["hidden"] });
    modal.addEventListener("click", (evento) => {
      if (evento.target === modal) cerrarModalVisible(modal);
    });
  });

  document.addEventListener("keydown", (evento) => {
    const modal = document.querySelector(".modal-overlay:not([hidden])");
    if (!modal) return;
    if (evento.key === "Escape") cerrarModalVisible(modal);
    if (evento.key === "Tab") atraparFoco(evento, modal);
  });
}

function initPasswordToggles() {
  document.querySelectorAll("[data-password-toggle]").forEach((boton) => {
    boton.addEventListener("click", () => {
      const input = document.getElementById(boton.dataset.passwordToggle);
      const visible = input.type === "text";
      input.type = visible ? "password" : "text";
      boton.innerHTML = iconSvg(visible ? "eye" : "eye-off");
      boton.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
    });
  });
}

function actualizarBotonTema(boton, tema) {
  const esClaro = tema === "light";
  boton.innerHTML = iconSvg(esClaro ? "moon" : "sun");
  boton.setAttribute("aria-label", esClaro ? "Activar modo oscuro" : "Activar modo claro");
  boton.title = esClaro ? "Modo oscuro" : "Modo claro";
}

function actualizarMetaTema(tema) {
  document.documentElement.style.colorScheme = tema;
  document.querySelector('meta[name="theme-color"]')?.setAttribute(
    "content",
    tema === "light" ? "#f1ede6" : "#0a0a09"
  );
}

function getUiChartColors() {
  const estilos = getComputedStyle(document.documentElement);
  const color = (token) => estilos.getPropertyValue(token).trim();
  return {
    accent: color("--accent"),
    secondary: color("--chart-secondary"),
    muted: color("--chart-muted"),
    grid: color("--chart-grid"),
    fill: color("--chart-fill"),
  };
}

function initTema() {
  const botones = document.querySelectorAll("[data-theme-toggle]");
  const temaActual = document.documentElement.dataset.theme || "dark";
  actualizarMetaTema(temaActual);
  botones.forEach((boton) => {
    actualizarBotonTema(boton, temaActual);
    boton.addEventListener("click", () => {
      const nuevoTema = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = nuevoTema;
      try {
        localStorage.setItem("zorros_theme", nuevoTema);
      } catch (error) {
        console.warn("No fue posible guardar la preferencia de tema", error);
      }
      actualizarMetaTema(nuevoTema);
      botones.forEach((control) => actualizarBotonTema(control, nuevoTema));
      document.dispatchEvent(new CustomEvent("zorros:theme-change", { detail: { tema: nuevoTema } }));
    });
  });
  window.addEventListener("storage", (evento) => {
    if (evento.key !== "zorros_theme" || !["light", "dark"].includes(evento.newValue)) return;
    document.documentElement.dataset.theme = evento.newValue;
    actualizarMetaTema(evento.newValue);
    botones.forEach((control) => actualizarBotonTema(control, evento.newValue));
    document.dispatchEvent(new CustomEvent("zorros:theme-change", { detail: { tema: evento.newValue } }));
  });
}

function initCacheEstatico() {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" })
      .catch((error) => console.warn("Cache no disponible", error));
  });
}

function initUi() {
  const region = document.createElement("div");
  region.id = "toast-region";
  region.className = "toast-region";
  region.setAttribute("aria-live", "polite");
  document.body.appendChild(region);
  initModales();
  initPasswordToggles();
  initTema();
  initCacheEstatico();
  window.requestAnimationFrame(() => document.body.classList.add("ui-ready"));
}

initUi();
