const CURRENT_YEAR = new Date().getFullYear();
const MODULES = {
  itn: {
    code: "ITN",
    path: "/",
    recordLabel: "fiche ITN",
    recordLabelPlural: "fiches ITN",
    emptyLabel: "Aucun numero ITN enregistre. Reservez des codes ou creez la premiere fiche pour lancer la numerotation.",
    exportSlug: "itn",
    placeholderPrefix: "QT230201-GSS-QA-ITN-01417",
  },
  rir: {
    code: "RIR",
    path: "/rir",
    recordLabel: "fiche RIR",
    recordLabelPlural: "fiches RIR",
    emptyLabel: "Aucun numero RIR enregistre. Reservez des codes ou creez la premiere fiche pour lancer la numerotation.",
    exportSlug: "rir",
    placeholderPrefix: "QT230201-GSS-QA-RIR-01417",
  },
  mrr: {
    code: "MRR",
    path: "/mrr",
    recordLabel: "fiche MRR",
    recordLabelPlural: "fiches MRR",
    emptyLabel: "Aucun numero MRR enregistre. Reservez des codes ou creez la premiere fiche pour lancer la numerotation.",
    exportSlug: "mrr",
    placeholderPrefix: "QT230201-GSS-QA-MRR-01417",
  },
  ncr: {
    code: "NCR",
    path: "/ncr",
    recordLabel: "fiche NCR",
    recordLabelPlural: "fiches NCR",
    emptyLabel: "Aucun numero NCR enregistre. Reservez des codes ou creez la premiere fiche pour lancer la numerotation.",
    exportSlug: "ncr",
    placeholderPrefix: "QT230201-GSS-QA-NCR-01417",
  },
  qor: {
    code: "QOR",
    path: "/qor",
    recordLabel: "fiche QOR",
    recordLabelPlural: "fiches QOR",
    emptyLabel: "Aucun numero QOR enregistre. Reservez des codes ou creez la premiere fiche pour lancer la numerotation.",
    exportSlug: "qor",
    placeholderPrefix: "QT230201-GSS-QA-QOR-01417",
  },
};
const DEFAULT_MODULE_KEY = "itn";

const state = {
  currentModule: getCurrentModule(),
  records: [],
  reusableRecords: [],
  ownerOptions: [],
  users: [],
  editingId: null,
  currentUser: null,
  settings: { prefix: MODULES[getCurrentModule()].placeholderPrefix, usingReservedNumber: false },
  filters: { query: "", status: "all", owner: "all", year: "all" },
  lastSyncLabel: "",
};

const statusLabels = {
  draft: "Brouillon",
  in_review: "En validation",
  approved: "Validee",
  reserved: "Reservee",
  unused: "Non utilise",
  archived: "Archivee",
};

const roleLabels = {
  viewer: "Lecteur",
  editor: "Editeur",
  admin: "Administrateur",
};

const elements = {
  authScreen: document.querySelector("#auth-screen"),
  appShell: document.querySelector("#app-shell"),
  loginForm: document.querySelector("#login-form"),
  loginUsername: document.querySelector("#login-username"),
  loginPassword: document.querySelector("#login-password"),
  authFeedback: document.querySelector("#auth-feedback"),
  passwordForm: document.querySelector("#password-form"),
  passwordWarning: document.querySelector("#password-warning"),
  currentPassword: document.querySelector("#current-password"),
  newPassword: document.querySelector("#new-password"),
  confirmPassword: document.querySelector("#confirm-password"),
  currentUserName: document.querySelector("#current-user-name"),
  currentUserRole: document.querySelector("#current-user-role"),
  logoutButton: document.querySelector("#logout-button"),
  moduleNavLinks: [...document.querySelectorAll(".module-nav__link")],
  topbarModuleCode: document.querySelector("#topbar-module-code"),
  heroTitle: document.querySelector("#hero-title"),
  settingsTitle: document.querySelector("#settings-title"),
  reserveTitle: document.querySelector("#reserve-title"),
  recordsTitle: document.querySelector("#records-title"),
  adminPanel: document.querySelector("#admin-panel"),
  userForm: document.querySelector("#user-form"),
  usersBody: document.querySelector("#users-body"),
  userRowTemplate: document.querySelector("#user-row-template"),
  quickReserveForm: document.querySelector("#quick-reserve-form"),
  quickReserveCount: document.querySelector("#quick-reserve-count"),
  quickReservePreferredField: document.querySelector("#quick-reserve-preferred-field"),
  quickReservePreferredList: document.querySelector("#quick-reserve-preferred-list"),
  quickReservePreview: document.querySelector("#quick-reserve-preview"),
  quickReserveButton: document.querySelector("#quick-reserve-button"),
  form: document.querySelector("#record-form"),
  formTitle: document.querySelector("#form-title"),
  submitButton: document.querySelector("#submit-button"),
  resetButton: document.querySelector("#reset-form"),
  refreshButton: document.querySelector("#refresh-button"),
  prefixInput: document.querySelector("#prefix-input"),
  savePrefixButton: document.querySelector("#save-prefix"),
  numberPreviewLabel: document.querySelector("#number-preview-label"),
  numberPreview: document.querySelector("#number-preview"),
  liveNumber: document.querySelector("#live-number"),
  liveNumberLabel: document.querySelector("#live-number-label"),
  syncStatus: document.querySelector("#sync-status"),
  feedback: document.querySelector("#feedback"),
  totalCount: document.querySelector("#total-count"),
  yearCount: document.querySelector("#year-count"),
  nextNumberLabel: document.querySelector("#next-number-label"),
  nextNumber: document.querySelector("#next-number"),
  reviewCount: document.querySelector("#review-count"),
  recordsBody: document.querySelector("#records-body"),
  rowTemplate: document.querySelector("#row-template"),
  emptyState: document.querySelector("#empty-state"),
  exportButton: document.querySelector("#export-button"),
  searchInput: document.querySelector("#search-input"),
  statusFilter: document.querySelector("#status-filter"),
  ownerFilter: document.querySelector("#owner-filter"),
  yearFilter: document.querySelector("#year-filter"),
  reusableNumberField: document.querySelector("#reusable-number-field"),
  reusableNumberSelect: document.querySelector("#reusable-number-select"),
  userFields: {
    displayName: document.querySelector("#user-display-name"),
    username: document.querySelector("#user-username"),
    role: document.querySelector("#user-role"),
    password: document.querySelector("#user-password"),
  },
  fields: {
    title: document.querySelector("#title"),
    year: document.querySelector("#year"),
    createdAt: document.querySelector("#created-at"),
    department: document.querySelector("#department"),
    owner: document.querySelector("#owner"),
    status: document.querySelector("#status"),
    notes: document.querySelector("#notes"),
  },
};

initialize();

function getCurrentModule() {
  const normalizedPath = window.location.pathname.replace(/\/+$/, "") || "/";
  return Object.entries(MODULES).find(([, module]) => module.path === normalizedPath)?.[0] || DEFAULT_MODULE_KEY;
}

function getModuleConfig() {
  return MODULES[state.currentModule] || MODULES[DEFAULT_MODULE_KEY];
}

function buildModuleApiUrl(path, extraParams = null) {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("module", state.currentModule);

  if (extraParams instanceof URLSearchParams) {
    extraParams.forEach((value, key) => {
      if (value !== "") {
        url.searchParams.set(key, value);
      }
    });
  }

  return `${url.pathname}${url.search}`;
}

function renderModuleChrome() {
  const module = getModuleConfig();

  document.title = `Registre Qualite ${module.code}`;
  elements.topbarModuleCode.textContent = module.code;
  elements.heroTitle.textContent = `Maitrisez la numerotation et la validation de chaque fiche ${module.code}`;
  elements.settingsTitle.textContent = `Parametres de numerotation ${module.code}`;
  elements.reserveTitle.textContent = `Generer plusieurs numeros ${module.code}`;
  elements.recordsTitle.textContent = `Liste des fiches ${module.code}`;
  elements.emptyState.textContent = module.emptyLabel;
  elements.prefixInput.placeholder = module.placeholderPrefix;
  elements.moduleNavLinks.forEach((link) => {
    link.dataset.active = link.dataset.module === state.currentModule ? "true" : "false";
  });

  if (!state.editingId) {
    elements.formTitle.textContent = `Ajouter une ${module.recordLabel}`;
  }
}

function initialize() {
  renderModuleChrome();
  setDefaultFormValues();
  bindEvents();
  restoreSession();
  window.setInterval(() => {
    if (state.currentUser) {
      loadRecords({ silent: true }).catch(() => {});
    }
  }, 30000);
}

function bindEvents() {
  elements.loginForm.addEventListener("submit", handleLogin);
  elements.logoutButton.addEventListener("click", handleLogout);
  elements.passwordForm.addEventListener("submit", handleChangePassword);
  elements.quickReserveForm.addEventListener("submit", handleQuickReserve);
  elements.form.addEventListener("submit", handleSubmit);
  elements.userForm.addEventListener("submit", handleCreateUser);
  elements.resetButton.addEventListener("click", resetForm);
  elements.refreshButton.addEventListener("click", () => loadDashboard());
  elements.savePrefixButton.addEventListener("click", savePrefix);
  elements.exportButton.addEventListener("click", exportCsv);
  elements.searchInput.addEventListener("input", (event) => {
    state.filters.query = event.target.value.trim().toLowerCase();
    loadRecords({ silent: true }).catch(() => {});
  });
  elements.statusFilter.addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    loadRecords({ silent: true }).catch(() => {});
  });
  elements.ownerFilter.addEventListener("change", (event) => {
    state.filters.owner = event.target.value;
    loadRecords({ silent: true }).catch(() => {});
  });
  elements.yearFilter.addEventListener("change", (event) => {
    state.filters.year = event.target.value;
    loadRecords({ silent: true }).catch(() => {});
  });
  elements.fields.year.addEventListener("input", updateLiveNumber);
  elements.reusableNumberSelect.addEventListener("change", updateLiveNumber);
  elements.quickReservePreferredList.addEventListener("change", updateQuickReservePreview);
  elements.quickReserveCount.addEventListener("input", updateQuickReservePreview);
}

async function restoreSession() {
  try {
    const response = await fetchJson("/api/auth/me");
    state.currentUser = response.user;
    showApplication();
    await loadDashboard();
  } catch {
    showLogin();
  }
}

async function handleLogin(event) {
  event.preventDefault();
  hideFeedback(elements.authFeedback);

  try {
    const response = await fetchJson("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: elements.loginUsername.value.trim(),
        password: elements.loginPassword.value,
      }),
    });

    state.currentUser = response.user;
    elements.loginPassword.value = "";
    showApplication();
    await loadDashboard();
    renderPasswordWarning();
    showFeedback("Connexion reussie.");
  } catch (error) {
    showFeedback(error.message, "error", elements.authFeedback);
  }
}

async function handleLogout() {
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
  } catch {}

  state.currentUser = null;
  state.records = [];
  state.reusableRecords = [];
  state.ownerOptions = [];
  state.users = [];
  resetForm();
  elements.passwordForm.reset();
  showLogin();
}

async function loadDashboard() {
  try {
    await Promise.all([
      loadSettings(),
      loadRecords(),
      loadUsersIfAllowed(),
    ]);
    renderCurrentUser();
    renderPasswordWarning();
    showFeedback("Donnees synchronisees avec succes.");
  } catch (error) {
    if (error.status === 401) {
      showLogin();
      return;
    }
    showFeedback(error.message, "error");
  }
}

async function loadSettings() {
  const response = await fetchJson(buildModuleApiUrl("/api/settings"));
  state.settings.prefix = response.prefix;
  state.settings.usingReservedNumber = Boolean(response.usingReservedNumber);
  elements.prefixInput.value = response.prefix;
  elements.numberPreview.textContent = response.nextNumber;
  renderNumberUsageLabels();
  updateLiveNumber();
}

async function loadRecords(options = {}) {
  const params = new URLSearchParams();
  if (state.filters.query) params.set("search", state.filters.query);
  if (state.filters.status !== "all") params.set("status", state.filters.status);
  if (state.filters.owner !== "all") params.set("owner", state.filters.owner);
  if (state.filters.year !== "all") params.set("year", state.filters.year);

  try {
    const response = await fetchJson(buildModuleApiUrl("/api/records", params));
    state.records = response.records;
    state.reusableRecords = response.reusableRecords || [];
    state.ownerOptions = response.owners || [];
    state.settings.prefix = response.prefix;
    elements.prefixInput.value = response.prefix;
    state.lastSyncLabel = new Intl.DateTimeFormat("fr-FR", {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(new Date());
    render();
  } catch (error) {
    if (!options.silent) {
      showFeedback(error.message, "error");
    }
    throw error;
  }
}

async function loadUsersIfAllowed() {
  if (!isAdmin()) {
    state.users = [];
    renderUsers();
    return;
  }

  const response = await fetchJson("/api/users");
  state.users = response.users;
  renderUsers();
}

async function handleSubmit(event) {
  event.preventDefault();

  const payload = {
    title: elements.fields.title.value.trim(),
    year: Number(elements.fields.year.value),
    createdAt: elements.fields.createdAt.value,
    department: elements.fields.department.value.trim(),
    owner: elements.fields.owner.value.trim(),
    status: elements.fields.status.value,
    notes: elements.fields.notes.value.trim(),
    reusableRecordId: elements.reusableNumberSelect.value || null,
  };

  try {
    if (state.editingId) {
      await fetchJson(buildModuleApiUrl(`/api/records/${state.editingId}`), {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showFeedback("La fiche a ete mise a jour.");
    } else {
      const response = await fetchJson(buildModuleApiUrl("/api/records"), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showFeedback(
        response.usedReservedNumber
          ? `La fiche a ete creee avec le numero non utilise ${response.record.number}.`
          : "La fiche a ete creee.",
      );
    }

    resetForm();
    await Promise.all([loadSettings(), loadRecords()]);
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

async function handleQuickReserve(event) {
  event.preventDefault();

  const quantity = Number(elements.quickReserveCount.value);
  const preferredReusableRecordIds = getSelectedQuickReserveIds();

  if (preferredReusableRecordIds.length > quantity) {
    showFeedback("Le nombre de numeros non utilises coches depasse la quantite demandee.", "error");
    return;
  }

  try {
    const response = await fetchJson(buildModuleApiUrl("/api/records/reserve"), {
      method: "POST",
      body: JSON.stringify({ quantity, preferredReusableRecordIds }),
    });

    elements.quickReserveCount.value = "1";
    clearQuickReserveSelections();
    updateQuickReservePreview();
    await Promise.all([loadSettings(), loadRecords()]);
    showFeedback(
      response.selectedCount
        ? `${response.count} numero(s) reserve(s) : ${response.selectedCount} choisi(s) + ${response.generatedCount} nouveau(x).`
        : `${response.count} numero(s) reserve(s) : ${response.firstNumber} -> ${response.lastNumber}`,
    );
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

async function handleCreateUser(event) {
  event.preventDefault();

  try {
    await fetchJson("/api/users", {
      method: "POST",
      body: JSON.stringify({
        displayName: elements.userFields.displayName.value.trim(),
        username: elements.userFields.username.value.trim(),
        role: elements.userFields.role.value,
        password: elements.userFields.password.value,
      }),
    });

    elements.userForm.reset();
    elements.userFields.role.value = "viewer";
    await loadUsersIfAllowed();
    showFeedback("Utilisateur cree avec succes.");
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

async function handleChangePassword(event) {
  event.preventDefault();

  const currentPassword = elements.currentPassword.value;
  const newPassword = elements.newPassword.value;
  const confirmPassword = elements.confirmPassword.value;

  if (newPassword !== confirmPassword) {
    showFeedback("La confirmation du mot de passe ne correspond pas.", "error");
    return;
  }

  try {
    const response = await fetchJson("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        currentPassword,
        newPassword,
      }),
    });

    state.currentUser = response.user;
    elements.passwordForm.reset();
    renderCurrentUser();
    renderPasswordWarning();
    showFeedback("Mot de passe mis a jour avec succes.");
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

async function savePrefix() {
  try {
    const response = await fetchJson(buildModuleApiUrl("/api/settings"), {
      method: "PUT",
      body: JSON.stringify({ prefix: sanitizePrefix(elements.prefixInput.value) }),
    });
    state.settings.prefix = response.prefix;
    elements.prefixInput.value = response.prefix;
    await Promise.all([loadSettings(), loadRecords()]);
    showFeedback(`Le prefixe ${getModuleConfig().code} a ete mis a jour.`);
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

async function deleteRecord(recordId) {
  const record = state.records.find((item) => item.id === recordId);
  if (!record) return;
  if (!window.confirm(`Supprimer la fiche ${record.number} ?`)) return;

  try {
    await fetchJson(buildModuleApiUrl(`/api/records/${recordId}`), { method: "DELETE" });
    if (state.editingId === recordId) resetForm();
    await Promise.all([loadSettings(), loadRecords()]);
    showFeedback("La fiche a ete supprimee.");
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

function showApplication() {
  elements.authScreen.hidden = true;
  elements.appShell.hidden = false;
  hideFeedback(elements.authFeedback);
}

function showLogin() {
  elements.appShell.hidden = true;
  elements.authScreen.hidden = false;
  elements.loginForm.reset();
  elements.loginUsername.focus();
  hideFeedback(elements.feedback);
}

function renderCurrentUser() {
  if (!state.currentUser) return;

  elements.currentUserName.textContent = `${state.currentUser.displayName} (${state.currentUser.username})`;
  elements.currentUserRole.textContent = roleLabels[state.currentUser.role] || state.currentUser.role;
  elements.adminPanel.hidden = !isAdmin();
  elements.savePrefixButton.disabled = !isAdmin();
  elements.prefixInput.disabled = !isAdmin();
  setRecordFormAccess();
}

function setDefaultFormValues() {
  const today = new Date().toISOString().slice(0, 10);
  elements.fields.createdAt.value = today;
  elements.fields.year.value = String(CURRENT_YEAR);
  elements.fields.status.value = "draft";
  elements.reusableNumberSelect.value = "";
  clearQuickReserveSelections();
  updateLiveNumber();
  updateQuickReservePreview();
}

function resetForm() {
  state.editingId = null;
  elements.form.reset();
  setDefaultFormValues();
  renderReusableNumberOptions();
  updateLiveNumber();
  elements.formTitle.textContent = `Ajouter une ${getModuleConfig().recordLabel}`;
  elements.submitButton.textContent = "Enregistrer la fiche";
  setRecordFormAccess();
}

function render() {
  renderModuleChrome();
  renderStats();
  renderOwnerFilter();
  renderYearFilter();
  renderReusableNumberOptions();
  renderQuickReservePreferredOptions();
  renderTable();
  renderCurrentUser();
  updateSyncStatus();
  updateLiveNumber();
  updateQuickReservePreview();
}

function renderStats() {
  const currentYearRecords = state.records.filter((item) => Number(item.year) === CURRENT_YEAR);
  const inReviewRecords = state.records.filter((item) => item.status === "in_review");
  const nextNumber = getNextSuggestedNumber(state.settings.prefix);

  elements.totalCount.textContent = String(state.records.length);
  elements.yearCount.textContent = String(currentYearRecords.length);
  elements.reviewCount.textContent = String(inReviewRecords.length);
  elements.nextNumber.textContent = nextNumber;
  elements.numberPreview.textContent = nextNumber;
  renderNumberUsageLabels();
}

function renderYearFilter() {
  const years = [...new Set(state.records.map((item) => String(item.year)))].sort((a, b) => Number(b) - Number(a));
  const currentValue = state.filters.year;

  elements.yearFilter.innerHTML = '<option value="all">Toutes</option>';
  years.forEach((year) => {
    const option = document.createElement("option");
    option.value = year;
    option.textContent = year;
    elements.yearFilter.append(option);
  });

  if (years.includes(currentValue)) {
    elements.yearFilter.value = currentValue;
  } else {
    state.filters.year = "all";
    elements.yearFilter.value = "all";
  }
}

function renderOwnerFilter() {
  const owners = state.ownerOptions;
  const currentValue = state.filters.owner;

  elements.ownerFilter.innerHTML = '<option value="all">Tous</option>';
  owners.forEach((owner) => {
    const option = document.createElement("option");
    option.value = owner;
    option.textContent = owner;
    elements.ownerFilter.append(option);
  });

  if (owners.includes(currentValue)) {
    elements.ownerFilter.value = currentValue;
  } else {
    state.filters.owner = "all";
    elements.ownerFilter.value = "all";
  }
}

function renderTable() {
  elements.recordsBody.innerHTML = "";

  state.records.forEach((record) => {
    const fragment = elements.rowTemplate.content.cloneNode(true);
    const cells = fragment.querySelectorAll("td");
    cells[0].textContent = record.number;

    cells[1].textContent = record.title;
    const titleMeta = document.createElement("span");
    titleMeta.className = "record-meta";
    titleMeta.textContent = `Cree par ${record.createdBy || "N/A"}`;
    cells[1].append(titleMeta);

    cells[2].textContent = record.department;
    cells[3].textContent = record.owner;
    cells[4].append(createStatusPill(record.status));

    cells[5].textContent = formatDate(record.updatedAt || record.createdAt);
    const updateMeta = document.createElement("span");
    updateMeta.className = "record-meta";
    updateMeta.textContent = `Par ${record.updatedBy || record.createdBy || "N/A"}`;
    cells[5].append(updateMeta);

    const editButton = fragment.querySelector('[data-action="edit"]');
    const deleteButton = fragment.querySelector('[data-action="delete"]');
    editButton.addEventListener("click", () => startEditing(record.id));
    deleteButton.addEventListener("click", () => deleteRecord(record.id));
    editButton.disabled = !canEdit();
    deleteButton.disabled = !isAdmin();

    elements.recordsBody.append(fragment);
  });

  elements.emptyState.hidden = state.records.length > 0;
  elements.emptyState.textContent = getModuleConfig().emptyLabel;
}

function renderUsers() {
  elements.usersBody.innerHTML = "";
  if (!isAdmin()) return;

  state.users.forEach((user) => {
    const fragment = elements.userRowTemplate.content.cloneNode(true);
    const cells = fragment.querySelectorAll("td");
    cells[0].textContent = user.displayName;
    cells[1].textContent = user.username;
    cells[2].append(createRolePill(user.role));
    cells[3].textContent = user.mustChangePassword ? "Mot de passe temporaire" : "Acces normal";
    cells[4].textContent = formatDate(user.createdAt);
    fragment.querySelector('[data-action="reset-password"]').addEventListener("click", () => resetUserPassword(user));
    elements.usersBody.append(fragment);
  });
}

async function resetUserPassword(user) {
  const confirmed = window.confirm(`Reinitialiser le mot de passe de ${user.displayName} ?`);
  if (!confirmed) return;

  try {
    const response = await fetchJson(`/api/users/${user.id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({}),
    });

    await loadUsersIfAllowed();
    showFeedback(
      `Mot de passe temporaire pour ${user.username} : ${response.temporaryPassword}`,
      "success",
    );
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

function startEditing(recordId) {
  if (!canEdit()) return;

  const record = state.records.find((item) => item.id === recordId);
  if (!record) return;

  state.editingId = record.id;
  elements.formTitle.textContent = `Modifier ${record.number}`;
  elements.submitButton.textContent = "Mettre a jour la fiche";
  elements.fields.title.value = record.title;
  elements.fields.year.value = String(record.year);
  elements.fields.createdAt.value = record.createdAt;
  elements.fields.department.value = record.department;
  elements.fields.owner.value = record.owner;
  elements.fields.status.value = record.status;
  elements.fields.notes.value = record.notes || "";
  elements.reusableNumberField.hidden = true;
  elements.reusableNumberSelect.value = "";
  updateLiveNumber();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateLiveNumber() {
  if (state.editingId) {
    const record = state.records.find((item) => item.id === state.editingId);
    if (record) {
      const prefix = record.prefix || state.settings.prefix;
      elements.liveNumberLabel.textContent = "Numero de la fiche";
      elements.liveNumber.textContent = buildNumber(prefix, record.serial);
      return;
    }
  }

  elements.liveNumber.textContent = getNextSuggestedNumber(state.settings.prefix, getSelectedReusableRecordId());
  renderNumberUsageLabels();
}

function updateQuickReservePreview() {
  const quantity = Math.max(1, Number(elements.quickReserveCount.value) || 1);
  const selectedRecords = getSelectedQuickReserveRecords();
  const selectedCount = selectedRecords.length;

  if (selectedCount > quantity) {
    elements.quickReservePreview.textContent = `Selection actuelle : ${selectedCount} numero(s) non utilise(s). Augmentez la quantite ou decochez des numeros.`;
    return;
  }

  if (selectedCount === quantity && selectedCount > 0) {
    const numbers = selectedRecords.map((record) => record.number);
    elements.quickReservePreview.textContent = `Numeros choisis : ${numbers.join(" | ")}`;
    return;
  }

  const firstSerial = getNextFreshSerial(state.settings.prefix);
  const lastSerial = firstSerial + (quantity - selectedCount) - 1;
  const firstNumber = buildNumber(state.settings.prefix, firstSerial);
  const lastNumber = buildNumber(state.settings.prefix, lastSerial);
  if (selectedCount > 0) {
    const selectedNumbers = selectedRecords.map((record) => record.number).join(" | ");
    elements.quickReservePreview.textContent = quantity - selectedCount === 1
      ? `Choisis : ${selectedNumbers} + nouveau : ${firstNumber}`
      : `Choisis : ${selectedNumbers} + nouveaux : ${firstNumber} -> ${lastNumber}`;
    return;
  }

  elements.quickReservePreview.textContent = quantity === 1
    ? `Numero reserve : ${firstNumber}`
    : `Plage reservee : ${firstNumber} -> ${lastNumber}`;
}

function getReusableReservedRecords(prefix, excludedId = null) {
  return state.reusableRecords
    .filter((item) => (
      item.prefix === prefix
      && item.status === "unused"
      && item.id !== excludedId
    ))
    .sort((left, right) => Number(left.serial) - Number(right.serial));
}

function getReusableReservedRecord(prefix, excludedId = null) {
  return getReusableReservedRecords(prefix, excludedId)[0] || null;
}

function getNextFreshSerial(prefix, excludedId = null) {
  const serials = state.records
    .filter((item) => item.prefix === prefix && item.id !== excludedId)
    .map((item) => Number(item.serial))
    .filter((value) => Number.isFinite(value));

  return serials.length === 0 ? 1 : Math.max(...serials) + 1;
}

function getNextSuggestedNumber(prefix, excludedId = null) {
  const selectedReusableRecord = getSelectedReusableRecord(prefix, excludedId);
  if (selectedReusableRecord) {
    return selectedReusableRecord.number;
  }

  const reusable = getReusableReservedRecord(prefix, excludedId);
  if (reusable) {
    return reusable.number;
  }

  return buildNumber(prefix, getNextFreshSerial(prefix, excludedId));
}

function getSelectedReusableRecordId() {
  const value = Number(elements.reusableNumberSelect.value);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function getSelectedReusableRecord(prefix, excludedId = null) {
  const selectedId = getSelectedReusableRecordId();
  if (!selectedId) return null;
  return getReusableReservedRecords(prefix, excludedId).find((item) => item.id === selectedId) || null;
}

function getSelectedQuickReserveIds() {
  return [...elements.quickReservePreferredList.querySelectorAll('input[type="checkbox"]:checked')]
    .map((input) => Number(input.value))
    .filter((value) => Number.isFinite(value) && value > 0);
}

function getSelectedQuickReserveRecords() {
  const selectedIds = new Set(getSelectedQuickReserveIds());
  return getReusableReservedRecords(state.settings.prefix).filter((record) => selectedIds.has(record.id));
}

function renderReusableNumberOptions() {
  const reusableRecords = getReusableReservedRecords(state.settings.prefix);
  const selectedValue = elements.reusableNumberSelect.value;

  elements.reusableNumberSelect.innerHTML = '<option value="">Selectionner un numero non utilise</option>';

  reusableRecords.forEach((record) => {
    const option = document.createElement("option");
    option.value = String(record.id);
    option.textContent = record.number;
    elements.reusableNumberSelect.append(option);
  });

  if (reusableRecords.some((record) => String(record.id) === selectedValue)) {
    elements.reusableNumberSelect.value = selectedValue;
  } else if (reusableRecords.length > 0) {
    elements.reusableNumberSelect.value = String(reusableRecords[0].id);
  } else {
    elements.reusableNumberSelect.value = "";
  }

  elements.reusableNumberField.hidden = state.editingId !== null || reusableRecords.length === 0;
}

function renderQuickReservePreferredOptions() {
  const reusableRecords = getReusableReservedRecords(state.settings.prefix);
  const selectedIds = new Set(getSelectedQuickReserveIds());

  elements.quickReservePreferredList.innerHTML = "";

  reusableRecords.forEach((record) => {
    const label = document.createElement("label");
    label.className = "checkbox-list__item";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = String(record.id);
    input.checked = selectedIds.has(record.id);

    const text = document.createElement("span");
    text.textContent = record.number;

    label.append(input, text);
    elements.quickReservePreferredList.append(label);
  });

  elements.quickReservePreferredField.hidden = reusableRecords.length === 0;
}

function clearQuickReserveSelections() {
  elements.quickReservePreferredList
    .querySelectorAll('input[type="checkbox"]')
    .forEach((input) => {
      input.checked = false;
    });
}

function renderNumberUsageLabels() {
  const hasReusableReserved = Boolean(getReusableReservedRecord(state.settings.prefix));
  const usingReserved = hasReusableReserved || state.settings.usingReservedNumber;

  elements.numberPreviewLabel.textContent = usingReserved ? "Numero non utilise disponible :" : "Prochain numero :";
  elements.nextNumberLabel.textContent = usingReserved ? "Numero non utilise" : "Prochain numero";
  elements.liveNumberLabel.textContent = usingReserved ? "Numero non utilise" : "Numero prevu";
}

function createStatusPill(status) {
  const pill = document.createElement("span");
  pill.className = "status-pill";
  pill.dataset.status = status;
  pill.textContent = statusLabels[status] || status;
  return pill;
}

function createRolePill(role) {
  const pill = document.createElement("span");
  pill.className = "role-pill";
  pill.dataset.role = role;
  pill.textContent = roleLabels[role] || role;
  return pill;
}

function sanitizePrefix(value) {
  const fallback = getModuleConfig().placeholderPrefix;
  const normalized = String(value || fallback).toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 32);
  return normalized || fallback;
}

function buildNumber(prefix, serial) {
  const normalizedPrefix = String(prefix || "");
  const head = normalizedPrefix.replace(/\d+$/, "");
  const tail = normalizedPrefix.slice(head.length);

  if (!tail) {
    return `${normalizedPrefix}${serial}`;
  }

  const width = tail.length + 1;
  const value = Number(tail) * 10 + Number(serial);
  return `${head}${String(value).padStart(width, "0")}`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("fr-FR").format(date);
}

function updateSyncStatus() {
  elements.syncStatus.textContent = state.lastSyncLabel
    ? `Derniere synchronisation : ${state.lastSyncLabel}`
    : "Connexion a la base en cours...";
}

function renderPasswordWarning() {
  if (state.currentUser?.mustChangePassword) {
    showFeedback(
      "Votre mot de passe a ete reinitialise. Merci de le changer avant de continuer.",
      "error",
      elements.passwordWarning,
    );
    return;
  }

  hideFeedback(elements.passwordWarning);
}

function showFeedback(message, variant = "success", target = elements.feedback) {
  target.hidden = false;
  target.dataset.variant = variant;
  target.textContent = message;
}

function hideFeedback(target) {
  target.hidden = true;
  target.textContent = "";
  delete target.dataset.variant;
}

function exportCsv() {
  if (state.records.length === 0) {
    showFeedback("Aucune fiche a exporter.", "error");
    return;
  }

  const header = ["Numero", "Intitule", "Annee", "Date de creation", "Service", "Responsable", "Statut", "Cree par", "Mis a jour par", "Notes"];
  const rows = state.records.map((record) => [
    record.number,
    record.title,
    record.year,
    record.createdAt,
    record.department,
    record.owner,
    statusLabels[record.status] || record.status,
    record.createdBy || "",
    record.updatedBy || "",
    record.notes || "",
  ]);

  const csv = [header, ...rows].map((columns) => columns.map(escapeCsvCell).join(";")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `fiches-${getModuleConfig().exportSlug}-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function setRecordFormAccess() {
  const enabled = canEdit() && !state.currentUser?.mustChangePassword;
  Object.values(elements.fields).forEach((field) => {
    field.disabled = !enabled;
  });
  elements.reusableNumberSelect.disabled = !enabled;
  elements.quickReservePreferredList
    .querySelectorAll('input[type="checkbox"]')
    .forEach((input) => {
      input.disabled = !enabled;
    });
  elements.submitButton.disabled = !enabled;
  elements.resetButton.disabled = !enabled;
  elements.quickReserveCount.disabled = !enabled;
  elements.quickReserveButton.disabled = !enabled;
}

function escapeCsvCell(value) {
  const safeValue = String(value ?? "");
  return `"${safeValue.replace(/"/g, '""')}"`;
}

function canEdit() {
  return state.currentUser && ["admin", "editor"].includes(state.currentUser.role);
}

function isAdmin() {
  return state.currentUser && state.currentUser.role === "admin";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });

  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "La requete a echoue.");
    error.status = response.status;
    throw error;
  }
  return data;
}
