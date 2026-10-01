initNav("dashboard");

let chartTendencia = null;

async function cargarResumen() {
  try {
    const data = await api("/dashboard/summary");
    document.getElementById("kpi-ventas-dia").textContent = formatoQ(data.ventas_dia);
    document.getElementById("kpi-ventas-mes").textContent = formatoQ(data.ventas_mes);

    const variacion = data.variacion_mes_pct;
    const variacionEl = document.getElementById("kpi-variacion-mes");
    variacionEl.textContent = `${variacion >= 0 ? "+" : ""}${variacion}% vs mes anterior`;
    variacionEl.className = "kpi-delta " + (variacion >= 0 ? "delta-up" : "delta-down");

    document.getElementById("kpi-cantidad-ventas").textContent = data.cantidad_ventas_mes;
    document.getElementById("kpi-ticket").textContent = formatoQ(data.ticket_promedio);
    document.getElementById("kpi-productos-vendidos").textContent = data.productos_vendidos_mes;
    document.getElementById("kpi-stock-bajo").textContent = data.stock_critico;
    document.getElementById("kpi-proyeccion").textContent = formatoQ(data.proyeccion_proximo_mes);
    document.getElementById("kpi-confianza").textContent =
      data.confianza_modelo != null ? `Confianza del modelo: ${data.confianza_modelo}%` : "Modelo aún no entrenado";
  } catch (err) {
    console.error(err);
    showToast("No se pudo cargar el resumen del dashboard.", "error");
  }
}

async function cargarTendencia() {
  try {
    const puntos = await api("/dashboard/trend?meses=12");
    const labels = puntos.map((p) => p.fecha);
    const real = puntos.map((p) => p.real);
    const proyectado = puntos.map((p) => p.proyectado);

    const colors = getUiChartColors();
    chartTendencia = new Chart(document.getElementById("chart-tendencia"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Real", data: real, borderColor: colors.accent, backgroundColor: colors.fill, spanGaps: true, tension: 0.34, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 5, fill: true },
          { label: "Proyectado", data: proyectado, borderColor: colors.secondary, borderDash: [7, 5], spanGaps: true, tension: 0.34, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        animation: { duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700 },
        plugins: { legend: { position: "bottom", align: "start", labels: { color: colors.secondary, usePointStyle: true, boxWidth: 7, padding: 20 } } },
        scales: {
          x: { ticks: { color: colors.muted, maxRotation: 0, maxTicksLimit: 7 }, grid: { display: false }, border: { display: false } },
          y: { ticks: { color: colors.muted, callback: (value) => `Q ${Number(value).toLocaleString("es-GT")}` }, grid: { color: colors.grid }, border: { display: false } },
        },
      },
    });
    document.getElementById("chart-tendencia-frame").classList.add("is-ready");
  } catch (err) {
    console.error(err);
    document.getElementById("chart-tendencia-frame").innerHTML = `<p class="empty-state">${escapeHtml(err.message || "No se pudo cargar la gráfica.")}</p>`;
  }
}

async function cargarRecomendaciones() {
  const contenedor = document.getElementById("lista-recomendaciones");
  if (getRol() !== "admin") {
    contenedor.innerHTML = '<p class="empty-state">Disponible solo para administradores.</p>';
    contenedor.setAttribute("aria-busy", "false");
    return;
  }
  try {
    const recos = await api("/predictions/recommendations");
    if (!recos.length) {
      contenedor.innerHTML = '<p class="empty-state">Sin alertas de reabastecimiento por ahora.</p>';
      return;
    }
    contenedor.innerHTML = recos
      .slice(0, 6)
      .map(
        (r) => `
        <div class="reco-item reco-${escapeHtml(r.urgencia)}">
          <strong>${escapeHtml(r.nombre)}</strong>
          <p>${escapeHtml(r.mensaje)}</p>
          <span>Sugerido: ${escapeHtml(r.cantidad_sugerida)} unidades · Lead time China: ${escapeHtml(r.lead_time_dias_china)} días</span>
        </div>`
      )
      .join("");
  } catch (err) {
    contenedor.innerHTML = `<p class="empty-state">${escapeHtml(err.message)}</p>`;
  } finally {
    contenedor.setAttribute("aria-busy", "false");
  }
}

function actualizarTemaGrafica() {
  if (!chartTendencia) return;
  const colors = getUiChartColors();
  chartTendencia.data.datasets[0].borderColor = colors.accent;
  chartTendencia.data.datasets[0].backgroundColor = colors.fill;
  chartTendencia.data.datasets[1].borderColor = colors.secondary;
  chartTendencia.options.plugins.legend.labels.color = colors.secondary;
  chartTendencia.options.scales.x.ticks.color = colors.muted;
  chartTendencia.options.scales.y.ticks.color = colors.muted;
  chartTendencia.options.scales.y.grid.color = colors.grid;
  chartTendencia.update("none");
}

document.addEventListener("zorros:theme-change", actualizarTemaGrafica);

cargarResumen();
cargarTendencia();
cargarRecomendaciones();
