initNav("predicciones");

if (getRol() !== "admin") {
  window.location.href = "/dashboard.html";
}

let chartInstancia = null;

const EVENTOS_GT = [
  { nombre: "Caravana del Zorro", mes: 2, dia: 14 },
  { nombre: "Bono 14", mes: 7, dia: 1 },
  { nombre: "Diciembre / Aguinaldo", mes: 12, dia: 1 },
];

function proximoEvento() {
  const hoy = new Date();
  let mejor = null;
  for (const ev of EVENTOS_GT) {
    let fecha = new Date(hoy.getFullYear(), ev.mes - 1, ev.dia);
    if (fecha < hoy) fecha = new Date(hoy.getFullYear() + 1, ev.mes - 1, ev.dia);
    const dias = Math.ceil((fecha - hoy) / (1000 * 60 * 60 * 24));
    if (!mejor || dias < mejor.dias) mejor = { nombre: ev.nombre, dias };
  }
  return mejor;
}

async function cargarPronostico() {
  const horizonte = document.getElementById("horizonte").value;
  const frame = document.getElementById("chart-pronostico-frame");
  frame.classList.remove("is-ready");
  try {
    const puntos = await api(`/predictions/forecast?horizonte=${horizonte}`);
    const labels = puntos.map((p) => p.fecha);
    const real = puntos.map((p) => p.real);
    const pronostico = puntos.map((p) => p.pronostico);

    const total = puntos.reduce((acc, p) => acc + (p.pronostico || 0), 0);
    document.getElementById("kpi-volumen-proyectado").textContent = formatoQ(total);

    if (chartInstancia) chartInstancia.destroy();
    const colors = getUiChartColors();
    chartInstancia = new Chart(document.getElementById("chart-pronostico"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Histórico real", data: real, borderColor: colors.secondary, backgroundColor: "transparent", spanGaps: true, tension: 0.34, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5 },
          { label: "Predicción IA", data: pronostico, borderColor: colors.accent, backgroundColor: colors.fill, spanGaps: true, tension: 0.34, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 5, fill: true },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        animation: { duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700 },
        plugins: { legend: { position: "bottom", align: "start", labels: { color: colors.secondary, usePointStyle: true, boxWidth: 7, padding: 20 } } },
        scales: {
          x: { ticks: { color: colors.muted, maxTicksLimit: 10, maxRotation: 0 }, grid: { display: false }, border: { display: false } },
          y: { ticks: { color: colors.muted, callback: (value) => `Q ${Number(value).toLocaleString("es-GT")}` }, grid: { color: colors.grid }, border: { display: false } },
        },
      },
    });
    frame.classList.add("is-ready");
  } catch (err) {
    console.error(err);
    frame.innerHTML = `<p class="empty-state">${escapeHtml(err.message || "No se pudo cargar el pronóstico.")}</p>`;
  }
}

async function cargarSenales() {
  const contenedor = document.getElementById("lista-senales");
  try {
    const senales = await api("/predictions/signals");
    if (!senales.length) {
      contenedor.innerHTML = '<p class="empty-state">Sin variaciones relevantes esta semana.</p>';
      return;
    }
    contenedor.innerHTML = senales
      .map(
        (s) => `
      <div class="reco-item">
        <span class="badge ${s.tendencia === "alta_demanda" ? "badge-alta" : "badge-baja"}">
          ${s.tendencia === "alta_demanda" ? "ALTA DEMANDA" : "BAJA DEMANDA"}
        </span>
        <strong>${escapeHtml(s.nombre)}</strong>
        <p>Categoría: ${escapeHtml(s.categoria)}</p>
        <span>${s.magnitud_pct > 0 ? "+" : ""}${escapeHtml(s.magnitud_pct)}% vs. periodo anterior</span>
      </div>`
      )
      .join("");
  } catch (err) {
    contenedor.innerHTML = `<p class="empty-state">${escapeHtml(err.message)}</p>`;
  } finally {
    contenedor.setAttribute("aria-busy", "false");
  }
}

async function cargarRecomendaciones() {
  const contenedor = document.getElementById("lista-recos");
  try {
    const recos = await api("/predictions/recommendations");
    if (!recos.length) {
      contenedor.innerHTML = '<p class="empty-state">No hay alertas de reabastecimiento.</p>';
      return;
    }
    contenedor.innerHTML = recos
      .map(
        (r) => `
      <div class="reco-item reco-${escapeHtml(r.urgencia)}">
        <strong>${escapeHtml(r.nombre)} <small>(${escapeHtml(r.sku)})</small></strong>
        <p>${escapeHtml(r.mensaje)}</p>
        <span>Stock actual: ${escapeHtml(r.stock_actual)} · Sugerido: ${escapeHtml(r.cantidad_sugerida)} und. · Lead time: ${escapeHtml(r.lead_time_dias_china)} días</span>
      </div>`
      )
      .join("");
  } catch (err) {
    contenedor.innerHTML = `<p class="empty-state">${escapeHtml(err.message)}</p>`;
  } finally {
    contenedor.setAttribute("aria-busy", "false");
  }
}

function mostrarProximoEvento() {
  const ev = proximoEvento();
  document.getElementById("kpi-proximo-evento").textContent = `${ev.nombre} (${ev.dias} días)`;
}

function formatoFechaCorta(iso) {
  if (!iso) return "";
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return "";
  return fecha.toLocaleDateString("es-GT", { day: "2-digit", month: "short", year: "numeric" });
}

function pintarEstadoModelo(estado) {
  const valor = document.getElementById("kpi-ultimo-modelo");
  const detalle = document.getElementById("kpi-metricas");
  const fecha = formatoFechaCorta(estado.fecha);
  if (estado.publicado) {
    valor.textContent = estado.algoritmo;
    detalle.textContent =
      `${fecha ? `${fecha} · ` : ""}MASE: ${estado.mase} · WAPE: ${estado.wape}% · Mejora vs. base: ${estado.mejora_vs_baseline_pct}%`;
    return;
  }
  valor.textContent = "No publicado";
  detalle.textContent = `${fecha ? `${fecha} · ` : ""}${estado.motivo || "El candidato no superó la referencia"}`;
}

async function cargarEstadoModelo() {
  try {
    const estado = await api("/predictions/model");
    if (estado.entrenado) pintarEstadoModelo(estado);
  } catch (err) {
    console.warn("No se pudo consultar el último entrenamiento:", err.message);
  }
}

document.getElementById("btn-recalibrar").addEventListener("click", async () => {
  const boton = document.getElementById("btn-recalibrar");
  setButtonLoading(boton, true, "Entrenando modelo");
  try {
    const resultado = await api("/predictions/retrain", { method: "POST" });
    pintarEstadoModelo({ ...resultado, fecha: new Date().toISOString() });
    await cargarPronostico();
    await cargarRecomendaciones();
    showToast("Modelo recalibrado correctamente.");
  } catch (err) {
    showToast(`No se pudo recalibrar: ${err.message}`, "error");
  } finally {
    setButtonLoading(boton, false);
  }
});

function actualizarTemaGrafica() {
  if (!chartInstancia) return;
  const colors = getUiChartColors();
  chartInstancia.data.datasets[0].borderColor = colors.secondary;
  chartInstancia.data.datasets[1].borderColor = colors.accent;
  chartInstancia.data.datasets[1].backgroundColor = colors.fill;
  chartInstancia.options.plugins.legend.labels.color = colors.secondary;
  chartInstancia.options.scales.x.ticks.color = colors.muted;
  chartInstancia.options.scales.y.ticks.color = colors.muted;
  chartInstancia.options.scales.y.grid.color = colors.grid;
  chartInstancia.update("none");
}

document.addEventListener("zorros:theme-change", actualizarTemaGrafica);
document.getElementById("horizonte").addEventListener("change", cargarPronostico);

cargarPronostico();
cargarEstadoModelo();
cargarSenales();
cargarRecomendaciones();
mostrarProximoEvento();
