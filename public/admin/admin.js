const loginView = document.querySelector("[data-login-view]");
const dashboard = document.querySelector("[data-dashboard]");
const loginForm = document.querySelector("[data-login-form]");
const loginStatus = document.querySelector("[data-login-status]");
const logoutButton = document.querySelector("[data-logout]");
const refreshButton = document.querySelector("[data-refresh]");
const searchInput = document.querySelector("[data-user-search]");
const usersTable = document.querySelector("[data-users-table]");
const usersBody = document.querySelector("[data-users-body]");
const loadingState = document.querySelector("[data-loading]");
const emptyState = document.querySelector("[data-empty]");
const notice = document.querySelector("[data-admin-notice]");
const totalUsers = document.querySelector("[data-total-users]");
const activeUsers = document.querySelector("[data-active-users]");
const deleteModal = document.querySelector("[data-delete-modal]");
const deleteUsername = document.querySelector("[data-delete-username]");
const deleteConfirm = document.querySelector("[data-delete-confirm]");
const deleteSubmit = document.querySelector("[data-delete-submit]");
const deleteStatus = document.querySelector("[data-delete-status]");

let csrfToken = "";
let users = [];
let selectedUsername = "";
let deleteTrigger = null;

const api = async (url, options = {}) => {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.error?.message || "Не удалось выполнить запрос.");
    error.status = response.status;
    throw error;
  }
  return payload;
};

const showLogin = (message = "") => {
  csrfToken = "";
  users = [];
  loginView.hidden = false;
  dashboard.hidden = true;
  logoutButton.hidden = true;
  if (loginStatus) loginStatus.textContent = message;
  window.setTimeout(() => loginForm?.elements.namedItem("password")?.focus(), 0);
};

const showDashboard = () => {
  loginView.hidden = true;
  dashboard.hidden = false;
  logoutButton.hidden = false;
};

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};

const cell = (label, className = "") => {
  const element = document.createElement("td");
  element.dataset.label = label;
  if (className) element.className = className;
  return element;
};

const renderUsers = () => {
  if (!usersBody) return;
  const query = String(searchInput?.value || "").trim().toLowerCase();
  const filtered = users.filter((user) =>
    `${user.username} ${user.email || ""}`.toLowerCase().includes(query),
  );
  usersBody.replaceChildren();

  filtered.forEach((user) => {
    const row = document.createElement("tr");
    const identity = cell("Пользователь");
    const primary = document.createElement("div");
    primary.className = "user-primary";
    const username = document.createElement("strong");
    username.textContent = user.username;
    const email = document.createElement("span");
    email.textContent = user.email || "Создан через CLI";
    primary.append(username, email);
    identity.append(primary);

    const status = cell("Статус");
    const badge = document.createElement("span");
    badge.className = `status-badge${user.active ? "" : " is-disabled"}`;
    badge.textContent = user.active ? "Активен" : "Заблокирован";
    status.append(badge);

    const created = cell("Создан", "date-cell");
    created.textContent = formatDate(user.createdAt);
    const lastLogin = cell("Последний вход", "date-cell");
    lastLogin.textContent = formatDate(user.lastLoginAt);

    const action = cell("Действия", "action-cell");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-button";
    remove.textContent = "Удалить";
    remove.addEventListener("click", () => openDelete(user.username, remove));
    action.append(remove);

    row.append(identity, status, created, lastLogin, action);
    usersBody.append(row);
  });

  loadingState.hidden = true;
  usersTable.hidden = filtered.length === 0;
  emptyState.hidden = filtered.length !== 0;
  if (emptyState && query && filtered.length === 0) {
    emptyState.querySelector("strong").textContent = "Ничего не найдено";
    emptyState.querySelector("span").textContent = "Измените запрос поиска.";
  } else if (emptyState) {
    emptyState.querySelector("strong").textContent = "Пользователей нет";
    emptyState.querySelector("span").textContent = "Новые учётные записи появятся здесь после регистрации.";
  }
};

const setNotice = (message, isError = false) => {
  if (!notice) return;
  notice.hidden = !message;
  notice.textContent = message;
  notice.classList.toggle("is-error", isError);
};

const loadUsers = async () => {
  loadingState.hidden = false;
  usersTable.hidden = true;
  emptyState.hidden = true;
  setNotice("");
  if (refreshButton) refreshButton.disabled = true;
  try {
    const payload = await api("/api/admin/users");
    users = Array.isArray(payload.users) ? payload.users : [];
    if (totalUsers) totalUsers.textContent = String(users.length);
    if (activeUsers) activeUsers.textContent = String(users.filter((user) => user.active).length);
    renderUsers();
  } catch (error) {
    loadingState.hidden = true;
    if (error.status === 401) {
      showLogin("Сессия завершена. Войдите снова.");
      return;
    }
    setNotice(error.message, true);
  } finally {
    if (refreshButton) refreshButton.disabled = false;
  }
};

const openDelete = (username, trigger) => {
  selectedUsername = username;
  deleteTrigger = trigger;
  deleteUsername.textContent = username;
  deleteConfirm.value = "";
  deleteSubmit.disabled = true;
  deleteStatus.textContent = "";
  deleteModal.hidden = false;
  document.body.classList.add("has-modal");
  window.setTimeout(() => deleteConfirm.focus(), 0);
};

const closeDelete = () => {
  deleteModal.hidden = true;
  document.body.classList.remove("has-modal");
  deleteTrigger?.focus();
  selectedUsername = "";
};

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!loginForm.reportValidity()) return;
  const button = loginForm.querySelector("button[type='submit']");
  const password = loginForm.elements.namedItem("password");
  button.disabled = true;
  button.firstChild.textContent = "Проверяем ";
  loginStatus.textContent = "";
  try {
    const payload = await api("/api/admin/session", {
      method: "POST",
      body: JSON.stringify({ password: password.value }),
    });
    csrfToken = payload.csrfToken;
    password.value = "";
    showDashboard();
    await loadUsers();
  } catch (error) {
    loginStatus.textContent = error.message;
    password.select();
  } finally {
    button.disabled = false;
    button.firstChild.textContent = "Войти ";
  }
});

logoutButton?.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await api("/api/admin/session", {
      method: "DELETE",
      headers: { "X-Tenion-Admin-CSRF": csrfToken },
    });
  } catch (_) {
    // A local logout still hides admin data if the session already expired.
  } finally {
    logoutButton.disabled = false;
    showLogin();
  }
});

refreshButton?.addEventListener("click", loadUsers);
searchInput?.addEventListener("input", renderUsers);
deleteConfirm?.addEventListener("input", () => {
  deleteSubmit.disabled = deleteConfirm.value !== selectedUsername;
});
document.querySelectorAll("[data-delete-close]").forEach((element) => element.addEventListener("click", closeDelete));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !deleteModal.hidden) closeDelete();
});

deleteSubmit?.addEventListener("click", async () => {
  if (!selectedUsername || deleteConfirm.value !== selectedUsername) return;
  deleteSubmit.disabled = true;
  deleteSubmit.textContent = "Удаляем…";
  deleteStatus.textContent = "";
  try {
    const payload = await api(`/api/admin/users/${encodeURIComponent(selectedUsername)}`, {
      method: "DELETE",
      headers: { "X-Tenion-Admin-CSRF": csrfToken },
    });
    const result = payload.result || {};
    const deletedName = selectedUsername;
    closeDelete();
    users = users.filter((user) => user.username !== deletedName);
    if (totalUsers) totalUsers.textContent = String(users.length);
    if (activeUsers) activeUsers.textContent = String(users.filter((user) => user.active).length);
    renderUsers();
    setNotice(`Пользователь ${deletedName} удалён: проектов — ${result.projectsDeleted || 0}, запусков — ${result.processRunsDeleted || 0}, артефактов — ${result.artifactsDeleted || 0}.`);
  } catch (error) {
    if (error.status === 401) {
      closeDelete();
      showLogin("Сессия завершена. Войдите снова.");
      return;
    }
    deleteStatus.textContent = error.message;
    deleteSubmit.disabled = false;
  } finally {
    deleteSubmit.textContent = "Удалить безвозвратно";
  }
});

const initialize = async () => {
  try {
    const payload = await api("/api/admin/session");
    csrfToken = payload.csrfToken;
    showDashboard();
    await loadUsers();
  } catch (_) {
    showLogin();
  }
};

initialize();
