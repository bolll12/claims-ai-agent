const state = { documents: [], history: [], pendingFiles: [], busy: false };
const $ = (id) => document.getElementById(id);

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* 保留状态码 */ }
    throw new Error(detail);
  }
  return response;
}

async function checkHealth() {
  try {
    await api("/health");
    $("healthDot").className = "online";
    $("healthText").textContent = "服务运行正常";
  } catch (_) {
    $("healthDot").className = "offline";
    $("healthText").textContent = "服务暂不可用";
  }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function scrollToBottom() {
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
}

function fileCards(files) {
  if (!files.length) return "";
  return `<div class="attachment-list">${files.map((file) => `<div class="attachment-card"><strong>${escapeHtml(file.name)}</strong><span>${(file.size / 1024).toFixed(1)} KB</span></div>`).join("")}</div>`;
}

function addUserMessage(content, files = []) {
  const article = document.createElement("article");
  article.className = "message user";
  article.innerHTML = `<div class="message-body">${fileCards(files)}<div class="bubble"><p>${escapeHtml(content)}</p></div></div>`;
  $("chatMessages").appendChild(article);
  scrollToBottom();
}

function addAssistantMessage() {
  const article = document.createElement("article");
  article.className = "message assistant";
  article.innerHTML = '<div class="avatar" aria-hidden="true">理</div><div class="message-body"><div class="intent" hidden></div><div class="bubble"><p>正在分析…</p></div><div class="document-details" hidden></div></div>';
  $("chatMessages").appendChild(article);
  scrollToBottom();
  return article;
}

function renderDocumentDetails(node, documents) {
  if (!documents.length) return;
  node.hidden = false;
  node.innerHTML = documents.map((doc) => {
    const fields = Object.entries(doc.fields || {}).map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("");
    const warnings = (doc.warnings || []).map((item) => `<div class="document-warning">需核实：${escapeHtml(item)}</div>`).join("");
    const confidence = doc.confidence == null ? "置信度未知" : `置信度 ${Math.round(doc.confidence * 100)}%`;
    return `<div><strong>${escapeHtml(doc.file_name)}</strong> · ${escapeHtml(doc.document_type)} · ${confidence}<p>${escapeHtml(doc.summary)}</p>${fields ? `<dl>${fields}</dl>` : ""}${warnings}</div>`;
  }).join("");
}

function renderPendingFiles() {
  const container = $("pendingFiles");
  container.hidden = !state.pendingFiles.length;
  container.innerHTML = state.pendingFiles.map((file, index) => `<div class="file-chip"><span>${escapeHtml(file.name)}</span><button type="button" data-index="${index}" aria-label="移除 ${escapeHtml(file.name)}">×</button></div>`).join("");
  container.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
    state.pendingFiles.splice(Number(button.dataset.index), 1);
    renderPendingFiles();
  }));
}

function selectFiles(files) {
  const selected = [...files];
  if (state.pendingFiles.length + selected.length > 6) { toast("每轮最多上传 6 个附件"); return; }
  const tooLarge = selected.find((file) => file.size > 10 * 1024 * 1024);
  if (tooLarge) { toast(`${tooLarge.name} 超过 10MB`); return; }
  state.pendingFiles.push(...selected);
  renderPendingFiles();
  $("fileInput").value = "";
}

async function analyzeFiles(files) {
  if (!files.length) return [];
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const response = await api("/api/documents/analyze", { method: "POST", body: form });
  return (await response.json()).documents;
}

async function streamAnswer(question, newDocuments, article) {
  const answer = article.querySelector(".bubble p");
  const intent = article.querySelector(".intent");
  const response = await api("/api/assistant/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, documents: state.documents, history: state.history.slice(-12) }),
  });
  answer.textContent = "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let detectedIntent = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const event of events) {
      const line = event.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const data = JSON.parse(line.slice(6));
      if (data.error) throw new Error(data.error);
      if (data.intent) {
        detectedIntent = data.intent;
        intent.hidden = false;
        intent.textContent = `${data.intent} · ${Math.round(data.intent_confidence * 100)}%`;
      }
      if (data.content) answer.textContent += data.content;
    }
    scrollToBottom();
  }
  if (!answer.textContent) answer.textContent = "模型未返回有效内容，请稍后重试。";
  renderDocumentDetails(article.querySelector(".document-details"), newDocuments);
  state.history.push(
    { role: "user", content: question },
    { role: "assistant", content: answer.textContent, intent: detectedIntent },
  );
}

async function sendMessage(rawQuestion) {
  if (state.busy) return;
  const files = [...state.pendingFiles];
  const question = rawQuestion.trim() || (files.length ? "请识别并总结我上传的理赔单证。" : "");
  if (!question) return;
  state.busy = true;
  $("sendQuestion").disabled = true;
  state.pendingFiles = [];
  renderPendingFiles();
  addUserMessage(question, files);
  const article = addAssistantMessage();
  try {
    const documents = await analyzeFiles(files);
    state.documents.push(...documents);
    await streamAnswer(question, documents, article);
  } catch (error) {
    article.classList.add("error");
    article.querySelector(".bubble p").textContent = error.message;
  } finally {
    state.busy = false;
    $("sendQuestion").disabled = false;
    scrollToBottom();
  }
}

$("attachButton").addEventListener("click", () => $("fileInput").click());
$("fileInput").addEventListener("change", (event) => selectFiles(event.target.files));
$("chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("question");
  const value = input.value;
  input.value = "";
  input.style.height = "auto";
  sendMessage(value);
});
$("question").addEventListener("input", (event) => {
  event.target.style.height = "auto";
  event.target.style.height = `${Math.min(event.target.scrollHeight, 150)}px`;
});
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("chatForm").requestSubmit();
  }
});
$("newChat").addEventListener("click", () => {
  state.documents = [];
  state.history = [];
  state.pendingFiles = [];
  renderPendingFiles();
  $("chatMessages").innerHTML = '<article class="message assistant"><div class="avatar" aria-hidden="true">理</div><div class="message-body"><div class="bubble"><p>新对话已开始。请描述你的问题或上传理赔单证。</p></div></div></article>';
});
document.querySelectorAll(".quick-actions button").forEach((button) => button.addEventListener("click", () => sendMessage(button.textContent)));

checkHealth();
