const messages = document.querySelector("#messages");
const timeline = document.querySelector("#timeline");
const form = document.querySelector("#composer");
const input = document.querySelector("#input");
let cursor = 0;
let relaySessionId = crypto.randomUUID();

function sessionHeaders(extra = {}) {
  return { ...extra, "X-Relay-Session": relaySessionId };
}

function addMessage(text, role, final = false) {
  const node = document.createElement("div");
  node.className = `message ${role}${final ? " final" : ""}`;
  node.textContent = text;
  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
}

function updateSnapshot(snapshot = {}) {
  document.querySelector("#status").textContent = snapshot.status || "idle";
  document.querySelector("#intent").textContent = snapshot.intent || "unknown";
  document.querySelector("#version").textContent = snapshot.version ?? 0;
  document.querySelector("#task").textContent = snapshot.task_id ? snapshot.task_id.slice(0, 8) : "none";
  document.querySelector("#branch").textContent = snapshot.branch_id
    ? `#${snapshot.branch_number} · ${snapshot.branch_id.slice(0, 6)}`
    : "none";
  document.querySelector("#calls").textContent = (snapshot.active_call_ids || []).length;
  const indicator = document.querySelector("#work-indicator");
  const interruptible = ["working", "planning", "executing"].includes(snapshot.status);
  indicator.hidden = !interruptible;
  const slots = document.querySelector("#slots");
  slots.replaceChildren();
  const entries = Object.entries(snapshot.slots || {});
  if (!entries.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No slots yet";
    slots.appendChild(empty);
  }
  for (const [key, value] of entries) {
    const chip = document.createElement("span");
    chip.className = "slot";
    chip.textContent = `${key}: ${value}`;
    slots.appendChild(chip);
  }
  renderContextDiff(snapshot.context_diff || {});
  renderPlanBranches(snapshot.plan_branches || [], snapshot.branch_id);
  const activeBranch = (snapshot.plan_branches || []).find((branch) => branch.branch_id === snapshot.branch_id);
  renderImpact(activeBranch?.impact_decisions || []);
  renderEvidence(snapshot.evidence || [], snapshot.branch_id);
  renderMemory(
    snapshot.conversation_history || [],
    snapshot.memory_turn_count || 0,
    snapshot.memory_turn_limit || 40,
  );
  renderMetrics(snapshot.metrics || {});
  renderTasks(snapshot.tasks || []);
}

function renderMemory(history, count, limit) {
  const root = document.querySelector("#memory-list");
  const badge = document.querySelector("#memory-count");
  root.replaceChildren();
  badge.textContent = `${count} / ${limit} turns`;
  if (!history.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No remembered conversation yet";
    root.appendChild(empty);
    return;
  }
  for (const turn of history.slice(-6).reverse()) {
    const item = document.createElement("div");
    item.className = `memory-item ${turn.role}`;
    const role = document.createElement("strong");
    role.textContent = turn.role;
    const text = document.createElement("span");
    text.textContent = turn.text;
    item.append(role, text);
    root.appendChild(item);
  }
}

function renderCapabilities(capabilities = []) {
  const root = document.querySelector("#capability-list");
  const badge = document.querySelector("#capability-count");
  root.replaceChildren();
  badge.textContent = `${capabilities.length} ${capabilities.length === 1 ? "tool" : "tools"}`;
  if (!capabilities.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No external tools configured";
    root.appendChild(empty);
    return;
  }
  for (const capability of capabilities) {
    const item = document.createElement("div");
    item.className = "capability-item";
    const name = document.createElement("strong");
    name.textContent = capability.name.replaceAll("_", " ");
    const safety = document.createElement("span");
    safety.textContent = capability.state_modifying ? "approval required" : "read only";
    const description = document.createElement("small");
    description.textContent = capability.description;
    item.append(name, safety, description);
    root.appendChild(item);
  }
}

function renderImpact(decisions) {
  const root = document.querySelector("#impact-list");
  const count = document.querySelector("#impact-count");
  root.replaceChildren();
  count.textContent = `${decisions.length} ${decisions.length === 1 ? "decision" : "decisions"}`;
  if (!decisions.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No interruption analysed yet";
    root.appendChild(empty);
    return;
  }
  for (const decision of decisions) {
    const item = document.createElement("div");
    item.className = `impact-item ${decision.action}`;
    const action = document.createElement("strong");
    action.textContent = decision.action;
    const score = document.createElement("span");
    score.textContent = `${Math.round((decision.score || 0) * 100)}% impact`;
    const reason = document.createElement("small");
    reason.textContent = (decision.reasons || []).join("; ");
    item.append(action, score, reason);
    root.appendChild(item);
  }
}

function renderMetrics(metrics) {
  document.querySelector("#metric-ack").textContent = `${metrics.acknowledgement_latency_ms || 0} ms`;
  document.querySelector("#metric-cancel").textContent = `${metrics.last_cancellation_latency_ms || 0} ms`;
  document.querySelector("#metric-interrupts").textContent = metrics.interruptions || 0;
  document.querySelector("#metric-calls").textContent = metrics.cancelled_calls || 0;
  document.querySelector("#metric-stale").textContent = metrics.stale_results_rejected || 0;
  document.querySelector("#metric-preserved").textContent = metrics.evidence_preserved || 0;
  document.querySelector("#metric-switches").textContent = metrics.task_switches || 0;
  document.querySelector("#metric-resumed").textContent = metrics.tasks_resumed || 0;
}

function renderTasks(tasks) {
  const root = document.querySelector("#task-list");
  const count = document.querySelector("#task-count");
  root.replaceChildren();
  count.textContent = `${tasks.length} ${tasks.length === 1 ? "task" : "tasks"}`;
  if (!tasks.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No tasks yet";
    root.appendChild(empty);
    return;
  }
  const resumePrompts = {
    travel_planning: "Continue my trip",
    study_planning: "Continue my study plan",
    research: "Resume my research",
  };
  for (const task of tasks) {
    const item = document.createElement("div");
    item.className = `task-item ${task.status}${task.active ? " active" : ""}`;
    const identity = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = task.intent.replaceAll("_", " ");
    const meta = document.createElement("span");
    meta.textContent = `Branch ${task.branch_number} · ${task.evidence_count} evidence`;
    identity.append(name, meta);
    const state = document.createElement("small");
    state.textContent = task.active ? "active" : task.status;
    item.append(identity, state);
    if (task.status === "paused" && resumePrompts[task.intent]) {
      const resume = document.createElement("button");
      resume.type = "button";
      resume.className = "task-resume";
      resume.textContent = "Resume";
      resume.addEventListener("click", () => send(resumePrompts[task.intent]));
      item.appendChild(resume);
    }
    root.appendChild(item);
  }
}

function renderEvidence(evidence, activeBranchId) {
  const root = document.querySelector("#evidence-list");
  const count = document.querySelector("#evidence-count");
  root.replaceChildren();
  count.textContent = `${evidence.length} ${evidence.length === 1 ? "item" : "items"}`;
  if (!evidence.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No grounded evidence yet";
    root.appendChild(empty);
    return;
  }
  for (const record of [...evidence].reverse()) {
    const validHere = (record.valid_branch_ids || []).includes(activeBranchId)
      && record.status !== "invalidated";
    const item = document.createElement("div");
    item.className = `evidence-item ${record.status}${validHere ? " active" : ""}`;
    const source = document.createElement("strong");
    source.textContent = record.source.replaceAll("_", " ");
    const status = document.createElement("span");
    status.textContent = validHere ? record.status : "excluded";
    const dependencies = document.createElement("small");
    dependencies.textContent = `depends on: ${(record.depends_on || []).join(", ") || "none"}`;
    item.append(source, status, dependencies);
    root.appendChild(item);
  }
}

function renderContextDiff(diff) {
  const root = document.querySelector("#context-diff");
  root.replaceChildren();
  const groups = [
    ["changed", "Changed"],
    ["added", "Added"],
    ["preserved", "Preserved"],
    ["removed", "Removed"],
  ];
  let count = 0;
  for (const [key, label] of groups) {
    for (const [name, value] of Object.entries(diff[key] || {})) {
      const item = document.createElement("div");
      item.className = `diff-item ${key}`;
      const title = document.createElement("span");
      title.textContent = `${label} · ${name}`;
      const detail = document.createElement("strong");
      detail.textContent = key === "changed" ? `${value.old} → ${value.new}` : String(value);
      item.append(title, detail);
      root.appendChild(item);
      count += 1;
    }
  }
  if (!count) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No correction yet";
    root.appendChild(empty);
  }
}

function renderPlanBranches(branches, activeBranchId) {
  const root = document.querySelector("#plan-branches");
  const badge = document.querySelector("#branch-badge");
  root.replaceChildren();
  const active = branches.find((branch) => branch.branch_id === activeBranchId);
  badge.textContent = active ? `Branch ${active.number}` : "No branch";
  if (!branches.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Start a task to see its execution plan.";
    root.appendChild(empty);
    return;
  }
  for (const branch of [...branches].reverse()) {
    const card = document.createElement("article");
    card.className = `branch-card ${branch.status}${branch.branch_id === activeBranchId ? " active" : ""}`;
    const header = document.createElement("div");
    header.className = "branch-header";
    const name = document.createElement("strong");
    name.textContent = `Branch ${branch.number}`;
    const status = document.createElement("span");
    status.textContent = branch.status;
    header.append(name, status);
    const request = document.createElement("p");
    request.className = "branch-request";
    request.textContent = branch.request_text || "Initial request";
    card.append(header, request);
    const steps = document.createElement("div");
    steps.className = "plan-steps";
    if (!(branch.steps || []).length) {
      const waiting = document.createElement("div");
      waiting.className = "plan-step queued";
      waiting.textContent = "Reasoning and plan selection";
      steps.appendChild(waiting);
    }
    for (const step of branch.steps || []) {
      const row = document.createElement("div");
      row.className = `plan-step ${step.status}`;
      const marker = document.createElement("i");
      marker.className = `dot ${step.status}`;
      const text = document.createElement("span");
      text.textContent = step.name;
      const state = document.createElement("small");
      state.textContent = step.status;
      row.append(marker, text, state);
      steps.appendChild(row);
    }
    card.appendChild(steps);
    root.appendChild(card);
  }
}

function describe(action) {
  const p = action.payload || {};
  if (action.type === "tool_call") return `${p.tool_name} · attempt ${p.attempt}`;
  if (action.type === "cancel_call") return `${p.tool_name} · ${p.reason}`;
  if (action.type === "trace") return p.name || "trace";
  return p.text || action.type;
}

function renderAction(action) {
  const p = action.payload || {};
  if (["spoken", "clarification", "final"].includes(action.type)) {
    const role = p.acknowledgement ? "assistant acknowledgement" : "assistant";
    addMessage(p.text || action.type, role, action.type === "final");
  }
  if (action.type === "final" && p.provider_fallback) {
    addMessage(
      "Provider synthesis was unavailable, so Relay returned the accepted grounded evidence directly.",
      "system",
    );
  }
  if (action.type === "tool_call") {
    addMessage(`Working: ${p.tool_name.replaceAll("_", " ")} (attempt ${p.attempt})`, "system");
  }
  if (action.type === "cancel_call") {
    addMessage(`Cancelled outdated work: ${p.tool_name.replaceAll("_", " ")}`, "system");
  }
  if (action.type === "trace" && p.name === "stale_tool_result_dropped") {
    addMessage("Ignored a late result from the cancelled task.", "system");
  }
  if (action.type === "trace" && p.name === "reasoning_cancelled") {
    addMessage("Cancelled outdated reasoning; applying your newest instruction.", "system");
  }
  if (action.type === "trace" && p.name === "grounded_results_invalidated") {
    addMessage("Discarded cached evidence that conflicts with your correction.", "system");
  }
  if (action.type === "trace" && p.name === "parallel_evidence_buffered") {
    addMessage(`Research source completed; ${p.remaining_calls} parallel searches still running.`, "system");
  }
  if (p.state_snapshot) updateSnapshot(p.state_snapshot);
  const event = document.createElement("div");
  event.className = `event ${action.type}`;
  const name = document.createElement("div");
  name.className = "event-name";
  name.textContent = action.type.replaceAll("_", " ");
  const detail = document.createElement("div");
  detail.className = "event-detail";
  detail.textContent = describe(action);
  event.append(name, detail);
  timeline.prepend(event);
}

async function send(text) {
  const value = text.trim();
  if (!value) return;
  addMessage(value, "user");
  input.value = "";
  await fetch("/api/messages", {
    method: "POST",
    headers: sessionHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text: value }),
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  send(input.value);
});
document.querySelectorAll("[data-message]").forEach((button) => {
  button.addEventListener("click", () => send(button.dataset.message));
});
document.querySelector("#clear").addEventListener("click", () => {
  relaySessionId = crypto.randomUUID();
  cursor = 0;
  messages.replaceChildren();
  timeline.replaceChildren();
  document.querySelector("#event-count").textContent = "0 events";
  loadStatus();
});
document.querySelector("#judge-demo").addEventListener("click", async () => {
  await send("Plan a 3-day trip to Delhi under ₹30,000");
  window.setTimeout(
    () => send("Actually change it to Jaipur under ₹20,000"),
    1200,
  );
});

async function poll() {
  const requestedSession = relaySessionId;
  try {
    const response = await fetch(`/api/actions?after=${cursor}`, {
      headers: sessionHeaders(),
    });
    const data = await response.json();
    if (requestedSession !== relaySessionId) return;
    data.actions.forEach(renderAction);
    cursor = data.cursor;
    document.querySelector("#event-count").textContent = `${cursor} events`;
  } finally {
    setTimeout(poll, 250);
  }
}

function loadStatus() {
  const requestedSession = relaySessionId;
  fetch("/api/status", { headers: sessionHeaders() })
    .then((response) => response.json())
    .then((data) => {
      if (requestedSession !== relaySessionId) return;
    document.querySelector("#provider").textContent = `${data.provider} · ${data.build_version}`;
    updateSnapshot(data.snapshot);
    renderCapabilities(data.capabilities || []);
    });
}

loadStatus();
poll();
