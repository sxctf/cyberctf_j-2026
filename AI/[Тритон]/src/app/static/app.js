const modelSelect = document.querySelector("#modelSelect");
const requestBody = document.querySelector("#requestBody");
const responseBody = document.querySelector("#responseBody");
const responseMeta = document.querySelector("#responseMeta");
const memoryBody = document.querySelector("#memoryBody");
const memoryResponseBody = document.querySelector("#memoryResponseBody");
const memoryMeta = document.querySelector("#memoryMeta");
const debugBody = document.querySelector("#debugBody");
const debugResponseBody = document.querySelector("#debugResponseBody");
const debugMeta = document.querySelector("#debugMeta");
const healthStatus = document.querySelector("#healthStatus");

const tabButtons = Array.from(document.querySelectorAll("[data-tab-target]"));
const tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function setPanelResponse(panel, value, meta, isSuccess = false) {
  panel.body.textContent = typeof value === "string" ? value : pretty(value);
  panel.meta.textContent = meta;
  panel.body.dataset.state = isSuccess ? "success" : "default";
}

function setButtonBusy(button, isBusy, busyText) {
  if (!button) {
    return;
  }
  if (!button.dataset.label) {
    button.dataset.label = button.textContent.trim();
  }
  button.disabled = isBusy;
  button.classList.toggle("is-loading", isBusy);
  button.textContent = isBusy ? busyText : button.dataset.label;
}

function switchTab(nextTab) {
  for (const button of tabButtons) {
    const isActive = button.dataset.tabTarget === nextTab;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  }
  for (const panel of tabPanels) {
    const isActive = panel.dataset.tabPanel === nextTab;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    healthStatus.textContent = response.ok ? "готов" : "ошибка";
    healthStatus.dataset.state = response.ok ? "ready" : "degraded";
  } catch {
    healthStatus.textContent = "недоступен";
    healthStatus.dataset.state = "offline";
  }
}

function renderModelOptions(models) {
  modelSelect.textContent = "";
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.name;
    option.textContent = model.name;
    modelSelect.append(option);
  }
  modelSelect.value = models.some((model) => model.name === "stateful_python_backend")
    ? "stateful_python_backend"
    : models[0]?.name || "";
}

async function loadModels() {
  try {
    const response = await fetch("/api/models");
    if (!response.ok) {
      modelSelect.innerHTML = '<option value="">модели недоступны</option>';
      return;
    }

    const payload = await response.json();
    renderModelOptions(payload.models || []);
  } catch {
    modelSelect.innerHTML = '<option value="">модели недоступны</option>';
  }
}

async function postJson(url, body) {
  const startedAt = performance.now();
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  const elapsed = Math.round(performance.now() - startedAt);
  const payload = await response.json();
  return {response, payload, elapsed};
}

function parseTextArea(textarea) {
  if (!textarea.value.trim()) {
    throw new Error("Введите JSON-запрос");
  }
  try {
    return JSON.parse(textarea.value);
  } catch (error) {
    throw new Error(`JSON не распознан: ${error.message}`);
  }
}

async function sendInference() {
  const button = document.querySelector("#sendRequest");
  let parsed;
  try {
    parsed = parseTextArea(requestBody);
  } catch (error) {
    setPanelResponse({body: responseBody, meta: responseMeta}, error.message, "ошибка клиента");
    return;
  }

  const target = modelSelect.value || "stateful_python_backend";
  responseMeta.textContent = "запрос выполняется";
  setButtonBusy(button, true, "Выполняется...");
  switchTab("inference");
  try {
    const {response, payload, elapsed} = await postJson(`/api/infer/${encodeURIComponent(target)}`, parsed);
    setPanelResponse({body: responseBody, meta: responseMeta}, payload, `${response.status} · ${elapsed}ms`, Boolean(payload.flag));
  } catch (error) {
    setPanelResponse({body: responseBody, meta: responseMeta}, error.message, "ошибка сети");
  } finally {
    setButtonBusy(button, false, "");
  }
}

async function readSharedMemory() {
  const button = document.querySelector("#readMemory");
  let parsed;
  try {
    parsed = parseTextArea(memoryBody);
  } catch (error) {
    setPanelResponse({body: memoryResponseBody, meta: memoryMeta}, error.message, "ошибка клиента");
    return;
  }

  memoryMeta.textContent = "запрос выполняется";
  setButtonBusy(button, true, "Выполняется...");
  switchTab("memory");
  try {
    const {response, payload, elapsed} = await postJson("/api/shared-memory/read", parsed);
    setPanelResponse({body: memoryResponseBody, meta: memoryMeta}, payload, `${response.status} · ${elapsed}ms`, response.ok);
  } catch (error) {
    setPanelResponse({body: memoryResponseBody, meta: memoryMeta}, error.message, "ошибка сети");
  } finally {
    setButtonBusy(button, false, "");
  }
}

async function runDebug() {
  const button = document.querySelector("#runDebug");
  let parsed;
  try {
    parsed = parseTextArea(debugBody);
  } catch (error) {
    setPanelResponse({body: debugResponseBody, meta: debugMeta}, error.message, "ошибка клиента");
    return;
  }

  debugMeta.textContent = "диагностика выполняется";
  setButtonBusy(button, true, "Выполняется...");
  switchTab("debug");
  try {
    const {response, payload, elapsed} = await postJson("/api/debug", parsed);
    setPanelResponse({body: debugResponseBody, meta: debugMeta}, payload, `${response.status} · ${elapsed}ms`, Boolean(payload.flag));
  } catch (error) {
    setPanelResponse({body: debugResponseBody, meta: debugMeta}, error.message, "ошибка сети");
  } finally {
    setButtonBusy(button, false, "");
  }
}

document.querySelector("#sendRequest").addEventListener("click", sendInference);
document.querySelector("#readMemory").addEventListener("click", readSharedMemory);
document.querySelector("#runDebug").addEventListener("click", runDebug);

for (const button of tabButtons) {
  button.addEventListener("click", () => switchTab(button.dataset.tabTarget));
}

checkHealth();
loadModels();
