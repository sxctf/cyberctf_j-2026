const sampleArchiveParams = {
  filename: "socialvault-export.xml",
  handle: "@mira_ops",
  displayName: "Mira Operations",
  network: "Chatter",
  risk: "low",
  mode: "merge"
};

const overlay = document.querySelector("#import-overlay");
const openButton = document.querySelector("#open-import");
const closeButton = document.querySelector("#close-import");
const secondaryOpenButton = document.querySelector("#open-import-secondary");
const loadSampleButton = document.querySelector("#load-sample");
const submitButton = document.querySelector("#submit-import");
const archiveFilename = document.querySelector("#archive-filename");
const archiveHandle = document.querySelector("#archive-handle");
const archiveDisplayName = document.querySelector("#archive-display-name");
const archiveNetwork = document.querySelector("#archive-network");
const archiveRisk = document.querySelector("#archive-risk");
const archiveMode = document.querySelector("#archive-mode");
const result = document.querySelector("#import-result");
const archiveJobStatus = document.querySelector("#archive-job-status");
const archiveList = document.querySelector("#archive-list");
const watchlistStatus = document.querySelector("#watchlist-status");
const searchInput = document.querySelector("#search-input");
const navButtons = document.querySelectorAll("[data-view]");
const views = document.querySelectorAll("[data-view-panel]");
const viewTitle = document.querySelector("#view-title");
const viewEyebrow = document.querySelector("#view-eyebrow");
const actionButtons = document.querySelectorAll("[data-action]");

const viewCopy = {
  live: {
    title: "Pulse stream",
    eyebrow: "Live social overview"
  },
  profiles: {
    title: "Profile index",
    eyebrow: "Known social identities"
  },
  mentions: {
    title: "Mention intelligence",
    eyebrow: "Keyword and entity queue"
  },
  watchlists: {
    title: "Watchlists",
    eyebrow: "Tracked account groups"
  },
  archive: {
    title: "Archive Vault",
    eyebrow: "Legacy imports"
  }
};

function readArchiveParams() {
  return {
    filename: archiveFilename.value.trim(),
    handle: archiveHandle.value.trim(),
    displayName: archiveDisplayName.value.trim(),
    network: archiveNetwork.value,
    risk: archiveRisk.value,
    mode: archiveMode.value
  };
}

function applyArchiveParams(params) {
  archiveFilename.value = params.filename;
  archiveHandle.value = params.handle;
  archiveDisplayName.value = params.displayName;
  archiveNetwork.value = params.network;
  archiveRisk.value = params.risk;
  archiveMode.value = params.mode;
}

applyArchiveParams(sampleArchiveParams);

function openDrawer() {
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  archiveFilename.focus();
}

function closeDrawer() {
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
  openButton.focus();
}

function setImportStatus(message) {
  result.textContent = message;
  if (archiveJobStatus) {
    archiveJobStatus.textContent = message;
  }
}

function createInspectHandler(button) {
  button.addEventListener("click", () => {
    const archiveName = button.dataset.archive || "selected archive";
    const source = button.dataset.source || "SocialVault";
    const status = button.dataset.status || "background processing";
    const message = [
      `Archive: ${archiveName}`,
      `Source: ${source}`,
      "Parser profile: legacy-compat",
      `Status: ${status}`
    ].join("\n");

    setImportStatus(message);
  });
}

function addArchiveRow(params, job) {
  const row = document.createElement("article");
  row.className = "archive-row";

  const details = document.createElement("div");
  const title = document.createElement("strong");
  const meta = document.createElement("span");
  const button = document.createElement("button");

  const jobId = job.jobId || job.id || `imp_${Date.now().toString(16)}`;
  const status = job.status || "queued";
  const displayName = params.displayName || "unknown profile";
  const handle = params.handle || "unknown handle";

  title.textContent = params.filename;
  meta.textContent = `${status} · ${displayName} ${handle} · job ${jobId}`;

  button.className = "quiet-button";
  button.type = "button";
  button.dataset.archive = params.filename;
  button.dataset.source = "SocialVault";
  button.dataset.status = status;
  button.textContent = "Inspect";
  createInspectHandler(button);

  details.append(title, meta);
  row.append(details, button);

  const firstArchive = archiveList.querySelector(".archive-row");
  archiveList.insertBefore(row, firstArchive);
}

function switchView(viewName) {
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });

  views.forEach((view) => {
    view.classList.toggle("active", view.dataset.viewPanel === viewName);
  });

  const copy = viewCopy[viewName];
  if (copy) {
    viewTitle.textContent = copy.title;
    viewEyebrow.textContent = copy.eyebrow;
  }

  window.location.hash = viewName;
}

openButton.addEventListener("click", openDrawer);
secondaryOpenButton.addEventListener("click", openDrawer);
closeButton.addEventListener("click", closeDrawer);

navButtons.forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

overlay.addEventListener("click", (event) => {
  if (event.target === overlay) {
    closeDrawer();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !overlay.classList.contains("hidden")) {
    closeDrawer();
  }
});

loadSampleButton.addEventListener("click", () => {
  applyArchiveParams(sampleArchiveParams);
  setImportStatus("Sample SocialVault archive parameters loaded.");
});

searchInput.addEventListener("input", () => {
  const value = searchInput.value.trim();
  if (!value) {
    setImportStatus("No archive imported in this session.");
    return;
  }

  setImportStatus(`Search filter staged: ${value}\nFeed results are pre-indexed in this demo workspace.`);
});

actionButtons.forEach((button) => {
  if (button.dataset.action === "inspect-archive") {
    createInspectHandler(button);
    return;
  }

  button.addEventListener("click", () => {
    const action = button.dataset.action;

    if (action === "refresh-feed") {
      setImportStatus("Live feed refreshed.\n3 monitored posts remain visible in the current demo workspace.");
      return;
    }

    if (action === "export-mentions") {
      setImportStatus("Mentions export staged.\nCSV rows: 34\nIncludes live posts, bios and imported archive hits.");
      return;
    }

    if (action === "sync-watchlists") {
      if (watchlistStatus) {
        watchlistStatus.textContent = [
          "Watchlist sync completed.",
          "",
          "Updated groups: 3",
          "New accounts: 2",
          "Stale profiles: 3"
        ].join("\n");
      }
      setImportStatus("Watchlists synced with the active workspace.");
      return;
    }

  });
});

submitButton.addEventListener("click", async () => {
  const params = readArchiveParams();

  if (!params.filename || !params.handle || !params.displayName) {
    setImportStatus("Archive import failed: filename, handle and display name are required.");
    return;
  }

  submitButton.disabled = true;
  setImportStatus("Requesting SocialVault legacy archive from /api/archive/import ...");

  try {
    const response = await fetch("/api/archive/import?id=sv-7142", {
      method: "GET",
      headers: {
        "Accept": "application/xml, text/xml, */*"
      }
    });

    await response.text();

    setImportStatus([
      `HTTP ${response.status} ${response.statusText}`,
      "",
      "Legacy archive loaded from the compatibility worker.",
      "The archive has been queued for workspace normalization."
    ].join("\n"));

    closeDrawer();
    addArchiveRow(params, { jobId: `imp_${Date.now().toString(16)}`, status: "loaded" });
    switchView("archive");
  } catch (error) {
    const fallbackJob = {
      jobId: `local_${Date.now().toString(16)}`,
      status: "queued"
    };

    setImportStatus([
      "Archive import queued in the UI.",
      "",
      "The backend endpoint /api/archive/import is not reachable from this page.",
      "When served by the challenge backend, this same action sends the import request.",
      "",
      String(error)
    ].join("\n"));

    closeDrawer();
    addArchiveRow(params, fallbackJob);
    switchView("archive");
  } finally {
    submitButton.disabled = false;
  }
});

const initialView = window.location.hash.replace("#", "");
if (viewCopy[initialView]) {
  switchView(initialView);
}
