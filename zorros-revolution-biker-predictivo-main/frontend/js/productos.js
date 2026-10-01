initNav("productos");

let productosCache = [];
let filtroActual = "todo";

async function cargarProductos() {
  const tbody = document.getElementById("tabla-productos");
  try {
    productosCache = await api("/products");
    const stockBajo = await api("/products/stock-bajo");
    const idsStockBajo = new Set(stockBajo.map((p) => p.id));

    document.getElementById("kpi-total-productos").textContent = productosCache.length;
    document.getElementById("kpi-stock-critico").textContent = stockBajo.length;
    document.getElementById("kpi-categorias").textContent = new Set(productosCache.map((p) => p.categoria)).size;

    renderTabla(idsStockBajo);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">${escapeHtml(err.message)}</td></tr>`;
  } finally {
    tbody.setAttribute("aria-busy", "false");
  }
}

function renderTabla(idsStockBajo) {
  const tbody = document.getElementById("tabla-productos");
  let lista = productosCache;
  if (filtroActual === "bajo") lista = lista.filter((p) => idsStockBajo.has(p.id));

  if (!lista.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No hay productos para mostrar.</td></tr>';
    return;
  }

  tbody.innerHTML = lista
    .map((p) => {
      const critico = idsStockBajo.has(p.id);
      return `
      <tr>
        <td data-label="Producto">${escapeHtml(p.nombre)}</td>
        <td data-label="SKU">${escapeHtml(p.sku)}</td>
        <td data-label="Categoría">${escapeHtml(p.categoria)}</td>
        <td data-label="Precio">${formatoQ(p.precio)}</td>
        <td data-label="Stock actual" class="${critico ? "text-danger" : ""}">${escapeHtml(p.stock_actual)} und.</td>
        <td data-label="Lead time China">${escapeHtml(p.lead_time_dias_china)} días</td>
        <td data-label="Estado">${critico ? '<span class="badge badge-critico">Stock bajo</span>' : '<span class="badge badge-ok">Estable</span>'}</td>
      </tr>`;
    })
    .join("");
}

document.querySelectorAll(".filtro-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filtro-btn").forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-pressed", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-pressed", "true");
    filtroActual = btn.dataset.filtro;
    cargarProductos();
  });
});

document.getElementById("btn-recibir-stock").addEventListener("click", () => {
  const select = document.getElementById("stock-producto");
  select.innerHTML = productosCache
    .map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.nombre)} (stock: ${escapeHtml(p.stock_actual)})</option>`)
    .join("");
  document.getElementById("modal-stock").hidden = false;
});
document.getElementById("cerrar-modal-stock").addEventListener("click", () => {
  document.getElementById("modal-stock").hidden = true;
});

document.getElementById("form-stock").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("stock-error");
  const boton = document.getElementById("btn-guardar-stock");
  errorEl.hidden = true;
  setButtonLoading(boton, true, "Registrando stock");
  try {
    await api("/inventory/receive", {
      method: "POST",
      body: JSON.stringify({
        product_id: Number(document.getElementById("stock-producto").value),
        cantidad: Number(document.getElementById("stock-cantidad").value),
        nota: document.getElementById("stock-nota").value,
      }),
    });
    document.getElementById("modal-stock").hidden = true;
    document.getElementById("form-stock").reset();
    await cargarProductos();
    showToast("Recepción de stock registrada.");
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    setButtonLoading(boton, false);
  }
});

const btnNuevoProducto = document.getElementById("btn-nuevo-producto");
if (btnNuevoProducto) {
  btnNuevoProducto.addEventListener("click", () => {
    document.getElementById("modal-producto").hidden = false;
  });
}
document.getElementById("cerrar-modal-producto").addEventListener("click", () => {
  document.getElementById("modal-producto").hidden = true;
});

document.getElementById("form-producto").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("producto-error");
  const boton = document.getElementById("btn-guardar-producto");
  errorEl.hidden = true;
  setButtonLoading(boton, true, "Guardando producto");
  try {
    await api("/products", {
      method: "POST",
      body: JSON.stringify({
        nombre: document.getElementById("prod-nombre").value,
        sku: document.getElementById("prod-sku").value,
        categoria: document.getElementById("prod-categoria").value,
        precio: Number(document.getElementById("prod-precio").value),
        costo: Number(document.getElementById("prod-costo").value),
        stock_actual: Number(document.getElementById("prod-stock").value),
        stock_minimo: Number(document.getElementById("prod-stock-minimo").value),
        lead_time_dias_china: Number(document.getElementById("prod-lead-time").value),
      }),
    });
    document.getElementById("modal-producto").hidden = true;
    document.getElementById("form-producto").reset();
    await cargarProductos();
    showToast("Producto creado correctamente.");
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    setButtonLoading(boton, false);
  }
});

cargarProductos();
