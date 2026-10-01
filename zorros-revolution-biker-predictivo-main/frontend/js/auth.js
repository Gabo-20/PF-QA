document.getElementById("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("login-error");
  const boton = document.getElementById("btn-login");
  errorEl.hidden = true;

  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;

  setButtonLoading(boton, true, "Verificando acceso");
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSession(data.access_token, data.rol, data.nombre);
    window.location.href = "/dashboard.html";
  } catch (err) {
    errorEl.textContent = err.message || "No se pudo iniciar sesión";
    errorEl.hidden = false;
    document.getElementById("email").focus();
  } finally {
    setButtonLoading(boton, false);
  }
});
