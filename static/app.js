const state = { documents: [], history: [], busy: false };
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
    $("healthDot").className = "status-dot online";
    $("healthText").textContent = "服务运行正常";
  } catch (_) {
    $("healthDot").className = "status-dot offline";
    $("healthText").textContent = "服务暂不可用";
  }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function renderDocuments() {
  const list = $("documentList");
  $("fileCount").textContent = state.documents.length ? `已识别 ${state.documents.length} 份` : "尚未添加附件";
  if (!state.documents.length) {
    list.innerHTML = '<div class="empty-state"><span>暂无单证</span><p>上传发票、病历、事故证明或查勘照片后，识别结果会显示在这里。</p></div>';
    return;
  }
  list.innerHTML = state.documents.map((doc) => {
    const fields = Object.entries(doc.fields || {}).map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("");
    const warnings = (doc.warnings || []).map((item) => `<div class="warning">需核实：${escapeHtml(item)}</div>`).join("");
    const confidence = doc.confidence == null ? "置信度未知" : `置信度 ${Math.round(doc.confidence * 100)}%`;
    return `<article class="document-item"><div class="document-title"><div><strong>${escapeHtml(doc.file_name)}</strong><span>${escapeHtml(doc.document_type)}</span></div><span class="confidence">${confidence}</span></div><p class="document-summary">${escapeHtml(doc.summary)}</p>${fields ? `<dl class="field-table">${fields}</dl>` : ""}${warnings}</article>`;
  }).join("");
}

async function uploadFiles(files) {
  if (!files.length) return;
  if (files.length > 6) { toast("每次最多上传 6 个附件"); return; }
  const form = new FormData();
  [...files].forEach((file) => form.append("files", file));
  $("documentList").insertAdjacentHTML("afterbegin", `<div class="loading-row">正在识别 ${files.length} 份附件…</div>`);
  try {
    const response = await api("/api/documents/analyze", { method: "POST", body: form });
    const result = await response.json();
    state.documents.push(...result.documents);
    renderDocuments();
    toast("单证识别完成");
  } catch (error) {
    renderDocuments();
    toast(error.message);
  } finally {
    $("fileInput").value = "";
  }
}

async function submitClaim() {
  const payload = {
    claim_id: $("claimId").value.trim(),
    description: $("description").value.trim(),
  };
  const policyId = $("policyId").value.trim();
  const amount = $("amount").value.trim();
  if (policyId) payload.policy_id = policyId;
  if (amount) payload.amount = amount;
  if (!payload.claim_id || !payload.description) { toast("请填写案件编号和事故说明"); return; }
  const button = $("submitClaim");
  button.disabled = true;
  try {
    const response = await api("/api/claims/process", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const result = await response.json();
    $("claimStatus").hidden = false;
    $("statusLabel").textContent = result.phase.replaceAll("_", " ");
    $("statusMessage").textContent = result.message;
    toast("案件状态已更新");
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
}

function addMessage(role, content, extraClass = "") {
  const node = document.createElement("div");
  node.className = `message ${role} ${extraClass}`.trim();
  node.textContent = content;
  $("chatMessages").appendChild(node);
  $("chatMessages").scrollTop = $("chatMessages").scrollHeight;
  return node;
}

async function ask(question) {
  if (!question || state.busy) return;
  state.busy = true;
  $("sendQuestion").disabled = true;
  addMessage("user", question);
  const answer = addMessage("assistant", "正在思考…");
  try {
    const response = await api("/api/assistant/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, claim_id: $("claimId").value.trim() || null, documents: state.documents, history: state.history.slice(-12) }),
    });
    answer.textContent = "";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
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
        if (data.content) answer.textContent += data.content;
      }
      $("chatMessages").scrollTop = $("chatMessages").scrollHeight;
    }
    if (!answer.textContent) answer.textContent = "模型未返回有效内容，请稍后重试。";
    state.history.push({ role: "user", content: question }, { role: "assistant", content: answer.textContent });
  } catch (error) {
    answer.textContent = error.message;
    answer.classList.add("error");
  } finally {
    state.busy = false;
    $("sendQuestion").disabled = false;
  }
}

const dropZone = $("dropZone");
dropZone.addEventListener("click", () => $("fileInput").click());
dropZone.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); $("fileInput").click(); } });
dropZone.addEventListener("dragover", (event) => { event.preventDefault(); dropZone.classList.add("dragging"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); uploadFiles(event.dataTransfer.files); });
$("fileInput").addEventListener("change", (event) => uploadFiles(event.target.files));
$("submitClaim").addEventListener("click", submitClaim);
$("newCase").addEventListener("click", () => {
  ["claimId", "policyId", "amount", "description"].forEach((id) => { $(id).value = ""; });
  $("claimStatus").hidden = true;
  state.documents = [];
  renderDocuments();
});
$("chatForm").addEventListener("submit", (event) => { event.preventDefault(); const input = $("question"); const value = input.value.trim(); input.value = ""; ask(value); });
$("clearChat").addEventListener("click", () => { state.history = []; $("chatMessages").innerHTML = '<div class="message assistant">对话已清空。你可以继续询问当前案件或已识别单证。</div>'; });
document.querySelectorAll(".suggestions button").forEach((button) => button.addEventListener("click", () => ask(button.textContent.trim())));

checkHealth();
renderDocuments();
