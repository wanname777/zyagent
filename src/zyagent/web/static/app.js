const state = {
  sessions: [],
  current: null,
  busy: false,
  sidebarOpen: false,
  theme: localStorage.getItem("zyagent-theme") || "harvest",
};

const mobileViewport = window.matchMedia("(max-width: 760px)");

const elements = {
  sidebar: document.querySelector("#sidebar"),
  sidebarOverlay: document.querySelector("#sidebar-overlay"),
  openSidebar: document.querySelector("#open-sidebar"),
  closeSidebar: document.querySelector("#close-sidebar"),
  newSession: document.querySelector("#new-session"),
  sessionList: document.querySelector("#session-list"),
  sessionCount: document.querySelector("#session-count"),
  connectionLight: document.querySelector("#connection-light"),
  connectionLabel: document.querySelector("#connection-label"),
  modelLabel: document.querySelector("#model-label"),
  conversationTitle: document.querySelector("#conversation-title"),
  activeCount: document.querySelector("#active-count"),
  totalCount: document.querySelector("#total-count"),
  refreshSession: document.querySelector("#refresh-session"),
  openCompress: document.querySelector("#open-compress"),
  summaryBanner: document.querySelector("#summary-banner"),
  summaryText: document.querySelector("#summary-text"),
  toggleSummary: document.querySelector("#toggle-summary"),
  messages: document.querySelector("#messages"),
  emptyState: document.querySelector("#empty-state"),
  composer: document.querySelector("#composer"),
  messageInput: document.querySelector("#message-input"),
  sendMessage: document.querySelector("#send-message"),
  compressDialog: document.querySelector("#compress-dialog"),
  compressForm: document.querySelector("#compress-form"),
  keepRecent: document.querySelector("#keep-recent"),
  keepRecentValue: document.querySelector("#keep-recent-value"),
  confirmCompress: document.querySelector("#confirm-compress"),
  themeDialog: document.querySelector("#theme-dialog"),
  openTheme: document.querySelector("#open-theme"),
  themeOptions: document.querySelector("#theme-options"),
  toastRegion: document.querySelector("#toast-region"),
};

function createIcon(name, className = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("icon");
  if (className) {
    svg.classList.add(className);
  }
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `/icons.svg#${name}`);
  svg.append(use);
  return svg;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || "请求失败");
  }
  return payload;
}

async function initialize() {
  applyTheme(state.theme);
  bindEvents();
  try {
    const [health] = await Promise.all([api("/api/health"), refreshSessions()]);
    elements.connectionLight.classList.add("is-online");
    elements.connectionLabel.textContent = "田埂在线";
    elements.modelLabel.textContent = health.model;
  } catch (error) {
    elements.connectionLight.classList.add("is-error");
    elements.connectionLabel.textContent = "连接失败";
    elements.modelLabel.textContent = "检查本地服务";
    showToast(error.message, true);
  }
}

function bindEvents() {
  elements.newSession.addEventListener("click", createSession);
  elements.composer.addEventListener("submit", sendMessage);
  elements.messageInput.addEventListener("input", resizeComposer);
  elements.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      elements.composer.requestSubmit();
    }
  });
  elements.refreshSession.addEventListener("click", () => {
    if (state.current) {
      selectSession(state.current.id, true);
    } else {
      refreshSessions();
    }
  });
  elements.openCompress.addEventListener("click", openCompressDialog);
  elements.compressForm.addEventListener("submit", compressSession);
  elements.keepRecent.addEventListener("input", () => {
    elements.keepRecentValue.value = elements.keepRecent.value;
  });
  elements.toggleSummary.addEventListener("click", () => {
    elements.summaryBanner.classList.toggle("is-expanded");
  });
  elements.openTheme.addEventListener("click", () => elements.themeDialog.showModal());
  elements.themeOptions.addEventListener("click", (event) => {
    const option = event.target.closest("[data-theme-value]");
    if (!option) {
      return;
    }
    applyTheme(option.dataset.themeValue);
    elements.themeDialog.close();
  });
  document.querySelectorAll(".dialog-close, .dialog-cancel").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });
  elements.openSidebar.addEventListener("click", () => setSidebar(true));
  elements.closeSidebar.addEventListener("click", () => setSidebar(false));
  elements.sidebarOverlay.addEventListener("click", () => setSidebar(false));
  mobileViewport.addEventListener("change", () => setSidebar(false));
  setSidebar(false);
}

async function refreshSessions(selectLatest = true) {
  const payload = await api("/api/sessions");
  state.sessions = payload.sessions;
  renderSessionList();
  if (!state.current && state.sessions.length && selectLatest) {
    await selectSession(state.sessions[0].id);
  }
}

async function createSession() {
  if (state.busy) {
    return;
  }
  setBusy(true);
  try {
    const payload = await api("/api/sessions", {
      method: "POST",
      body: "{}",
    });
    state.current = payload.session;
    await refreshSessions(false);
    renderCurrentSession();
    setSidebar(false);
    elements.messageInput.focus();
    showToast("新日志已经铺好");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function selectSession(sessionId, announce = false) {
  if (state.busy) {
    return;
  }
  try {
    const payload = await api(`/api/sessions/${encodeURIComponent(sessionId)}`);
    state.current = payload.session;
    renderCurrentSession();
    renderSessionList();
    setSidebar(false);
    if (announce) {
      showToast("日志已刷新");
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderSessionList() {
  elements.sessionList.replaceChildren();
  elements.sessionCount.textContent = String(state.sessions.length);
  if (!state.sessions.length) {
    const empty = document.createElement("p");
    empty.className = "session-list-empty";
    empty.textContent = "还没有日志";
    elements.sessionList.append(empty);
    return;
  }

  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-item";
    button.dataset.sessionId = session.id;
    button.setAttribute("aria-current", String(state.current?.id === session.id));
    button.addEventListener("click", () => selectSession(session.id));

    const title = document.createElement("span");
    title.className = "session-item__title";
    title.textContent = session.title;
    const count = document.createElement("span");
    count.className = "session-item__count";
    count.textContent = String(session.message_count);
    const preview = document.createElement("span");
    preview.className = "session-item__preview";
    preview.textContent = session.preview;
    button.append(title, count, preview);

    if (session.parent_session_id) {
      const branch = document.createElement("span");
      branch.className = "session-item__branch";
      branch.append(createIcon("git-branch"), document.createTextNode("分支"));
      button.append(branch);
    }
    elements.sessionList.append(button);
  }
}

function renderCurrentSession() {
  const session = state.current;
  if (!session) {
    elements.conversationTitle.textContent = "新会话";
    elements.activeCount.textContent = "0 活跃";
    elements.totalCount.textContent = "0 总计";
    elements.openCompress.disabled = true;
    elements.summaryBanner.hidden = true;
    elements.messages.replaceChildren(elements.emptyState);
    elements.emptyState.hidden = false;
    return;
  }

  elements.conversationTitle.textContent = session.title;
  elements.activeCount.textContent = `${session.active_message_count} 活跃`;
  elements.totalCount.textContent = `${session.message_count} 总计`;
  elements.openCompress.disabled = session.active_message_count <= 1 || state.busy;
  renderSummary(session);
  renderMessages(session);
}

function renderSummary(session) {
  if (!session.summary) {
    elements.summaryBanner.hidden = true;
    elements.summaryBanner.classList.remove("is-expanded");
    return;
  }
  elements.summaryText.textContent = session.summary;
  elements.summaryBanner.hidden = false;
}

function renderMessages(session, optimisticText = "") {
  elements.messages.replaceChildren();
  if (!session.messages.length && !optimisticText) {
    elements.emptyState.hidden = false;
    elements.messages.append(elements.emptyState);
    return;
  }
  elements.emptyState.hidden = true;

  const results = new Map(
    session.messages
      .filter((message) => message.type === "tool_result")
      .map((message) => [message.tool_call_id, message]),
  );
  for (const message of session.messages) {
    if (message.type === "tool_result") {
      continue;
    }
    elements.messages.append(renderMessage(message, results));
  }
  if (optimisticText) {
    elements.messages.append(
      renderMessage({
        id: "optimistic-user",
        type: "user",
        text: optimisticText,
        created_at: new Date().toISOString(),
      }, results, false),
      renderLoadingMessage(),
    );
  }
  requestAnimationFrame(() => {
    elements.messages.scrollTop = elements.messages.scrollHeight;
  });
}

function renderMessage(message, results, allowBranch = true) {
  const article = document.createElement("article");
  article.className = `message message--${message.type}`;
  article.dataset.messageId = message.id;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.append(createIcon(message.type === "user" ? "user" : "bot"));

  const content = document.createElement("div");
  content.className = "message-content";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  const text = document.createElement("div");
  text.className = "message-text";
  appendRichText(text, message.text || "");
  bubble.append(text);
  content.append(bubble);

  if (message.tool_calls?.length) {
    content.append(renderToolTasks(message.tool_calls, results));
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const time = document.createElement("time");
  time.dateTime = message.created_at;
  time.textContent = formatTime(message.created_at);
  meta.append(time);
  if (allowBranch) {
    const branch = document.createElement("button");
    branch.type = "button";
    branch.className = "branch-button";
    branch.title = "从这条消息分支";
    branch.append(createIcon("git-branch"), document.createTextNode("分支"));
    branch.addEventListener("click", () => branchFromMessage(message.id));
    meta.append(branch);
  }
  content.append(meta);
  article.append(avatar, content);
  return article;
}

function renderToolTasks(toolCalls, results) {
  const container = document.createElement("div");
  container.className = "tool-tasks";
  for (const call of toolCalls) {
    const result = results.get(call.id);
    const details = document.createElement("details");
    details.className = "tool-task";
    if (result?.is_error) {
      details.classList.add("is-error");
    }
    const summary = document.createElement("summary");
    summary.append(
      createIcon("terminal"),
      document.createTextNode(call.name),
    );
    const status = document.createElement("span");
    status.className = "tool-task__status";
    status.title = result?.is_error ? "执行失败" : "执行完成";
    summary.append(status);
    const argumentsBlock = document.createElement("pre");
    argumentsBlock.textContent = JSON.stringify(call.arguments, null, 2);
    details.append(summary, argumentsBlock);
    if (result) {
      const resultBlock = document.createElement("div");
      resultBlock.className = "tool-task__result";
      resultBlock.textContent = result.content;
      details.append(resultBlock);
    }
    container.append(details);
  }
  return container;
}

function renderLoadingMessage() {
  const article = document.createElement("article");
  article.className = "message message--assistant loading-message";
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.append(createIcon("bot"));
  const content = document.createElement("div");
  content.className = "message-content";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.append(createIcon("loader-circle"), document.createTextNode("正在翻信…"));
  content.append(bubble);
  article.append(avatar, content);
  return article;
}

function appendRichText(container, value) {
  const codePattern = /```([^\n]*)\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match;
  while ((match = codePattern.exec(value)) !== null) {
    appendParagraphs(container, value.slice(cursor, match.index));
    appendCodeBlock(container, match[2].replace(/\n$/, ""));
    cursor = match.index + match[0].length;
  }
  appendParagraphs(container, value.slice(cursor));
  if (!container.childNodes.length) {
    appendParagraphs(container, value);
  }
}

function appendParagraphs(container, value) {
  const chunks = value.split(/\n{2,}/).filter((chunk) => chunk.length);
  for (const chunk of chunks) {
    const lines = chunk.split("\n");
    if (lines.length && lines.every((line) => line.trimStart().startsWith("- "))) {
      const list = document.createElement("ul");
      for (const line of lines) {
        const item = document.createElement("li");
        appendInlineText(item, line.trimStart().slice(2));
        list.append(item);
      }
      container.append(list);
      continue;
    }
    const paragraph = document.createElement("p");
    lines.forEach((line, index) => {
      if (index) {
        paragraph.append(document.createElement("br"));
      }
      appendInlineText(paragraph, line);
    });
    container.append(paragraph);
  }
}

function appendInlineText(container, value) {
  const inlinePattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let cursor = 0;
  let match;
  while ((match = inlinePattern.exec(value)) !== null) {
    container.append(document.createTextNode(value.slice(cursor, match.index)));
    const token = match[0];
    const element = document.createElement(
      token.startsWith("**") ? "strong" : "code",
    );
    element.textContent = token.startsWith("**")
      ? token.slice(2, -2)
      : token.slice(1, -1);
    container.append(element);
    cursor = match.index + token.length;
  }
  container.append(document.createTextNode(value.slice(cursor)));
}

function appendCodeBlock(container, value) {
  const pre = document.createElement("pre");
  const code = document.createElement("code");
  code.textContent = value;
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "icon-button copy-code";
  copy.title = "复制代码";
  copy.setAttribute("aria-label", "复制代码");
  copy.append(createIcon("copy"));
  copy.addEventListener("click", async () => {
    await navigator.clipboard.writeText(value);
    showToast("代码已复制");
  });
  pre.append(code, copy);
  container.append(pre);
}

async function sendMessage(event) {
  event.preventDefault();
  const text = elements.messageInput.value.trim();
  if (!text || state.busy) {
    return;
  }
  setBusy(true);
  elements.messageInput.value = "";
  resizeComposer();
  try {
    if (!state.current) {
      const created = await api("/api/sessions", { method: "POST", body: "{}" });
      state.current = created.session;
    }
    renderMessages(state.current, text);
    const payload = await api(
      `/api/sessions/${encodeURIComponent(state.current.id)}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ text }),
      },
    );
    state.current = payload.session;
    await refreshSessions(false);
    renderCurrentSession();
  } catch (error) {
    renderCurrentSession();
    showToast(error.message, true);
  } finally {
    setBusy(false);
    elements.messageInput.focus();
  }
}

async function branchFromMessage(messageId) {
  if (!state.current || state.busy) {
    return;
  }
  setBusy(true);
  try {
    const payload = await api(
      `/api/sessions/${encodeURIComponent(state.current.id)}/branches`,
      {
        method: "POST",
        body: JSON.stringify({ message_id: messageId }),
      },
    );
    state.current = payload.session;
    await refreshSessions(false);
    renderCurrentSession();
    showToast("新的分支日志已生成");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function openCompressDialog() {
  if (!state.current || state.current.active_message_count <= 1) {
    return;
  }
  const maximum = Math.max(1, state.current.active_message_count - 1);
  const value = Math.min(12, maximum);
  elements.keepRecent.max = String(maximum);
  elements.keepRecent.value = String(value);
  elements.keepRecentValue.value = String(value);
  elements.compressDialog.showModal();
}

async function compressSession(event) {
  event.preventDefault();
  if (!state.current || state.busy) {
    return;
  }
  elements.compressDialog.close();
  setBusy(true);
  try {
    const payload = await api(
      `/api/sessions/${encodeURIComponent(state.current.id)}/compress`,
      {
        method: "POST",
        body: JSON.stringify({
          keep_recent: Number.parseInt(elements.keepRecent.value, 10),
        }),
      },
    );
    state.current = payload.session;
    await refreshSessions(false);
    renderCurrentSession();
    showToast("旧消息已经收进记忆粮仓");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function setBusy(value) {
  state.busy = value;
  elements.sendMessage.disabled = value;
  elements.newSession.disabled = value;
  elements.refreshSession.disabled = value;
  elements.openCompress.disabled =
    value || !state.current || state.current.active_message_count <= 1;
  elements.messageInput.disabled = value;
}

function resizeComposer() {
  const wrappedLines = Math.ceil(elements.messageInput.value.length / 72);
  const explicitLines = elements.messageInput.value.split("\n").length;
  elements.messageInput.rows = Math.min(6, Math.max(1, wrappedLines, explicitLines));
}

function setSidebar(open) {
  const isOpen = mobileViewport.matches ? open : true;
  state.sidebarOpen = isOpen;
  elements.sidebar.classList.toggle("is-open", isOpen);
  elements.sidebar.toggleAttribute("inert", mobileViewport.matches && !isOpen);
  elements.sidebar.setAttribute(
    "aria-hidden",
    String(mobileViewport.matches && !isOpen),
  );
  elements.sidebarOverlay.hidden = !mobileViewport.matches || !isOpen;
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("zyagent-theme", theme);
  document.querySelectorAll("[data-theme-value]").forEach((option) => {
    option.setAttribute("aria-checked", String(option.dataset.themeValue === theme));
  });
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = `toast${isError ? " toast--error" : ""}`;
  toast.append(
    createIcon(isError ? "circle-alert" : "check"),
    document.createTextNode(message),
  );
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 3200);
}

initialize();
