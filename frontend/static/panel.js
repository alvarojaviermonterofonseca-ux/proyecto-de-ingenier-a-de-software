(() => {
  const tokenKey = "gym-control-api-token";
  const loginView = document.querySelector("#login-view");
  const appView = document.querySelector("#app-view");
  const loginForm = document.querySelector("#login-form");
  const loginButton = document.querySelector("#login-button");
  const loginMessage = document.querySelector("#login-message");
  const resourceSelect = document.querySelector("#resource-select");
  const resourceHeading = document.querySelector("#resource-heading");
  const resourceMessage = document.querySelector("#resource-message");
  const resourceData = document.querySelector("#resource-data");
  const previousButton = document.querySelector("#previous-button");
  const nextButton = document.querySelector("#next-button");
  let token = sessionStorage.getItem(tokenKey);
  let tokenType = "Bearer";

  function setLoginMessage(message) {
    loginMessage.textContent = message;
  }

  function showLogin(message = "") {
    loginView.hidden = false;
    appView.hidden = true;
    setLoginMessage(message);
  }

  function showApp(user) {
    loginView.hidden = true;
    appView.hidden = false;
    const role = user.rol_detalle?.nombre;
    document.querySelector("#user-label").textContent =
      role ? `${user.nombre} · ${role}` : user.nombre;
  }

  function clearToken() {
    token = null;
    tokenType = "Bearer";
    sessionStorage.removeItem(tokenKey);
  }

  function errorMessage(data, fallback) {
    if (typeof data?.error?.detalles === "string") {
      return data.error.detalles;
    }
    if (typeof data?.detail === "string") {
      return data.detail;
    }
    if (typeof data?.error?.mensaje === "string") {
      return data.error.mensaje;
    }
    if (data?.error?.detalles && typeof data.error.detalles === "object") {
      return Object.values(data.error.detalles).flat().join(" ");
    }
    return fallback;
  }

  async function apiRequest(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (token) {
      headers.set("Authorization", `${tokenType} ${token}`);
    }
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(url, { ...options, headers });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const message = errorMessage(data, `Error HTTP ${response.status}`);
      if (response.status === 401) {
        clearToken();
        showLogin("La sesión expiró o no es válida. Inicia sesión nuevamente.");
      }
      throw new Error(message);
    }
    return data;
  }

  function setPageLinks(data) {
    previousButton.dataset.url = data.previous || "";
    nextButton.dataset.url = data.next || "";
    previousButton.disabled = !data.previous;
    nextButton.disabled = !data.next;
  }

  async function loadResource(url = `/api/${resourceSelect.value}/`) {
    resourceHeading.textContent =
      resourceSelect.selectedOptions[0]?.textContent || "Datos";
    resourceMessage.textContent = "Cargando...";
    resourceData.textContent = "";
    setPageLinks({});

    try {
      const data = await apiRequest(url);
      const rows = Array.isArray(data?.results) ? data.results : data;
      resourceData.textContent = JSON.stringify(rows, null, 2);
      resourceMessage.textContent = Array.isArray(data?.results)
        ? `${data.count} registros`
        : Array.isArray(data)
          ? `${data.length} registros`
          : "Datos cargados";
      setPageLinks(data);
    } catch (error) {
      resourceMessage.textContent = error.message;
      resourceData.textContent = "No se pudieron cargar los registros.";
    }
  }

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginButton.disabled = true;
    setLoginMessage("");
    const formData = new FormData(loginForm);

    try {
      const response = await fetch("/api/login/", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({
          correo: formData.get("correo"),
          contrasena: formData.get("contrasena"),
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(errorMessage(data, `Error HTTP ${response.status}`));
      }
      if (!data?.token) {
        throw new Error("El servidor inició sesión pero no devolvió un token.");
      }

      token = data.token;
      tokenType = data.tipo_token || "Bearer";
      sessionStorage.setItem(tokenKey, token);
      loginForm.reset();
      showApp(data.usuario);
      await loadResource();
    } catch (error) {
      setLoginMessage(error.message || "No se pudo iniciar sesión.");
    } finally {
      loginButton.disabled = false;
    }
  });

  document.querySelector("#logout-button").addEventListener("click", async () => {
    try {
      await apiRequest("/api/logout/", { method: "POST", body: "{}" });
      clearToken();
      showLogin("Sesión cerrada.");
    } catch (error) {
      resourceMessage.textContent = `No se pudo cerrar la sesión: ${error.message}`;
    }
  });

  resourceSelect.addEventListener("change", () => loadResource());
  document.querySelector("#refresh-button").addEventListener("click", () => loadResource());
  previousButton.addEventListener("click", () => loadResource(previousButton.dataset.url));
  nextButton.addEventListener("click", () => loadResource(nextButton.dataset.url));

  if (token) {
    apiRequest("/api/me/")
      .then((user) => {
        showApp(user);
        return loadResource();
      })
      .catch(() => clearToken());
  } else {
    showLogin();
  }
})();
