const state = { claimId: null, documents: [], history: [], pendingFiles: [], busy: false, isDemo: false };
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
  $("chatMessages").scrollTo({ top: $("chatMessages").scrollHeight, behavior: "smooth" });
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
  if (!selected.length) return;
  if (state.pendingFiles.length + selected.length > 6) { toast("每轮最多上传 6 个附件"); return; }
  const tooLarge = selected.find((file) => file.size > 10 * 1024 * 1024);
  if (tooLarge) { toast(`${tooLarge.name} 超过 10MB`); return; }
  if (state.isDemo) {
    state.claimId = null;
    state.documents = [];
    state.history = [];
    state.isDemo = false;
    toast("已退出演示案件，将使用真实附件解析");
  }
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
    body: JSON.stringify({ question, claim_id: state.claimId, documents: state.documents, history: state.history.slice(-12) }),
  });
  answer.textContent = "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let detectedIntent = null;
  let completed = false;
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
      if (data.trace) updateTrace(data.trace);
      if (data.done) { completed = true; traceNode("output", "done", "回答已完成"); $("traceStatus").textContent = "执行完成"; }
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
  if (!completed) throw new Error("连接中断，回答未完成，请重试。");
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
  $("newChat").disabled = true;
  resetTrace();
  $("traceStatus").textContent = "执行中";
  traceNode("input", "done", "已接收本轮问题");
  const fileMeta = files.map(file => ({name: file.name, size: file.size, type: file.type}));
  setTraceParams("input", {question, files: fileMeta}, {question, history_count: state.history.slice(-12).length});
  setTraceParams("documents", {files: fileMeta}, files.length ? undefined : {skipped: true, reason: "本轮无新附件"});
  traceNode("documents", files.length ? "running" : "skipped", files.length ? `正在识别 ${files.length} 份附件` : "本轮无新附件");
  $("sendQuestion").disabled = true;
  state.pendingFiles = [];
  renderPendingFiles();
  addUserMessage(question, files);
  const article = addAssistantMessage();
  try {
    const uploadStarted = performance.now();
    const documents = await analyzeFiles(files);
    if (files.length) traceNode("documents", "done", `${documents.length} 份真实附件 · ${Math.round(performance.now() - uploadStarted)} ms（含模型识别）`);
    if (files.length) setTraceParams("documents", undefined, {documents});
    state.documents.push(...documents);
    state.documents = state.documents.slice(-6);
    await streamAnswer(question, documents, article);
  } catch (error) {
    document.querySelectorAll(".trace-node.running").forEach(node => { traceNode(node.dataset.node, "error", "调用失败"); setTraceParams(node.dataset.node, undefined, {error: error.message}); });
    traceNode("output", "error", error.message);
    $("traceStatus").textContent = "执行失败";
    article.classList.add("error");
    article.querySelector(".bubble p").textContent = error.message;
  } finally {
    state.busy = false;
    $("newChat").disabled = false;
    $("sendQuestion").disabled = false;
    scrollToBottom();
  }
}

async function runDemoClaim() {
  if (state.busy) return;
  state.busy = true;
  $("newChat").disabled = true;
  $("demoCase").disabled = true;
  $("sendQuestion").disabled = true;
  resetTrace();
  $("traceStatus").textContent = "运行演示案件";
  const article = addAssistantMessage();
  try {
    const response = await api("/api/demo/claims/process", { method: "POST" });
    const data = await response.json();
    state.claimId = data.claim.claim_id;
    state.documents = data.documents;
    state.history = [];
    state.isDemo = true;
    traceNode("input", "done", `合成案件 ${data.claim.claim_id}`);
    setTraceParams("input", {source: "本地合成演示数据"}, data.claim);
    traceNode("documents", "done", `${data.documents.length} 份合成单证`);
    setTraceParams("documents", {source: "演示数据"}, {documents: data.documents});
    traceNode("classification", "skipped", "演示案件直接进入正式理赔状态机");
    setTraceParams("classification", {mode: "demo"}, {skipped: true});
    updateTrace({node: "route", status: "done", selected: "claims", input: {mode: "demo"}, output: {selected: "claims"}});
    traceNode("claims", "running", "正在运行合成理赔状态机");
    data.trace.forEach(updateTrace);
    const decision = {accept: "受理建议", review: "人工复核", reject: "不受理建议", investigate: "调查核实"}[data.result.decision] || data.result.decision;
    traceNode("claims", "done", `演示决策：${decision}`);
    setTraceParams("claims", data.claim, data.result);
    traceNode("output", "done", "演示案件运行完成");
    setTraceParams("output", data.result, {completed: true, demo: true});
    $("traceStatus").textContent = "演示完成";
    const confidence = data.result.confidence == null ? "" : `，置信度 ${Math.round(data.result.confidence * 100)}%`;
    article.querySelector(".intent").hidden = false;
    article.querySelector(".intent").textContent = "合成演示案件";
    article.querySelector(".bubble p").textContent = `案件 ${data.result.claim_id}：${data.result.message} 决策 ${decision}${confidence}。`;
    renderDocumentDetails(article.querySelector(".document-details"), data.documents);
  } catch (error) {
    article.classList.add("error");
    article.querySelector(".bubble p").textContent = error.message;
    traceNode("output", "error", error.message);
    $("traceStatus").textContent = "演示失败";
  } finally {
    state.busy = false;
    $("newChat").disabled = false;
    $("demoCase").disabled = false;
    $("sendQuestion").disabled = false;
    scrollToBottom();
  }
}

$("attachButton").addEventListener("click", () => $("fileInput").click());
$("demoCase").addEventListener("click", runDemoClaim);
$("fileInput").addEventListener("change", (event) => selectFiles(event.target.files));
$("chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.busy) return;
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
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("chatForm").requestSubmit();
  }
});
$("newChat").addEventListener("click", () => {
  if (state.busy) return;
  resetTrace();
  state.claimId = null;
  state.documents = [];
  state.history = [];
  state.isDemo = false;
  state.pendingFiles = [];
  renderPendingFiles();
  $("chatMessages").innerHTML = '<article class="message assistant"><div class="avatar" aria-hidden="true">理</div><div class="message-body"><div class="bubble"><p>新对话已开始。请描述你的问题或上传理赔单证。</p></div></div></article>';
});
document.querySelectorAll(".quick-actions button").forEach((button) => button.addEventListener("click", () => sendMessage(button.textContent)));

const traceNames = {
  input: "接收消息", documents: "附件识别", classification: "多轮意图识别",
  route: "选择回答链路", claims: "理赔智能体", general: "通用基模", output: "返回回答",
  claim_intake: "报案信息核查", claim_documents: "理赔单证核查", claim_policy: "保单与责任核验",
  claim_damage: "损失专家", claim_risk: "风险专家", claim_liability: "责任专家",
  claim_confidence: "置信度计算", claim_decision: "审核决策路由",
};
const claimTraceNodes = [
  "claim_intake", "claim_documents", "claim_policy", "claim_damage", "claim_risk",
  "claim_liability", "claim_confidence", "claim_decision",
];
function setTraceParams(id, input, output) {
  const node = document.querySelector(`[data-node="${id}"]`);
  if (!node) return;
  for (const [kind, value] of Object.entries({input, output})) {
    if (value !== undefined) node.querySelector(`[data-param="${kind}"]`).textContent = JSON.stringify(redactTrace(value), null, 2);
  }
}
function redactTrace(value) {
  if (Array.isArray(value)) return value.map(redactTrace);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, val]) => [
    key, /api.?key|password|secret|authorization|身份证|银行卡|手机号|地址/i.test(key) ? "[已脱敏]" : redactTrace(val)
  ]));
  if (typeof value !== "string") return value;
  return value.replace(/sk-[A-Za-z0-9_-]+/g, "[密钥]").replace(/[0-9]{17}[0-9Xx]/g, "[身份证]").replace(/1[3-9][0-9]{9}/g, "[手机号]");
}
function traceNode(id, status, detail = "") {
  const node = document.querySelector(`[data-node="${id}"]`);
  if (!node) return;
  node.className = `trace-node ${status}`;
  node.querySelector(".node-state").textContent = {waiting:"等待", running:"执行中", done:"已完成", skipped:"未调用", error:"失败"}[status];
  if (detail) node.querySelector("small").textContent = detail;
}
const traceDetails = {};
function resetTrace() {
  Object.keys(traceDetails).forEach(key => delete traceDetails[key]);
  const node = (id, extraClass = "") => `<div class="trace-node ${extraClass}" data-node="${id}"><div class="node-head"><strong>${traceNames[id]}</strong><span class="node-state">等待</span></div><small>等待本轮执行</small><details class="trace-params"><summary>输入 / 输出参数</summary><h3>输入</h3><pre data-param="input">尚未调用</pre><h3>输出</h3><pre data-param="output">尚无输出</pre></details></div>`;
  const arrow = '<div class="trace-arrow" aria-hidden="true">↓</div>';
  const expertRow = `<div class="trace-parallel"><span>并行分析</span><div class="trace-experts">${["claim_damage", "claim_risk", "claim_liability"].map(id => node(id, "compact")).join("")}</div></div>`;
  const claimDetail = `<section id="claimTraceDetail" class="claim-trace-detail"><header><strong>理赔状态机明细</strong><span>对话预审 / 正式核赔节点</span></header>${node("claim_intake")}${arrow}${node("claim_documents")}${arrow}${node("claim_policy")}${arrow}${expertRow}${arrow}${node("claim_confidence")}${arrow}${node("claim_decision")}</section>`;
  $("traceGraph").innerHTML = ["input", "documents", "classification", "route"].map(node).join(arrow)
    + arrow + '<div class="trace-branches">' + node("claims") + node("general") + '</div>'
    + claimDetail + arrow + node("output");
  $("traceStatus").textContent = "等待提问";
}
function updateTrace(event) {
  traceDetails[event.node] = { ...traceDetails[event.node], ...event };
  event = traceDetails[event.node];
  const detail = [event.summary, event.model, event.intent,
    event.history_count != null ? `参考 ${event.history_count} 条历史消息` : "",
    event.elapsed_ms != null ? `${event.elapsed_ms} ms` : ""].filter(Boolean).join(" · ");
  traceNode(event.node, event.status, detail);
  setTraceParams(event.node, event.input, event.output);
  if (["claims", "general"].includes(event.node) && event.output) {
    setTraceParams("output", event.output, event.status === "done" ? {content: event.output.content, completed: true} : event.output);
  }
  if (event.node === "route") {
    traceNode("route", "done", event.selected === "general" ? "一般咨询 → 通用基模" : "理赔意图 → 理赔智能体");
    traceNode(event.selected === "general" ? "claims" : "general", "skipped", "本轮未选择此链路");
    const detail = $("claimTraceDetail");
    detail.classList.toggle("inactive", event.selected === "general");
    if (event.selected === "general") {
      claimTraceNodes.forEach(id => traceNode(id, "skipped", "一般咨询未进入理赔状态机"));
    }
  }
  if (["claims", "general"].includes(event.node) && event.status === "running") traceNode("output", "running", "等待并接收流式回答");
}
resetTrace();
checkHealth();
