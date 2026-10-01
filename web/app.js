const messages = document.querySelector("#messages");
const timeline = document.querySelector("#timeline");
const form = document.querySelector("#composer");
const input = document.querySelector("#input");
const voiceButton = document.querySelector("#voice");
const voiceStatus = document.querySelector("#voice-status");
const voiceLabel = document.querySelector("#voice-label");
const voicePreview = document.querySelector("#voice-preview");
let cursor = 0;
let relaySessionId = crypto.randomUUID();
let lastTimelineSignature = "";
let lastTimelineCount = 0;
let liveFeedEvents = [];
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let voiceRequested = false;
let lastPartial = "";
let lastPartialSentAt = 0;

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

function humanize(value = "") {
  return String(value).replaceAll("_", " ");
}

function setBackendActivity(text) {
  document.querySelector("#current-action").textContent = text;
}

function setVoiceState(active, label = "Listening continuously", preview = "Speak naturally. Relay will keep listening while it works.") {
  voiceButton.classList.toggle("active", active);
  voiceButton.setAttribute("aria-pressed", String(active));
  voiceButton.setAttribute("aria-label", active ? "Stop voice input" : "Start voice input");
  voiceButton.title = active ? "Stop voice input" : "Start voice input";
  voiceButton.textContent = active ? "Stop" : "Mic";
  voiceStatus.hidden = !active && !preview;
  voiceLabel.textContent = label;
  voicePreview.textContent = preview;
}

function updatePipeline(status = "idle") {
  const phases = ["listen", "understand", "execute", "answer"];
  const activeIndex = {
    idle: 0,
    awaiting_clarification: 1,
    planning: 1,
    working: 2,
    executing: 2,
    complete: 3,
    cancelled: 3,
    error: 3,
  }[status] ?? 1;
  phases.forEach((phase, index) => {
    const node = document.querySelector(`#phase-${phase}`);
    node.classList.toggle("done", index < activeIndex);
    node.classList.toggle("active", index === activeIndex);
  });
}

function updateSnapshot(snapshot = {}) {
  const status = snapshot.status || "idle";
  document.querySelector("#status").textContent = status;
  document.querySelector("#intent").textContent = snapshot.intent || "unknown";
  document.querySelector("#version").textContent = snapshot.version ?? 0;
  document.querySelector("#task").textContent = snapshot.task_id ? snapshot.task_id.slice(0, 8) : "none";
  document.querySelector("#branch").textContent = snapshot.branch_id
    ? `#${snapshot.branch_number} · ${snapshot.branch_id.slice(0, 6)}`
    : "none";
  const activeCalls = (snapshot.active_call_ids || []).length;
  document.querySelector("#calls").textContent = activeCalls;
  document.querySelector("#active-calls-badge").textContent = `${activeCalls} ${activeCalls === 1 ? "call" : "calls"}`;
  const pill = document.querySelector("#status-pill");
  pill.textContent = humanize(status);
  pill.className = `status-pill ${status}`;
  document.querySelector("#backend-title").textContent = {
    idle: "Ready for a task",
    awaiting_clarification: "Waiting for clarification",
    planning: "Understanding your request",
    working: "Executing the active plan",
    executing: "Executing the active plan",
    complete: "Latest task completed",
    cancelled: "Active work stopped",
    error: "Backend needs attention",
  }[status] || "Processing your request";
  updatePipeline(status);
  if (status === "idle") setBackendActivity("Waiting for your message");
  if (status === "complete") setBackendActivity("Response delivered from the active branch");
  if (status === "awaiting_clarification") setBackendActivity("Waiting for missing information");
  if (status === "error") setBackendActivity("A backend operation failed safely");
  renderActiveTask(snapshot.tasks || [], status);
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

function renderActiveTask(tasks, status) {
  const active = tasks.find((task) => task.current) || tasks.find((task) => task.active) || tasks[0];
  const title = document.querySelector("#active-task-title");
  const request = document.querySelector("#active-task-request");
  const step = document.querySelector("#active-task-step");
  const state = document.querySelector("#active-task-status");
  const headerRequest = document.querySelector("#current-request");
  if (!active) {
    title.textContent = "Waiting for a request";
    request.textContent = "Send a message to create the first execution branch.";
    step.textContent = "No tool or reasoning step is running.";
    state.textContent = status;
    headerRequest.textContent = "No active request";
    return;
  }
  title.textContent = humanize(active.intent || "current task");
  request.textContent = active.request_text || "Current request is being prepared.";
  step.textContent = active.active_step
    ? `Running now: ${active.active_step}`
    : active.status === "complete"
      ? "Completed. This is the latest authoritative result."
      : active.status === "cancelled"
        ? "Cancelled. A newer instruction can replace it."
        : "Reasoning and tool selection are in progress.";
  state.textContent = active.status || status;
  headerRequest.textContent = active.request_text || "Current request is being prepared.";
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
    item.className = `task-item ${task.status}${task.current ? " current" : ""}${task.active ? " active" : ""}`;
    const identity = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = task.intent.replaceAll("_", " ");
    const meta = document.createElement("span");
    meta.textContent = `Branch ${task.branch_number} · ${task.evidence_count} evidence`;
    identity.append(name, meta);
    const state = document.createElement("small");
    state.textContent = task.status;
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
    empty.textContent = "Send any task to see the active execution branch.";
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
  if (action.type === "tool_call") {
    const inputs = Object.entries(p.arguments || {}).map(([key, value]) => `${humanize(key)}: ${value}`).join(" · ");
    return `${humanize(p.tool_name)}${inputs ? ` — ${inputs}` : ""} · attempt ${p.attempt}`;
  }
  if (action.type === "cancel_call") return `${humanize(p.tool_name)} · ${humanize(p.reason)}`;
  if (action.type === "trace") return humanize(p.name || "trace");
  return p.text || action.type;
}

function renderLiveFeed(action) {
  const root = document.querySelector("#live-feed");
  const count = document.querySelector("#live-feed-count");
  const detail = describe(action);
  const label = action.type === "trace" ? "system" : humanize(action.type);
  const event = { label, detail, type: action.type };
  const previous = liveFeedEvents[0];
  if (previous && previous.label === event.label && previous.detail === event.detail) return;
  liveFeedEvents = [event, ...liveFeedEvents].slice(0, 5);
  root.replaceChildren();
  count.textContent = `${liveFeedEvents.length} ${liveFeedEvents.length === 1 ? "event" : "events"}`;
  for (const item of liveFeedEvents) {
    const row = document.createElement("div");
    row.className = `live-feed-item ${item.type}`;
    const name = document.createElement("strong");
    name.textContent = item.label;
    const text = document.createElement("span");
    text.textContent = item.detail;
    row.append(name, text);
    root.appendChild(row);
  }
}

function showInterruption(text) {
  document.querySelector("#interrupt-banner").hidden = false;
  document.querySelector("#interrupt-summary").textContent = text;
}

function renderTimelineEvent(action) {
  const detailText = describe(action);
  const signature = `${action.type}:${detailText}`;
  if (signature === lastTimelineSignature && timeline.firstElementChild) {
    lastTimelineCount += 1;
    let repeat = timeline.firstElementChild.querySelector(".event-repeat");
    if (!repeat) {
      repeat = document.createElement("span");
      repeat.className = "event-repeat";
      timeline.firstElementChild.querySelector(".event-name").appendChild(repeat);
    }
    repeat.textContent = `×${lastTimelineCount}`;
    return;
  }
  if (timeline.querySelector(".empty")) timeline.replaceChildren();
  lastTimelineSignature = signature;
  lastTimelineCount = 1;
  const event = document.createElement("div");
  event.className = `event ${action.type}`;
  const name = document.createElement("div");
  name.className = "event-name";
  name.textContent = humanize(action.type);
  const detail = document.createElement("div");
  detail.className = "event-detail";
  detail.textContent = detailText;
  event.append(name, detail);
  timeline.prepend(event);
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
  if (action.type === "spoken" && p.acknowledgement) setBackendActivity("Understanding the newest instruction");
  if (action.type === "tool_call") setBackendActivity(`Running ${humanize(p.tool_name)} with the latest context`);
  if (action.type === "cancel_call") {
    setBackendActivity(`Stopped outdated ${humanize(p.tool_name)} work`);
    showInterruption(`Cancelled ${humanize(p.tool_name)} because a newer instruction arrived`);
  }
  if (action.type === "trace" && p.name === "stale_tool_result_dropped") setBackendActivity("Ignored a late result; replacement work continues");
  if (action.type === "trace" && p.name === "reasoning_cancelled") {
    setBackendActivity("Cancelled outdated reasoning; applying the newest instruction");
    showInterruption("Old reasoning stopped; newest message is now authoritative");
  }
  if (action.type === "trace" && p.name === "grounded_results_invalidated") {
    setBackendActivity("Removed evidence that conflicts with the correction");
    showInterruption(`${p.count || "Conflicting"} evidence item(s) invalidated`);
  }
  if (action.type === "trace" && p.name === "parallel_evidence_buffered") {
    setBackendActivity(`Research evidence accepted; ${p.remaining_calls} parallel searches remain`);
  }
  if (action.type === "trace" && p.name === "speculative_intent_started") {
    setBackendActivity(`Listening to partial speech: “${p.partial_text || "…"}”`);
  }
  if (action.type === "trace" && p.name === "interruption_detected") showInterruption("New message detected while work was active");
  if (action.type === "final") setBackendActivity(p.local_fast_path ? "Answered through the local fast path" : "Final answer delivered from the active branch");
  if (p.state_snapshot) updateSnapshot(p.state_snapshot);
  renderLiveFeed(action);
  renderTimelineEvent(action);
}

async function send(text) {
  const value = text.trim();
  if (!value) return;
  addMessage(value, "user");
  input.value = "";
  setBackendActivity("Sending the newest instruction to Relay");
  try {
    const response = await fetch("/api/messages", {
      method: "POST",
      headers: sessionHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text: value }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    addMessage("Relay could not reach the backend. Please retry in a moment.", "assistant");
    setBackendActivity("Backend connection failed; request was not accepted");
  }
}

async function sendTranscript(text, endOfTurn) {
  const value = text.trim();
  if (!value) return;
  if (endOfTurn) {
    addMessage(value, "user");
    input.value = "";
    setBackendActivity("Final speech received; applying it to the active plan");
  }
  const response = await fetch("/api/transcripts", {
    method: "POST",
    headers: sessionHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text: value, end_of_turn: endOfTurn }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

function configureVoice() {
  if (!SpeechRecognition) {
    voiceButton.disabled = true;
    voiceButton.title = "Voice recognition is not supported in this browser";
    return;
  }
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = navigator.language || "en-IN";

  recognition.onstart = () => {
    setVoiceState(true);
  };
  recognition.onresult = (event) => {
    let interim = "";
    const finalParts = [];
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const phrase = event.results[index][0]?.transcript?.trim();
      if (!phrase) continue;
      if (event.results[index].isFinal) finalParts.push(phrase);
      else interim += `${phrase} `;
    }
    const partial = interim.trim();
    if (partial) {
      voicePreview.textContent = partial;
      const now = Date.now();
      if (partial !== lastPartial && now - lastPartialSentAt >= 180) {
        lastPartial = partial;
        lastPartialSentAt = now;
        sendTranscript(partial, false).catch(() => {
          setVoiceState(true, "Voice connection interrupted", "The partial transcript could not reach Relay.");
        });
      }
    }
    if (finalParts.length) {
      const finalText = finalParts.join(" ");
      lastPartial = "";
      voicePreview.textContent = "Final speech sent. Keep speaking to interrupt again.";
      sendTranscript(finalText, true).catch(() => {
        addMessage("Relay could not accept the voice transcript. Please retry or type the message.", "system");
      });
    }
  };
  recognition.onerror = (event) => {
    const denied = ["not-allowed", "service-not-allowed"].includes(event.error);
    if (denied) voiceRequested = false;
    const message = denied
      ? "Microphone permission was not granted. You can continue typing."
      : `Voice recognition paused (${humanize(event.error)}).`;
    setVoiceState(false, "Voice input unavailable", message);
  };
  recognition.onend = () => {
    if (voiceRequested) {
      try {
        recognition.start();
      } catch (error) {
        setTimeout(() => voiceRequested && recognition.start(), 300);
      }
      return;
    }
    setVoiceState(false, "Voice input stopped", "Press Mic whenever you want Relay to listen continuously.");
  };
}

function stopVoice() {
  voiceRequested = false;
  if (recognition) recognition.stop();
}

voiceButton.addEventListener("click", () => {
  if (!recognition) return;
  if (voiceRequested) {
    stopVoice();
    return;
  }
  voiceRequested = true;
  setVoiceState(true, "Starting microphone", "Your browser may ask for microphone permission.");
  try {
    recognition.start();
  } catch (error) {
    voiceRequested = false;
    setVoiceState(false, "Voice input unavailable", "The microphone could not be started. You can continue typing.");
  }
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  send(input.value);
});
document.querySelector("#clear").addEventListener("click", () => {
  stopVoice();
  relaySessionId = crypto.randomUUID();
  cursor = 0;
  messages.replaceChildren();
  const intro = document.createElement("div");
  intro.className = "message assistant intro-message";
  intro.innerHTML = "<strong>What would you like to accomplish?</strong><span>I’ll keep listening while I reason and use tools. Send a new message while I work to redirect me.</span>";
  messages.appendChild(intro);
  timeline.replaceChildren();
  const timelineEmpty = document.createElement("span");
  timelineEmpty.className = "empty";
  timelineEmpty.textContent = "No events yet";
  timeline.appendChild(timelineEmpty);
  lastTimelineSignature = "";
  lastTimelineCount = 0;
  liveFeedEvents = [];
  document.querySelector("#live-feed").innerHTML = '<span class="empty">The next request will stream its backend steps here.</span>';
  document.querySelector("#live-feed-count").textContent = "0 events";
  document.querySelector("#interrupt-banner").hidden = true;
  document.querySelector("#event-count").textContent = "0 events";
  loadStatus();
});
document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
    document.querySelectorAll(".tab-page").forEach((page) => page.classList.toggle("active", page.id === `tab-${button.dataset.tab}`));
  });
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
configureVoice();
poll();
