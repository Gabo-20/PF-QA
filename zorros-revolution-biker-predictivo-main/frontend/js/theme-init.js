(() => {
  let temaGuardado = null;
  try {
    temaGuardado = localStorage.getItem("zorros_theme");
  } catch (error) {
    console.warn("No fue posible leer la preferencia de tema", error);
  }
  if (!['light', 'dark'].includes(temaGuardado)) temaGuardado = null;
  const temaSistema = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  document.documentElement.dataset.theme = temaGuardado || temaSistema;
})();
