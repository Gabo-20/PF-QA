initNav("ventas");

const LIMITE_RESULTADOS = 12;
let productosCache = [];
let productosPromise = null;
let secuenciaItems = 0;

function normalizarBusqueda(valor) {
  return String(valor || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function cargarProductos(forzar = false) {
  if (forzar) productosPromise = null;
  if (!productosPromise) {
    productosPromise = api("/products")
      .then((productos) => {
        productosCache = productos;
        return productos;
      })
      .catch((error) => {
        productosPromise = null;
        throw error;
      });
  }
  return productosPromise;
}

function obtenerProducto(id) {
  return productosCache.find((producto) => Number(producto.id) === Number(id));
}

function anunciar(mensaje) {
  const region = document.getElementById("venta-status");
  region.textContent = "";
  window.requestAnimationFrame(() => {
    region.textContent = mensaje;
  });
}

function mostrarError(mensaje, campo) {
  const error = document.getElementById("venta-error");
  error.textContent = mensaje;
  error.hidden = false;
  if (campo) {
    campo.setAttribute("aria-invalid", "true");
    campo.focus();
  }
}

function ocultarError() {
  const error = document.getElementById("venta-error");
  error.hidden = true;
  error.textContent = "";
}

function etiquetaProducto(producto) {
  const sku = producto.sku || "Sin SKU";
  const categoria = producto.categoria || "Sin categoría";
  return producto.nombre + " · " + sku + " · " + categoria;
}

function filtrarProductos(termino) {
  const busqueda = normalizarBusqueda(termino);
  if (!busqueda) return productosCache.slice(0, LIMITE_RESULTADOS);
  return productosCache
    .filter((producto) => normalizarBusqueda(etiquetaProducto(producto)).includes(busqueda))
    .slice(0, LIMITE_RESULTADOS);
}

function cerrarLista(fila) {
  const input = fila.querySelector(".item-producto-buscar");
  const lista = fila.querySelector(".combobox-options");
  input.setAttribute("aria-expanded", "false");
  input.removeAttribute("aria-activedescendant");
  lista.hidden = true;
  fila._indiceActivo = -1;
}

function marcarActivo(fila, indice) {
  const resultados = fila._resultados || [];
  const habilitados = resultados
    .map((producto, posicion) => ({ producto, posicion }))
    .filter(({ producto }) => Number(producto.stock_actual) > 0);
  if (!habilitados.length) return;
  const indiceHabilitado = Math.max(0, Math.min(indice, habilitados.length - 1));
  const posicion = habilitados[indiceHabilitado].posicion;
  fila._indiceActivo = posicion;
  const input = fila.querySelector(".item-producto-buscar");
  const opciones = [...fila.querySelectorAll(".combobox-option")];
  opciones.forEach((opcion, actual) => opcion.classList.toggle("is-active", actual === posicion));
  const activa = opciones[posicion];
  input.setAttribute("aria-activedescendant", activa.id);
  activa.scrollIntoView({ block: "nearest" });
}

function indiceHabilitadoActual(fila) {
  const resultados = fila._resultados || [];
  const habilitados = resultados
    .map((producto, posicion) => ({ producto, posicion }))
    .filter(({ producto }) => Number(producto.stock_actual) > 0);
  return habilitados.findIndex(({ posicion }) => posicion === fila._indiceActivo);
}

function renderOpciones(fila) {
  const input = fila.querySelector(".item-producto-buscar");
  const lista = fila.querySelector(".combobox-options");
  const seleccionado = fila.querySelector(".item-producto").value;
  const resultados = filtrarProductos(input.value);
  fila._resultados = resultados;
  fila._indiceActivo = -1;

  if (!resultados.length) {
    lista.innerHTML = '<p class="combobox-empty">No hay coincidencias. Busca por nombre, SKU o categoría.</p>';
  } else {
    lista.innerHTML = resultados.map((producto, indice) => {
      const agotado = Number(producto.stock_actual) <= 0;
      const idOpcion = lista.id + "-option-" + indice;
      const clases = "combobox-option" + (agotado ? " is-disabled" : "");
      return [
        '<div id="', idOpcion, '" class="', clases, '" role="option" data-product-id="',
        escapeHtml(producto.id), '" aria-selected="', String(String(seleccionado) === String(producto.id)),
        '" aria-disabled="', String(agotado), '">',
        '<span class="combobox-option-main"><strong>', escapeHtml(producto.nombre), '</strong><small>',
        escapeHtml(producto.sku || "Sin SKU"), " · ", escapeHtml(producto.categoria || "Sin categoría"),
        '</small></span><span class="combobox-option-stock"><strong>', formatoQ(producto.precio),
        "</strong><small>", agotado ? "Agotado" : "Stock: " + escapeHtml(producto.stock_actual),
        "</small></span></div>",
      ].join("");
    }).join("");
  }
  lista.hidden = false;
  input.setAttribute("aria-expanded", "true");
  input.removeAttribute("aria-activedescendant");
  anunciar(resultados.length ? resultados.length + " productos encontrados." : "Sin productos coincidentes.");
}

function seleccionarProducto(fila, producto) {
  if (!producto || Number(producto.stock_actual) <= 0) return;
  const input = fila.querySelector(".item-producto-buscar");
  const idInput = fila.querySelector(".item-producto");
  const cantidad = fila.querySelector(".item-cantidad");
  input.value = producto.nombre;
  input.dataset.selectedLabel = producto.nombre;
  input.removeAttribute("aria-invalid");
  idInput.value = producto.id;
  cantidad.max = producto.stock_actual;
  if (Number(cantidad.value) > Number(producto.stock_actual)) cantidad.value = producto.stock_actual;
  cerrarLista(fila);
  anunciar(producto.nombre + " seleccionado. Stock disponible: " + producto.stock_actual + ".");
}

function moverActivo(fila, direccion) {
  const resultados = fila._resultados || [];
  const cantidadHabilitada = resultados.filter((producto) => Number(producto.stock_actual) > 0).length;
  if (!cantidadHabilitada) return;
  const actual = indiceHabilitadoActual(fila);
  const siguiente = actual < 0
    ? (direccion > 0 ? 0 : cantidadHabilitada - 1)
    : (actual + direccion + cantidadHabilitada) % cantidadHabilitada;
  marcarActivo(fila, siguiente);
}

function manejarTecladoCombobox(evento, fila) {
  const input = fila.querySelector(".item-producto-buscar");
  const estaAbierto = input.getAttribute("aria-expanded") === "true";
  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(evento.key)) {
    evento.preventDefault();
    if (!estaAbierto) renderOpciones(fila);
    if (evento.key === "Home") marcarActivo(fila, 0);
    else if (evento.key === "End") marcarActivo(fila, Number.MAX_SAFE_INTEGER);
    else moverActivo(fila, evento.key === "ArrowDown" ? 1 : -1);
    return;
  }
  if (evento.key === "Enter" && estaAbierto) {
    evento.preventDefault();
    if (fila._indiceActivo >= 0) seleccionarProducto(fila, fila._resultados[fila._indiceActivo]);
    return;
  }
  if (evento.key === "Escape" && estaAbierto) {
    evento.preventDefault();
    evento.stopPropagation();
    cerrarLista(fila);
    return;
  }
  if (evento.key === "Tab") cerrarLista(fila);
}

function conectarCombobox(fila) {
  const input = fila.querySelector(".item-producto-buscar");
  const lista = fila.querySelector(".combobox-options");
  input.addEventListener("focus", () => renderOpciones(fila));
  input.addEventListener("click", () => renderOpciones(fila));
  input.addEventListener("input", () => {
    fila.querySelector(".item-producto").value = "";
    input.dataset.selectedLabel = "";
    input.removeAttribute("aria-invalid");
    fila.querySelector(".item-cantidad").removeAttribute("max");
    renderOpciones(fila);
  });
  input.addEventListener("keydown", (evento) => manejarTecladoCombobox(evento, fila));
  lista.addEventListener("mousedown", (evento) => evento.preventDefault());
  lista.addEventListener("mousemove", (evento) => {
    const opcion = evento.target.closest(".combobox-option:not(.is-disabled)");
    if (!opcion) return;
    const opciones = [...lista.querySelectorAll(".combobox-option")];
    fila._indiceActivo = opciones.indexOf(opcion);
    opciones.forEach((actual) => actual.classList.toggle("is-active", actual === opcion));
    input.setAttribute("aria-activedescendant", opcion.id);
  });
  lista.addEventListener("click", (evento) => {
    const opcion = evento.target.closest(".combobox-option:not(.is-disabled)");
    if (opcion) seleccionarProducto(fila, obtenerProducto(opcion.dataset.productId));
  });
}

function crearFilaItem() {
  const uid = ++secuenciaItems;
  const fila = document.createElement("div");
  const inputId = "producto-buscar-" + uid;
  const listaId = "producto-opciones-" + uid;
  const cantidadId = "producto-cantidad-" + uid;
  fila.className = "item-venta";
  fila.innerHTML = [
    '<div class="product-combobox"><label class="sr-only" for="', inputId, '">Buscar producto</label>',
    '<div class="combobox-control">', iconSvg("search", "icon combobox-search-icon"),
    '<input id="', inputId, '" type="search" class="item-producto-buscar" placeholder="Buscar nombre, SKU o categoría"',
    ' role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="', listaId,
    '" autocomplete="off" required>', iconSvg("chevron-down", "icon combobox-chevron"), "</div>",
    '<input type="hidden" class="item-producto">',
    '<div id="', listaId, '" class="combobox-options" role="listbox" aria-label="Productos" hidden></div></div>',
    '<div class="quantity-field"><label for="', cantidadId, '">Cantidad</label><input id="',
    cantidadId, '" type="number" class="item-cantidad" min="1" step="1" value="1" required></div>',
    '<button type="button" class="btn-icon quitar-item" aria-label="Quitar producto">',
    iconSvg("trash"), "</button>",
  ].join("");
  conectarCombobox(fila);
  return fila;
}

function agregarItem(enfocar = true) {
  const contenedor = document.getElementById("items-venta");
  const fila = crearFilaItem();
  contenedor.appendChild(fila);
  if (enfocar) fila.querySelector(".item-producto-buscar").focus();
  anunciar("Producto " + contenedor.querySelectorAll(".item-venta").length + " agregado.");
}

function mostrarEstadoCatalogo(tipo, mensaje) {
  const icono = tipo === "error" ? "alert" : (tipo === "loading" ? "refresh" : "search");
  const reintentar = tipo === "error"
    ? '<button type="button" class="btn btn-ghost retry-products">' + iconSvg("refresh") + "<span>Reintentar</span></button>"
    : "";
  document.getElementById("items-venta").innerHTML = [
    '<div class="catalog-state catalog-', tipo, '">', iconSvg(icono, "icon"),
    "<p>", escapeHtml(mensaje), "</p>", reintentar, "</div>",
  ].join("");
}

async function prepararCatalogo(forzar = false) {
  const agregar = document.getElementById("btn-agregar-item");
  agregar.disabled = true;
  mostrarEstadoCatalogo("loading", "Cargando catálogo…");
  try {
    await cargarProductos(forzar);
    document.getElementById("items-venta").innerHTML = "";
    if (!productosCache.length) {
      mostrarEstadoCatalogo("empty", "No hay productos disponibles en el catálogo.");
      return;
    }
    agregar.disabled = false;
    agregarItem();
  } catch (error) {
    mostrarEstadoCatalogo("error", error.message || "No se pudo cargar el catálogo.");
  }
}

document.getElementById("btn-agregar-item").addEventListener("click", () => agregarItem());

document.getElementById("items-venta").addEventListener("click", (evento) => {
  const reintentar = evento.target.closest(".retry-products");
  if (reintentar) {
    prepararCatalogo(true);
    return;
  }
  const boton = evento.target.closest(".quitar-item");
  if (!boton) return;
  const fila = boton.closest(".item-venta");
  const siguiente = fila.nextElementSibling?.querySelector(".item-producto-buscar")
    || fila.previousElementSibling?.querySelector(".item-producto-buscar")
    || document.getElementById("btn-agregar-item");
  fila.remove();
  siguiente.focus();
  anunciar("Producto eliminado de la venta.");
});

document.addEventListener("click", (evento) => {
  document.querySelectorAll(".item-venta").forEach((fila) => {
    if (!fila.contains(evento.target)) cerrarLista(fila);
  });
});

document.getElementById("btn-nueva-venta").addEventListener("click", async () => {
  ocultarError();
  document.getElementById("modal-venta").hidden = false;
  await prepararCatalogo();
});

document.getElementById("btn-cerrar-modal").addEventListener("click", () => {
  document.getElementById("modal-venta").hidden = true;
});

function validarItems() {
  const filas = [...document.querySelectorAll(".item-venta")];
  if (!filas.length) {
    mostrarError("Agrega al menos un producto.", document.getElementById("btn-agregar-item"));
    return null;
  }
  const ids = new Set();
  const items = [];
  for (const fila of filas) {
    const buscador = fila.querySelector(".item-producto-buscar");
    const id = Number(fila.querySelector(".item-producto").value);
    const cantidadInput = fila.querySelector(".item-cantidad");
    const cantidad = Number(cantidadInput.value);
    const producto = obtenerProducto(id);
    if (!producto) {
      mostrarError("Selecciona un producto válido de la lista.", buscador);
      return null;
    }
    if (ids.has(id)) {
      mostrarError("Este producto ya está agregado. Ajusta la cantidad en una sola fila.", buscador);
      return null;
    }
    if (!Number.isInteger(cantidad) || cantidad < 1 || cantidad > Number(producto.stock_actual)) {
      mostrarError("La cantidad de " + producto.nombre + " debe estar entre 1 y " + producto.stock_actual + ".", cantidadInput);
      return null;
    }
    ids.add(id);
    items.push({ product_id: id, cantidad });
  }
  return items;
}

document.getElementById("form-venta").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  ocultarError();
  document.querySelectorAll("[aria-invalid='true']").forEach((campo) => campo.removeAttribute("aria-invalid"));
  const items = validarItems();
  if (!items) return;
  const boton = document.getElementById("btn-registrar-venta");
  setButtonLoading(boton, true, "Registrando venta");
  try {
    await api("/sales", {
      method: "POST",
      body: JSON.stringify({
        metodo_pago: document.getElementById("metodo-pago").value,
        canal: "Tienda",
        items,
      }),
    });
    document.getElementById("modal-venta").hidden = true;
    await cargarVentas();
    cargarProductos(true).catch(() => {});
    showToast("Venta registrada correctamente.");
  } catch (error) {
    mostrarError(error.message);
  } finally {
    setButtonLoading(boton, false);
  }
});

async function cargarVentas() {
  const tbody = document.getElementById("tabla-ventas");
  try {
    const ventas = await api("/sales?limit=100");
    if (!ventas.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Aún no hay ventas registradas.</td></tr>';
      return;
    }
    tbody.innerHTML = ventas.map((venta) => [
      "<tr><td data-label=\"Número\">#", escapeHtml(venta.id), "</td>",
      '<td data-label="Fecha">', escapeHtml(new Date(venta.fecha_hora).toLocaleString("es-GT")), "</td>",
      '<td data-label="Cajero">', escapeHtml(venta.cajero_nombre), "</td>",
      '<td data-label="Productos">', venta.items.map((item) => escapeHtml(item.cantidad) + "× " + escapeHtml(item.producto_nombre)).join(", "), "</td>",
      '<td data-label="Total">', formatoQ(venta.total), "</td>",
      '<td data-label="Pago">', escapeHtml(venta.metodo_pago), "</td></tr>",
    ].join("")).join("");
  } catch (error) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">' + escapeHtml(error.message) + "</td></tr>";
  } finally {
    tbody.setAttribute("aria-busy", "false");
  }
}

cargarProductos().catch(() => {});
cargarVentas();
