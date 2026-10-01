initNav("usuarios");

if (getRol() !== "admin") {
  window.location.href = "/dashboard.html";
}

let usuariosCache = [];
let miId = null;

function mostrarAviso(mensaje) {
  const el = document.getElementById("aviso");
  el.textContent = mensaje;
  el.hidden = !mensaje;
}

function abrir(id) {
  document.getElementById(id).hidden = false;
}

function cerrar(id) {
  document.getElementById(id).hidden = true;
  const error = document.querySelector(`#${id} .form-error`);
  if (error) error.hidden = true;
}

async function cargarUsuarios() {
  mostrarAviso("");
  try {
    const [yo, usuarios] = await Promise.all([api("/auth/me"), api("/users")]);
    miId = yo.id;
    usuariosCache = usuarios;

    document.getElementById("kpi-total").textContent = usuarios.length;
    document.getElementById("kpi-admins").textContent = usuarios.filter((u) => u.rol === "admin" && u.activo).length;
    document.getElementById("kpi-inactivos").textContent = usuarios.filter((u) => !u.activo).length;

    renderTabla();
  } catch (err) {
    document.getElementById("tabla-usuarios").innerHTML =
      `<tr><td colspan="5" class="empty-state">${escapeHtml(err.message)}</td></tr>`;
  } finally {
    document.getElementById("tabla-usuarios").setAttribute("aria-busy", "false");
  }
}

function renderTabla() {
  const tbody = document.getElementById("tabla-usuarios");
  if (!usuariosCache.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No hay usuarios registrados.</td></tr>';
    return;
  }

  tbody.innerHTML = usuariosCache
    .map((u) => {
      const soyYo = u.id === miId;
      const etiqueta = u.rol === "admin" ? "Administrador" : "Cajero";
      const estado = u.activo
        ? '<span class="badge badge-ok">Activo</span>'
        : '<span class="badge badge-critico">Inactivo</span>';
      return `
      <tr>
        <td data-label="Nombre">${escapeHtml(u.nombre)}${soyYo ? ' <small class="kpi-label">(tú)</small>' : ""}</td>
        <td data-label="Correo">${escapeHtml(u.email)}</td>
        <td data-label="Rol">${escapeHtml(etiqueta)}</td>
        <td data-label="Estado">${estado}</td>
        <td data-label="Acciones"><div class="table-actions">
          <button class="btn btn-ghost accion" data-accion="rol" data-id="${escapeHtml(u.id)}">
            ${iconSvg("shield", "icon icon-sm")}<span>${u.rol === "admin" ? "Hacer cajero" : "Hacer admin"}</span>
          </button>
          <button class="btn btn-ghost ${u.activo ? "btn-danger" : ""} accion" data-accion="estado" data-id="${escapeHtml(u.id)}">
            ${iconSvg(u.activo ? "close" : "check", "icon icon-sm")}<span>${u.activo ? "Desactivar" : "Activar"}</span>
          </button>
          <button class="btn btn-ghost accion" data-accion="password" data-id="${escapeHtml(u.id)}">
            ${iconSvg("key", "icon icon-sm")}<span>Restablecer clave</span>
          </button>
        </div></td>
      </tr>`;
    })
    .join("");
}

document.getElementById("tabla-usuarios").addEventListener("click", async (e) => {
  const boton = e.target.closest(".accion");
  if (!boton) return;

  const id = Number(boton.dataset.id);
  const usuario = usuariosCache.find((u) => u.id === id);
  if (!usuario) return;

  if (boton.dataset.accion === "password") {
    document.getElementById("reset-destino").textContent = usuario.email;
    document.getElementById("form-reset").dataset.id = id;
    document.getElementById("reset-password").value = "";
    abrir("modal-reset");
    return;
  }

  setButtonLoading(boton, true, "Actualizando");
  mostrarAviso("");
  try {
    if (boton.dataset.accion === "rol") {
      const nuevo = usuario.rol === "admin" ? "cajero" : "admin";
      await api(`/users/${id}/rol`, { method: "PUT", body: JSON.stringify({ rol: nuevo }) });
    } else {
      await api(`/users/${id}/estado`, { method: "PUT", body: JSON.stringify({ activo: !usuario.activo }) });
    }
    await cargarUsuarios();
  } catch (err) {
    mostrarAviso(err.message);
  } finally {
    setButtonLoading(boton, false);
  }
});

// ---------- Nuevo usuario ----------
document.getElementById("btn-nuevo-usuario").addEventListener("click", () => {
  document.getElementById("form-usuario").reset();
  abrir("modal-usuario");
});
document.getElementById("cerrar-modal-usuario").addEventListener("click", () => cerrar("modal-usuario"));

document.getElementById("form-usuario").addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("usuario-error");
  const boton = document.getElementById("btn-crear-usuario");
  error.hidden = true;
  setButtonLoading(boton, true, "Creando usuario");
  try {
    await api("/users", {
      method: "POST",
      body: JSON.stringify({
        nombre: document.getElementById("u-nombre").value.trim(),
        email: document.getElementById("u-email").value.trim(),
        rol: document.getElementById("u-rol").value,
        password: document.getElementById("u-password").value,
      }),
    });
    cerrar("modal-usuario");
    await cargarUsuarios();
    showToast("Usuario creado correctamente.");
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    setButtonLoading(boton, false);
  }
});

// ---------- Restablecer contraseña de otro ----------
document.getElementById("cerrar-modal-reset").addEventListener("click", () => cerrar("modal-reset"));

document.getElementById("form-reset").addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("reset-error");
  const boton = document.getElementById("btn-restablecer-password");
  error.hidden = true;
  setButtonLoading(boton, true, "Restableciendo");
  try {
    const id = e.target.dataset.id;
    await api(`/users/${id}/password`, {
      method: "PUT",
      body: JSON.stringify({ password_nueva: document.getElementById("reset-password").value }),
    });
    cerrar("modal-reset");
    showToast("Contraseña restablecida correctamente.");
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    setButtonLoading(boton, false);
  }
});

// ---------- Cambiar la propia ----------
document.getElementById("btn-mi-password").addEventListener("click", () => {
  document.getElementById("form-mi-password").reset();
  abrir("modal-mi-password");
});
document.getElementById("cerrar-modal-mi-password").addEventListener("click", () => cerrar("modal-mi-password"));

document.getElementById("form-mi-password").addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("mi-password-error");
  const boton = document.getElementById("btn-cambiar-password");
  error.hidden = true;
  setButtonLoading(boton, true, "Actualizando clave");
  try {
    await api("/auth/me/password", {
      method: "PUT",
      body: JSON.stringify({
        password_actual: document.getElementById("mi-actual").value,
        password_nueva: document.getElementById("mi-nueva").value,
      }),
    });
    cerrar("modal-mi-password");
    showToast("Tu contraseña se cambió correctamente.");
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    setButtonLoading(boton, false);
  }
});

cargarUsuarios();
