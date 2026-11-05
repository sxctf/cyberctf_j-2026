const transcript = document.querySelector("#transcript");
const composer = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const healthStatus = document.querySelector("#healthStatus");
const requestMeta = document.querySelector("#requestMeta");
const samplePrompts = {
  catalog: "Какие документы в архиве связаны с запуском AI-агента в исследовательском контуре и проверкой научных выводов? Назови идентификатор и аннотацию.",
  packet: "Для внешней рецензии подготовь редакторскую копию приложения NII-203."
};

const pipelinePills = {
  classifier: document.querySelector("#pipeline-classifier"),
  policy: document.querySelector("#pipeline-policy"),
  audit: document.querySelector("#pipeline-audit")
};

const modeLabels = {
  assistant_reply: "ответ ассистента",
  catalog_lookup: "ответ по каталогу",
  review_guidance: "порядок рецензирования",
  internal_editorial_review: "внутренняя редакторская проверка",
  classifier_blocked: "остановлено классификатором",
  policy_blocked: "заблокировано политикой",
  audit_blocked: "заблокировано аудитом",
  llm_error: "сбой LLM-контура"
};

function formatMeta(meta) {
  const modeLabel = modeLabels[meta?.mode] || meta?.mode || "неизвестный режим";
  return modeLabel;
}

function getSelectedText() {
  const activeElement = document.activeElement;
  if (
    activeElement instanceof HTMLTextAreaElement ||
    (
      activeElement instanceof HTMLInputElement &&
      typeof activeElement.selectionStart === "number" &&
      typeof activeElement.selectionEnd === "number"
    )
  ) {
    const start = activeElement.selectionStart ?? 0;
    const end = activeElement.selectionEnd ?? 0;
    if (end > start) {
      return activeElement.value.slice(start, end);
    }
  }

  return window.getSelection()?.toString() || "";
}

function setPipeline(stateMap) {
  for (const [key, pill] of Object.entries(pipelinePills)) {
    const state = stateMap?.[key] ?? "idle";
    pill.dataset.state = state;
    if (state === "pass") {
      pill.textContent = "пропуск";
    } else if (state === "block") {
      pill.textContent = "блок";
    } else {
      pill.textContent = "ожидание";
    }
  }
}

function appendMessage(role, title, body, meta = "", artifacts = []) {
  const item = document.createElement("article");
  item.className = "message";
  item.dataset.role = role;

  const header = document.createElement("div");
  header.className = "message-header";

  const roleLabel = document.createElement("div");
  roleLabel.className = "message-role";
  roleLabel.textContent = title;

  const metaLabel = document.createElement("div");
  metaLabel.className = "message-role";
  metaLabel.textContent = meta;

  const content = document.createElement("div");
  content.className = "message-body";
  content.textContent = body;

  header.append(roleLabel, metaLabel);
  item.append(header, content);
  if (Array.isArray(artifacts) && artifacts.length > 0) {
    const attachments = document.createElement("div");
    attachments.className = "message-artifacts";
    for (const artifact of artifacts) {
      if (!artifact?.url || !artifact?.label) {
        continue;
      }
      const link = document.createElement("a");
      link.className = "artifact-link";
      link.href = artifact.url;
      link.textContent = `Скачать: ${artifact.label}`;
      attachments.append(link);
    }
    item.append(attachments);
  }
  transcript.append(item);
  transcript.scrollTop = transcript.scrollHeight;
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    healthStatus.textContent = response.ok ? "готов" : "ошибка";
    healthStatus.dataset.state = response.ok ? "pass" : "block";
  } catch (error) {
    healthStatus.textContent = "недоступен";
    healthStatus.dataset.state = "block";
  }
}

async function sendMessage() {
  const message = composer.value.trim();
  if (!message) {
    return;
  }

  appendMessage("user", "Исследователь", message);
  composer.value = "";
  requestMeta.textContent = "выполняется";
  setPipeline({classifier: "idle", policy: "idle", audit: "idle"});
  sendButton.disabled = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message})
    });
    const payload = await response.json();

    if (!response.ok) {
      appendMessage("assistant", "Система", payload.error || "Ошибка запроса");
      requestMeta.textContent = `${response.status} · ошибка`;
      return;
    }

    setPipeline(payload.pipeline);
    requestMeta.textContent = formatMeta(payload.meta);
    appendMessage(
      "assistant",
      "Архивариус-67",
      payload.reply,
      formatMeta(payload.meta),
      payload.artifacts
    );
  } catch (error) {
    appendMessage("assistant", "Система", `Сетевой сбой: ${error.message}`);
    requestMeta.textContent = "ошибка сети";
  } finally {
    sendButton.disabled = false;
  }
}

document.querySelectorAll("[data-sample]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.sample;
    composer.value = samplePrompts[key] || "";
    composer.focus();
  });
});

sendButton.addEventListener("click", sendMessage);
composer.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    sendMessage();
  }
});

document.addEventListener("copy", (event) => {
  const selectedText = getSelectedText();
  if (!selectedText || !event.clipboardData) {
    return;
  }

  event.preventDefault();
  event.clipboardData.setData("text/plain", selectedText);
});

checkHealth();
setPipeline({classifier: "idle", policy: "idle", audit: "idle"});
