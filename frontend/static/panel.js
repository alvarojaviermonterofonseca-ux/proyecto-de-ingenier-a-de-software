import { ACTIONS, RESOURCES, createAccessControl } from "./rbac.js";

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
  const accessDenied = document.querySelector("#access-denied");
  const rbacNotice = document.querySelector("#rbac-notice");
  const roles = [];
  let token = sessionStorage.getItem(tokenKey);
  let tokenType = "Bearer";
  let currentUser = null;
  let accessControl = null;
  let loadedRows = [];

  const can = (resource, action) => accessControl?.can(currentUser, resource, action) === true;

  function setLoginMessage(message) {
    loginMessage.textContent = message;
  }

  function showLogin(message = "") {
    loginView.hidden = false;
    appView.hidden = true;
    setLoginMessage(message);
  }

  function showApp(user) {
    currentUser = user;
    loginView.hidden = true;
    appView.hidden = false;
    const roleNames = accessControl.assignedRoles(user)
      .map((name) => roles.find((role) => role.nombre === name)?.nombre || name)
      .join(", ");
    document.querySelector("#user-label").textContent =
      roleNames ? `${user.nombre} · ${roleNames}` : user.nombre;
    renderPermissionControls();
    renderRoleOptions();
    renderRoleEditor();
    rbacNotice.hidden = true;
    if (accessControl.warnings.length) {
      rbacNotice.textContent = accessControl.warnings.join(" ");
      rbacNotice.hidden = false;
    }
  }

  function clearToken() {
    token = null;
    tokenType = "Bearer";
    currentUser = null;
    accessControl = null;
    roles.splice(0, roles.length);
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
    if (data && typeof data === "object" && !Array.isArray(data)) {
      const validationErrors = Object.values(data).flat().filter((value) => typeof value === "string");
      if (validationErrors.length) {
        return validationErrors.join(" ");
      }
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

  function requirePermission(resource, action) {
    if (can(resource, action)) {
      return true;
    }
    accessDenied.hidden = false;
    accessDenied.querySelector("a").focus();
    return false;
  }

  function renderPermissionControls() {
    document.querySelectorAll("[data-permission]").forEach((element) => {
      const [resource, action] = element.dataset.permission.split(":");
      element.hidden = !can(resource, action);
    });
    document.querySelector("#create-user-shortcut").hidden =
      !can(RESOURCES.users, "view") || !can(RESOURCES.users, "create");
    document.querySelectorAll("#resource-select option").forEach((option) => {
      option.hidden = !can(option.value, "view");
    });
    document.querySelector("#export-button").disabled = !can(resourceSelect.value, "export");
    const selectedOption = resourceSelect.selectedOptions[0];
    if (!selectedOption || selectedOption.hidden) {
      const firstAllowed = [...resourceSelect.options].find((option) => !option.hidden);
      if (firstAllowed) {
        resourceSelect.value = firstAllowed.value;
      }
    }
  }

  function setPageLinks(data) {
    previousButton.dataset.url = data.previous || "";
    nextButton.dataset.url = data.next || "";
    previousButton.disabled = !data.previous;
    nextButton.disabled = !data.next;
  }

  async function loadResource(url = `/api/v1/${resourceSelect.value}/`) {
    const resource = resourceSelect.value;
    resourceHeading.textContent = resourceSelect.selectedOptions[0]?.textContent || "Datos";
    document.querySelector("#export-button").disabled = !can(resource, "export");
    resourceMessage.textContent = "Cargando...";
    resourceData.textContent = "";
    loadedRows = [];
    setPageLinks({});
    if (!requirePermission(resource, "view")) {
      resourceMessage.textContent = "Acceso denegado: no tienes permiso para consultar este recurso.";
      return;
    }

    try {
      const data = await apiRequest(url);
      loadedRows = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
      resourceData.textContent = JSON.stringify(loadedRows.length ? loadedRows : data, null, 2);
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

  function fillSelect(select, selectedNames = []) {
    select.replaceChildren();
    roles.filter((role) => role.is_active !== false).forEach((role) => {
      const option = document.createElement("option");
      option.value = role.nombre;
      option.textContent = role.nombre;
      option.selected = selectedNames.includes(role.nombre);
      select.append(option);
    });
  }

  function renderRoleOptions() {
    const primaryRoleSelect = document.querySelector("#new-user-primary-role");
    primaryRoleSelect.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Selecciona un rol";
    placeholder.disabled = true;
    placeholder.selected = true;
    primaryRoleSelect.append(placeholder);
    roles.filter((role) => role.is_active !== false).forEach((role) => {
      const option = document.createElement("option");
      option.value = role.nombre;
      option.textContent = role.nombre;
      primaryRoleSelect.append(option);
    });
    fillSelect(document.querySelector("#new-user-roles"));
    const editorSelect = document.querySelector("#role-select");
    const previousRole = editorSelect.value;
    fillSelect(editorSelect, [previousRole || ""]);
    renderRoleEditor();
  }

  function renderRoleEditor() {
    const roleName = document.querySelector("#role-select").value;
    const role = roles.find((entry) => entry.nombre === roleName);
    const permissionMatrix = document.querySelector("#permission-matrix");
    const form = document.querySelector("#role-form");
    permissionMatrix.replaceChildren();
    if (!role) {
      form.hidden = true;
      return;
    }
    form.hidden = false;
    document.querySelector("#role-description").value = role.descripcion || "";
    const grants = accessControl.permissionsFor(roleName);
    Object.values(RESOURCES).forEach((resource) => {
      const row = document.createElement("fieldset");
      row.className = "permission-row";
      const legend = document.createElement("legend");
      legend.textContent = resource;
      row.append(legend);
      ACTIONS.forEach((action) => {
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.name = `${resource}:${action}`;
        checkbox.checked = grants[resource]?.includes(action) === true;
        checkbox.dataset.resource = resource;
        checkbox.dataset.action = action;
        label.append(checkbox, document.createTextNode(action));
        row.append(label);
      });
      permissionMatrix.append(row);
    });
    form.querySelectorAll("input").forEach((input) => {
      input.disabled = !can(RESOURCES.roles, "edit");
    });
  }

  function roleId(name) {
    return roles.find((role) => role.nombre === name)?.id;
  }

  async function loadUsers() {
    const message = document.querySelector("#users-message");
    const table = document.querySelector("#users-table");
    if (!requirePermission(RESOURCES.users, "view")) {
      message.textContent = "No tienes permiso para consultar usuarios.";
      return;
    }
    message.textContent = "Cargando usuarios...";
    table.replaceChildren();
    try {
      const data = await apiRequest("/api/v1/usuarios/");
      const users = Array.isArray(data?.results) ? data.results : data;
      users.forEach((user) => table.append(renderUserRow(user)));
      message.textContent = `${users.length} usuarios cargados.`;
    } catch (error) {
      message.textContent = `No se pudieron cargar los usuarios: ${error.message}`;
    }
  }

  function renderUserRow(user) {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.maxLength = 150;
    nameInput.required = true;
    nameInput.value = user.nombre;
    nameInput.setAttribute("aria-label", `Nombre de ${user.nombre}`);
    nameCell.append(nameInput);
    const emailCell = document.createElement("td");
    const emailInput = document.createElement("input");
    emailInput.type = "email";
    emailInput.required = true;
    emailInput.value = user.correo;
    emailInput.setAttribute("aria-label", `Correo de ${user.nombre}`);
    emailCell.append(emailInput);
    const rolesCell = document.createElement("td");
    const roleSelect = document.createElement("select");
    roleSelect.multiple = true;
    roleSelect.setAttribute("aria-label", `Roles para ${user.nombre}`);
    fillSelect(roleSelect, accessControl.assignedRoles(user));
    const primaryRole = user.rol_detalle?.nombre || user.rol_nombre;
    [...roleSelect.options].forEach((option) => {
      if (option.value === primaryRole) {
        option.disabled = true;
      }
    });
    rolesCell.append(roleSelect);
    const stateCell = document.createElement("td");
    stateCell.textContent = user.is_active ? "Activo" : "Inactivo";
    const actionCell = document.createElement("td");
    const saveDetails = document.createElement("button");
    saveDetails.type = "button";
    saveDetails.className = "secondary-button";
    saveDetails.textContent = "Guardar datos";
    saveDetails.hidden = !can(RESOURCES.users, "edit");
    saveDetails.addEventListener("click", async () => {
      if (!requirePermission(RESOURCES.users, "edit")) {
        return;
      }
      if (!nameInput.reportValidity() || !emailInput.reportValidity()) {
        return;
      }
      saveDetails.disabled = true;
      try {
        await apiRequest(`/api/v1/usuarios/${user.id}/`, {
          method: "PATCH",
          body: JSON.stringify({ nombre: nameInput.value, correo: emailInput.value }),
        });
        document.querySelector("#users-message").textContent = "Datos de usuario actualizados.";
        await loadUsers();
      } catch (error) {
        document.querySelector("#users-message").textContent = `No se pudieron guardar los datos: ${error.message}`;
        saveDetails.disabled = false;
      }
    });
    actionCell.append(saveDetails);
    const saveRoles = document.createElement("button");
    saveRoles.type = "button";
    saveRoles.className = "secondary-button";
    saveRoles.textContent = "Guardar roles";
    saveRoles.hidden = !can(RESOURCES.users, "edit");
    saveRoles.addEventListener("click", async () => {
      if (!requirePermission(RESOURCES.users, "edit")) {
        return;
      }
      const selectedRoleIds = [...roleSelect.selectedOptions]
        .map((option) => roleId(option.value))
        .filter((id) => Number.isInteger(id));
      saveRoles.disabled = true;
      try {
        await apiRequest(`/api/v1/usuarios/${user.id}/roles/`, {
          method: "PATCH",
          body: JSON.stringify({ roles: selectedRoleIds }),
        });
        document.querySelector("#users-message").textContent =
          "Roles del usuario actualizados en la base de datos.";
        await loadUsers();
      } catch (error) {
        document.querySelector("#users-message").textContent = `No se pudieron guardar los roles: ${error.message}`;
        saveRoles.disabled = false;
      }
    });
    actionCell.append(saveRoles);
    if (user.is_active && can(RESOURCES.users, "edit")) {
      const deactivate = document.createElement("button");
      deactivate.type = "button";
      deactivate.className = "secondary-button";
      deactivate.textContent = "Desactivar";
      deactivate.addEventListener("click", async () => {
        if (!requirePermission(RESOURCES.users, "edit")) {
          return;
        }
        deactivate.disabled = true;
        try {
          await apiRequest(`/api/v1/usuarios/${user.id}/`, {
            method: "PATCH",
            body: JSON.stringify({ is_active: false }),
          });
          await loadUsers();
        } catch (error) {
          document.querySelector("#users-message").textContent = `No se pudo desactivar: ${error.message}`;
          deactivate.disabled = false;
        }
      });
      actionCell.append(deactivate);
    }
    row.append(nameCell, emailCell, rolesCell, stateCell, actionCell);
    return row;
  }

  async function refreshRoles() {
    const latestRoles = await apiRequest("/api/v1/roles/");
    roles.splice(0, roles.length, ...(Array.isArray(latestRoles?.results) ? latestRoles.results : latestRoles));
    accessControl = createAccessControl(roles);
    if (currentUser) {
      currentUser = await apiRequest("/api/v1/me/");
    }
    return roles;
  }

  async function loadRoles() {
    const message = document.querySelector("#roles-message");
    if (!requirePermission(RESOURCES.roles, "view")) {
      message.textContent = "No tienes permiso para consultar roles.";
      return;
    }
    message.textContent = "Cargando roles...";
    try {
      await refreshRoles();
      showApp(currentUser);
      message.textContent = `${roles.length} roles y sus permisos cargados desde la base de datos.`;
    } catch (error) {
      message.textContent = `No se pudieron cargar los roles: ${error.message}`;
    }
  }

  function setRoute() {
    const routeName = window.location.hash.slice(1) || "datos";
    const route = document.querySelector(`[data-route="${CSS.escape(routeName)}"]`);
    accessDenied.hidden = true;
    document.querySelectorAll("[data-route-link]").forEach((link) => {
      if (link.dataset.routeLink === routeName) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
    document.querySelectorAll(".route-view").forEach((section) => {
      section.hidden = section !== route;
    });
    if (!route) {
      accessDenied.hidden = false;
      return;
    }
    const routePermission = {
      usuarios: [RESOURCES.users, "view"],
      roles: [RESOURCES.roles, "view"],
    }[routeName];
    if (routePermission && !requirePermission(...routePermission)) {
      route.hidden = true;
      return;
    }
    if (routeName === "usuarios") {
      loadUsers();
    } else if (routeName === "roles") {
      renderRoleEditor();
    } else {
      renderPermissionControls();
      loadResource();
    }
  }

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginButton.disabled = true;
    setLoginMessage("");
    const formData = new FormData(loginForm);

    try {
      const response = await fetch("/api/v1/login/", {
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
      if (!data?.token || !data?.usuario) {
        throw new Error("El servidor no devolvió una sesión válida.");
      }

      token = data.token;
      tokenType = data.tipo_token || "Bearer";
      sessionStorage.setItem(tokenKey, token);
      loginForm.reset();
      roles.splice(0, roles.length);
      currentUser = data.usuario;
      accessControl = createAccessControl([]);
      if (can(RESOURCES.roles, "view")) {
        await refreshRoles();
      }
      showApp(currentUser);
      window.location.hash = "datos";
      setRoute();
    } catch (error) {
      setLoginMessage(error.message || "No se pudo iniciar sesión.");
    } finally {
      loginButton.disabled = false;
    }
  });

  document.querySelector("#logout-button").addEventListener("click", async () => {
    try {
      await apiRequest("/api/v1/logout/", { method: "POST", body: "{}" });
      clearToken();
      showLogin("Sesión cerrada.");
    } catch (error) {
      resourceMessage.textContent = `No se pudo cerrar la sesión: ${error.message}`;
    }
  });

  resourceSelect.addEventListener("change", () => loadResource());
  document.querySelector("#refresh-button").addEventListener("click", () => loadResource());
  document.querySelector("#create-user-shortcut").addEventListener("click", () => {
    if (!requirePermission(RESOURCES.users, "create")) {
      return;
    }
    window.location.hash = "usuarios";
  });
  document.querySelector("#export-button").addEventListener("click", () => {
    if (!requirePermission(resourceSelect.value, "export")) {
      return;
    }
    const blob = new Blob([JSON.stringify(loadedRows, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${resourceSelect.value}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  });
  previousButton.addEventListener("click", () => loadResource(previousButton.dataset.url));
  nextButton.addEventListener("click", () => loadResource(nextButton.dataset.url));
  window.addEventListener("hashchange", setRoute);
  document.querySelector("#users-refresh").addEventListener("click", loadUsers);
  document.querySelector("#roles-refresh").addEventListener("click", loadRoles);
  document.querySelector("#role-select").addEventListener("change", renderRoleEditor);

  document.querySelector("#user-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const message = document.querySelector("#users-message");
    if (!requirePermission(RESOURCES.users, "create")) {
      return;
    }
    if (!form.reportValidity()) {
      return;
    }
    const formData = new FormData(form);
    const primaryRoleName = document.querySelector("#new-user-primary-role").value;
    if (!primaryRoleName) {
      message.textContent = "Selecciona un rol principal.";
      return;
    }
    const additionalRoleNames = [...document.querySelector("#new-user-roles").selectedOptions]
      .map((option) => option.value)
      .filter((name) => name !== primaryRoleName);
    const rolesAsignados = additionalRoleNames
      .map((name) => roleId(name))
      .filter((id) => Number.isInteger(id));
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    message.textContent = "Creando usuario...";
    try {
      await apiRequest("/api/v1/usuarios/", {
        method: "POST",
        body: JSON.stringify({
          rol: roleId(primaryRoleName),
          roles_asignados: rolesAsignados,
          nombre: formData.get("nombre"),
          correo: formData.get("correo"),
          contrasena: formData.get("contrasena"),
          perfil: {},
        }),
      });
      form.reset();
      message.textContent = "Usuario creado con su rol principal y roles adicionales en la base de datos.";
      await loadUsers();
    } catch (error) {
      message.textContent = `No se pudo crear el usuario: ${error.message}`;
    } finally {
      submitButton.disabled = false;
    }
  });

  document.querySelector("#role-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#roles-message");
    if (!requirePermission(RESOURCES.roles, "edit")) {
      message.textContent = "No tienes permiso para modificar roles.";
      return;
    }
    const role = roles.find((entry) => entry.nombre === document.querySelector("#role-select").value);
    if (!role) {
      message.textContent = "Selecciona un rol válido.";
      return;
    }
    const button = event.currentTarget.querySelector('button[type="submit"]');
    const permissions = [...event.currentTarget.querySelectorAll(
      "#permission-matrix input[type=checkbox]:checked",
    )].map((checkbox) => `${checkbox.dataset.resource}:${checkbox.dataset.action}`);
    button.disabled = true;
    message.textContent = "Guardando rol y permisos...";
    try {
      await apiRequest(`/api/v1/roles/${role.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ descripcion: document.querySelector("#role-description").value }),
      });
      await apiRequest(`/api/v1/roles/${role.id}/permisos/`, {
        method: "PUT",
        body: JSON.stringify({ permisos: permissions }),
      });
      await refreshRoles();
      showApp(currentUser);
      message.textContent = "Rol y permisos guardados en la base de datos.";
      renderPermissionControls();
      setRoute();
    } catch (error) {
      message.textContent = `No se pudieron guardar los cambios: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });

  if (token) {
    apiRequest("/api/v1/me/")
      .then(async (user) => {
        currentUser = user;
        accessControl = createAccessControl([]);
        if (can(RESOURCES.roles, "view")) {
          await refreshRoles();
        }
        showApp(currentUser);
        setRoute();
      })
      .catch((error) => {
        clearToken();
        showLogin(error.message || "No se pudo recuperar la sesión.");
      });
  } else {
    showLogin();
  }
})();
