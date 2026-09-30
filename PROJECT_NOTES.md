# Relay Project Notebook

This is the living teammate handoff for the Samsung Theme 05 project. Update it
after every meaningful code, architecture, test, scope, or integration change.

Last updated: September 30, 2026

## 1. Project in one sentence

Relay is a session-scoped runtime that lets an AI agent be interrupted, corrected,
cancelled, paused, and resumed while reasoning and tools are running, without
mixing stale work into the current answer.

## 2. The problem

Conventional assistants commonly behave as a half-duplex sequence: listen, think,
then speak. A real user may change a destination, add a constraint, cancel an
operation, or switch tasks before the assistant finishes. This creates concurrency
and state-consistency problems:

- The assistant may finish an obsolete request.
- Results from cancelled calls may arrive late and pollute the new answer.
- A local correction may unnecessarily erase all useful work.
- A paused task may lose its state.
- A state-changing action may run twice after a retry.
- The assistant may stay silent during slow reasoning or claim completion too early.

## 3. What Relay is and is not

Relay is the control layer around an existing language model. ChatGPT, Claude,
Gemini, or a local model can be connected behind one model-adapter interface.

Relay owns:

- Streaming events and structured actions.
- Fast acknowledgement and slow asynchronous execution.
- Intent, slots, session tasks, and state snapshots.
- Tool selection validation, cancellation, timeouts, and retry policy.
- Stale-result rejection and exactly-once side-effect protection.
- Trace logging and evaluation behavior.

The external model owns language understanding, reasoning, and natural response
generation. We are not training a new foundation model.

## 4. Official constraints we are following

- Python 3.10-3.12 runtime.
- Two asynchronous queues: timestamped events in, actions out.
- Inputs may include text chunks, end-of-turn markers, interruption signals, WAV,
  PNG frames, tool results, and dynamic tool manifests.
- Outputs include spoken fillers, tool calls with `call_id`, cancellations,
  clarifications, final responses, and structured state snapshots.
- Session memory only; no cross-session profile.
- Wake-word detection, speech-synthesis quality, and UI polish are out of scope.
- Scenario limit: 120 seconds; setup/warm-up limit: 300 seconds.

Scoring priorities:

| Category | Weight | Relay evidence |
|---|---:|---|
| Task completion | 40% | Valid arguments, grounded results, snapshots |
| Interruption recovery | 35% | Cancellation and stale-result suppression |
| Response latency | 15% | Fast path before slow work |
| Safety and protocol | 10% | JSON contract and side-effect idempotency |

## 5. Architecture

```text
Text / WAV / PNG / tool result
              |
              v
      Timestamped input queue
              |
      +-------+--------+
      |                |
      v                v
 Fast path       Slow path / model
 acknowledgement     reasoning
      |                |
      +-------+--------+
              |
     Interruption coordinator
              |
     Task + state + tool manager
              |
       Structured output queue
```

The visual UI will consume exactly the same action stream as the CLI and evaluation
harness. UI work will not be allowed to change core orchestration behavior.

## 6. Completed work

### Requirements and planning

- Read and visually verified the complete three-page Theme 5 guide.
- Converted guide requirements into a scoring-first execution plan.
- Selected a provider-independent architecture rather than training a model.
- Defined the main Delhi-to-Jaipur interruption demonstration.

### Protocol

- Created `InputEvent` with event ID, event type, timestamp, and payload.
- Created `Action` with action ID, action type, timestamp, and payload.
- Created versioned `StateSnapshot` containing intent, slots, call IDs, status,
  current task ID, and paused task IDs.
- Added event types for transcript chunks, explicit interruptions, tool results,
  WAV/audio, PNG/video frames, and shutdown.
- Added output actions for spoken messages, tool calls, cancellations,
  clarifications, final responses, and traces.

### Fast and slow paths

- Implemented a fast acknowledgement before slow tool work begins.
- Implemented a separately cancellable slow-path coroutine.
- Added partial-transcript detection and a speculative-intent trace.
- Added truthful clarification when a required slot is missing.

### Intent and session state

- Added deterministic baseline detection for travel, study, pause, and cancel.
- Added destination, budget, trip-duration, and study-subject extraction.
- Added localized corrections: changed slots are replaced and unchanged slots remain.
- Kept all state inside the current RelayAgent session.

### Task checkpoints

- Added unique task IDs and task statuses.
- Added session task registry.
- Added pause, switch, cancel, complete, and resume behavior.
- Preserved a paused travel task while a study task becomes active.
- Restored the travel task and its slots when resumed.

### Interruption safety

- Added unique `call_id` values for every tool invocation.
- Emit explicit cancellation actions for superseded calls.
- Remove invalid call IDs from the active snapshot.
- Drop late results when their call ID is no longer active.
- Fixed a discovered race where an emitted tool call outlived its planning coroutine.

### Tool lifecycle

- Parse dynamic tool manifests.
- Distinguish read-only and state-modifying tools.
- Validate required arguments and primitive JSON-schema types.
- Correlate asynchronous results with active calls.
- Apply configurable tool timeouts.
- Retry read-only calls only within their configured retry limit.
- Never automatically retry state-changing calls with an uncertain outcome.
- Assign idempotency keys and block duplicate state-changing calls.
- Ground final actions in the accepted tool result.

### Model integration foundation

- Added a provider-independent `ModelAdapter` protocol.
- Added strict structured decisions: `tool_call`, `clarification`, or `final`.
- Added a `ModelContext` containing task, slots, tools, and grounded results.
- Added an offline deterministic adapter for development without API cost.
- Wired model decisions into the slow path while keeping the old deterministic
  fallback available.
- Added an OpenAI Responses API adapter using `OPENAI_API_KEY` and `OPENAI_MODEL`.
- Added strict JSON-schema output requests and defensive response parsing.
- Added provider-error handling that returns a truthful clarification instead of
  crashing or claiming completion.
- The live provider path is implemented and mock-tested; it has not been called
  against a real account because no user API key is configured in this workspace.

### Visual dashboard

- Added a dependency-free local HTTP dashboard at `http://127.0.0.1:8000`.
- Added a chat panel with interruption scenario shortcuts.
- Added a live inspector for status, intent, version, task ID, active calls, and slots.
- Added a timeline for spoken actions, tool calls, cancellations, traces, and finals.
- Added a thread-safe bridge between HTTP requests and Relay's async runtime.
- Added deterministic demo-tool completion so the full flow is visible without
  external travel or study services.
- The dashboard uses Gemini when `GEMINI_API_KEY` is present, OpenAI when only
  `OPENAI_API_KEY` is present, and otherwise starts in offline-demo mode.
- Smoke-tested page serving, stylesheet serving, message acceptance, and the
  `spoken -> tool_call -> final` action flow.

### Development and verification

- Added a CLI that prints the same JSON actions used by the evaluation harness.
- Added a deterministic virtual-clock harness skeleton.
- Added unit, async behavior, security, HTTP-boundary, and browser smoke tests.
- All 83 automated tests are passing in the current deployment-ready build.

## 7. Important defects found and fixed

1. An outstanding tool call was initially not considered active after its planning
   coroutine finished. Corrections therefore could miss cancellation. Active work
   now includes both running coroutines and outstanding tool calls.
2. Late results could have been mistaken for current work without call correlation.
   Results are now accepted only for active `call_id` values.
3. Blind retry could duplicate a booking or other side effect. Automatic retry is
   now limited to read-only tools; mutations use idempotency protection.
4. A provider timeout during final synthesis previously hid a successful weather or
   research result. Relay now completes from accepted grounded evidence and labels
   the response as a provider fallback.
5. `Cancel cars. Compare scooters instead` previously matched the word `cancel` and
   stopped the whole task. Relay now distinguishes cancellation-only commands from
   replacement instructions, forks the corrected branch, and updates the topic.

## 8. Current limitations

- Intent and slot parsing are deterministic baselines, not model-powered yet.
- General chat is provider-powered and history-aware, but truly live information or
  real-world actions still require an appropriate external tool or integration.
- Live weather currently depends on Open-Meteo availability and network access.
- OpenAI and Gemini adapters are implemented; provider calls still require the
  user's private key and quota. Claude has not been implemented.
- Domain tools currently use manifests and injected results; there is no live travel
  or study data service.
- State-changing tools still need a full propose/commit/reconcile lifecycle.
- Read-only evidence is selectively preserved by the semantic impact engine; a full
  graph scheduler that skips already-completed tool steps is still future work.
- Audio and image events are acknowledged/buffered but not decoded or grounded.
- The virtual-clock harness needs complete scheduling, fault injection, and scoring.
- The local dashboard is an MVP, not production UI; it uses polling and has no authentication.
- Cancelling a Relay model task suppresses its result immediately, but the standard-library
  HTTP worker may remain alive until the provider request returns or reaches its timeout.
- Evaluation-kit schemas must be reconciled when the official kit is released.

## 9. Current test coverage

Tests cover:

- Travel slot extraction.
- Localized corrections.
- Explicit cancellation.
- Fast acknowledgement before tool call.
- Cancellation and corrected replanning.
- Stale-result rejection.
- Partial-transcript speculation trace.
- Pause, task switch, and checkpoint resume.
- Tool-schema argument validation.
- Read-only retry after a reported failure.
- Read-only retry after timeout.
- No automatic retry for state-changing tools.
- Idempotency blocking for duplicate mutations.
- Model-decision validation and deterministic adapter selection.
- OpenAI request construction, structured response parsing, and malformed-output rejection.
- Model synthesis after a grounded tool result.
- Virtual-clock trace serialization.
- Three-call parallel cancellation and exactly-once cancellation signals.
- Reverse-order, duplicate, unknown, and obsolete tool-result rejection.
- Rapid three-branch corrections with only the newest branch active.
- Cancellation of in-flight model reasoning.
- Semantic interruption-impact decisions and explanations.
- Secret redaction and bounded external error text.
- Empty and oversized HTTP requests, path traversal, and static delivery.
- Bounded long-session action retention and cursor continuity.
- Current-build desktop and 390 px responsive browser behavior.
- Bounded session conversation memory across arbitrary general follow-ups.
- Provider payload propagation for conversation history.
- Visible cancellation of superseded ordinary model reasoning.
- Generic goal changes recorded in branch context diffs.
- Cancellation-only versus cancel-and-replace language.
- Weather and calculation intent/argument extraction.
- Exact research replacement from cars to scooters while work is active.
- Grounded final delivery when provider synthesis times out after tool completion.

Run the exact test count before relying on any number written in this document.

## 10. How to run it now

```powershell
cd "C:\Users\rajee\OneDrive\Documents\ChatGPT\projectsamsung"
$python = "C:\Users\rajee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python -m unittest discover -s tests -v
& $python -m relay.demo
& $python -m relay.web
```

Then open `http://127.0.0.1:8000`. For live OpenAI reasoning, set
`OPENAI_API_KEY` and optionally `OPENAI_MODEL` in the current PowerShell session.

Suggested CLI inputs:

```text
Plan a 3-day trip to Delhi under ₹30,000
Actually change it to Jaipur under ₹20,000
Pause this
Make a study plan for mathematics exam
Continue my trip
```

## 11. Work remaining

### Next: finish task and tool correctness

- Add state-changing propose, commit, and reconciliation states.
- Convert semantic dependencies into an executable graph scheduler.
- Cancel only affected work while unrelated parallel calls continue.
- Reuse preserved read-only results to skip completed graph nodes.
- Add seeded randomized concurrency/fault testing beyond the deterministic race suite.

### Next: live-verify the real model

- Configure an OpenAI project key locally through an environment variable.
- Never commit or paste API keys into source files or this notebook.
- Run the live adapter against the configured account and chosen model.
- Verify structured tool selection, grounded synthesis, errors, and rate limits.
- Replace the standard-library request worker with cancelable async HTTP if needed.
- Expand grounded fallback formatting for additional future integration schemas.

### Then: multimodal grounding

- Add transcription adapter for WAV inputs.
- Add vision adapter for PNG frames.
- Process both behind immediate conversational acknowledgement.
- Clarify ambiguous perception instead of guessing.

### Then: evaluation and UI

- Complete deterministic scheduling and mock tool fault injection.
- Implement nine public-style scenarios and adversarial timing tests.
- Emit JSONL traces and calculate latency/safety metrics.
- Refine the existing UI only where it improves demonstration clarity.

### Finalization

- Test on supported Python versions.
- Run clean-environment installation and smoke tests.
- Record the interruption and multimodal demonstrations.
- Finish architecture, reproducibility, limitations, and pitch material.
- Package and submit before September 25.

## 12. Progress snapshot

- Core interruption architecture: approximately 85% complete.
- Submission-ready backend: approximately 75% complete after semantic impact,
  evidence isolation, provider-resilient grounding, security hardening, and validation;
  extended live provider verification,
  graph execution, and multimodal grounding are still pending.
- Completed major milestones: requirements, architecture, Python foundation,
  protocol, fast/slow paths, state tracking, interruption safety.
- In progress: executable dependency graph and live-provider verification.
- Automated evaluation is active; multimodal processing and final packaging remain.

## 13. Change log

### September 17, 2026 - initial foundation

- Replaced the early Node prototype with the required Python runtime.
- Added protocol, orchestrator, intent parsing, tool registry, harness, CLI, and tests.
- Added interruption cancellation and stale-result suppression.

### September 17, 2026 - task checkpoints

- Added session task registry and task IDs.
- Added pause, switch, resume, completion, and cancellation state.
- Added automated checkpoint-resume coverage.

### September 17, 2026 - safe tool lifecycle

- Added manifest validation, result correlation, timeouts, read-only retry policy,
  mutation idempotency, and associated tests.

### September 17, 2026 - model-adapter foundation

- Added provider-neutral model context and decision contract.
- Added strict decision validation and offline deterministic adapter.
- Wired the adapter into the slow execution path.

### September 17, 2026 - OpenAI adapter and visual dashboard

- Implemented an OpenAI Responses API adapter with structured JSON decisions.
- Added grounded second-pass synthesis after tool results.
- Added environment-only API-key configuration and `.env.example`.
- Added a local web dashboard with chat, state, slots, and event timeline.
- Added mock provider tests and an offline end-to-end dashboard smoke test.
- Increased the automated suite from 18 to 22 passing tests.

### September 18, 2026 - dashboard intent-routing correction

- Reproduced a dashboard report where `hii` established `general_assistance`, then
  `Actually change it to Jaipur under ₹20,000` incorrectly inherited that intent.
- Changed routing so destination, budget, or duration slots can establish travel intent
  even when the correction does not repeat the words trip or travel.
- Standardized the demo tool manifests as JSON Schema objects.
- Added unit and end-to-end regression coverage for the exact reported sequence.
- Renamed `Clear view` to `Clear display` because it clears visible elements, not session state.
- Re-ran the dashboard flow and verified `general_assistance -> travel_planning ->
  search_travel -> grounded Jaipur final` on the corrected build.
- Replaced the confusing offline general-purpose placeholder with a message that
  explains which demo tasks are currently configured.

### September 18, 2026 - cached-result invalidation and visible progress

- Reproduced a post-completion correction where slots changed to Jaipur but the
  deterministic model reused a cached Delhi result and repeated the Delhi final.
- Added result-to-slot conflict checking and invalidation before replanning.
- Added regression coverage proving a completed Delhi result cannot satisfy a Jaipur request.
- Expanded offline travel and study outputs into useful multi-line plans.
- Increased the web demo tool delay to four seconds to create a clear interruption window.
- Added visible chat status for tool execution, cancellation, stale-result rejection,
  and cached-evidence invalidation.
- Smoke-tested a completed Delhi plan followed by a Jaipur correction and verified
  separate Delhi and Jaipur tool calls plus the correct three-day, INR 20,000 Jaipur final.

### September 18, 2026 - stale server diagnosis

- Inspected the live service on port 8000 after the corrected output did not appear.
- Confirmed that its in-memory Python backend was an older build even though it served
  the latest frontend files from disk.
- Added a visible dashboard build identifier (`2026.09.18.2`).
- Added `Cache-Control: no-store` to API and static responses so browser caching cannot
  hide frontend changes during development.
- Found two separate old Python processes listening on port 8000, which caused requests
  to reach inconsistent in-memory builds.
- Stopped both stale listeners and started one corrected server.
- Verified build `2026.09.18.2`, action count 0, and exactly one port-8000 listener.

### Technology-stack decision

- Keep the evaluated orchestration runtime in Python 3.10-3.12 because this is an
  explicit Theme 5 execution constraint, not an arbitrary framework preference.
- Use browser-native HTML, CSS, and JavaScript for the current lightweight dashboard.
- Node.js/React remains an optional presentation-layer upgrade only if the core scoring
  work is complete; the agent protocol stays Python to remain evaluation-compatible.

### September 18, 2026 - secure OpenAI launcher

- Diagnosed another failed provider switch and found two simultaneous port-8000
  listeners, both started without `OPENAI_API_KEY` and therefore in offline mode.
- Added `scripts/start_openai.ps1` to prompt securely, set the key and model in the
  same process environment, reject duplicate listeners, and launch Relay once.

### September 18, 2026 - provider error diagnostics

- Confirmed that the OpenAI badge only indicates key presence, not key validity,
  project quota, billing, permissions, or model access.
- Replaced the generic provider-unavailable response with safe categories for
  authentication, insufficient quota/billing, rate limit, model access, invalid
  request, and network failures.
- Added tests that diagnostics remain useful without echoing provider secrets.
- Re-ran the full suite after the diagnostics change: all 27 tests passed, Python
  compilation passed, and `git diff --check` reported no formatting errors.

### September 18, 2026 - Gemini free-tier provider

- Selected Gemini Flash as the primary no-payment demo provider based on Google's
  documented free tier and structured-output support.
- Added a dependency-free Gemini GenerateContent adapter using Relay's existing
  provider-neutral model contract.
- Added safe Gemini diagnostics for authentication, quota, model, request, and
  network failures without exposing the API key.
- Added `scripts/start_gemini.ps1` for secure invisible key entry and clean provider
  selection.
- Updated both dashboard and CLI provider selection: Gemini, then OpenAI, then offline.
- Increased the dashboard build identifier to `2026.09.18.3`.
- Added three Gemini adapter tests; all 30 project tests and compilation checks pass.

### September 18, 2026 - Gemini 503 resilience

- Confirmed from the dashboard that the Gemini key authenticated far enough to reach
  the provider, but the selected model returned HTTP 503 (temporary unavailability).
- Changed the default demo model to the lighter free-tier-capable
  `gemini-3.1-flash-lite` model.
- Added two bounded automatic retries for HTTP 503 responses and a Flash-Lite fallback
  when a different Gemini model is configured.
- Preserved interruption semantics because retry waits remain asynchronous and cancellable.
- Improved the exhausted-retry message and updated the dashboard build to `2026.09.18.4`.
- Added a recovery regression test; all 31 tests pass.

### September 18, 2026 - live Gemini end-to-end verification

- User successfully ran Relay with Gemini and captured a 35-event agent timeline.
- Verified live model decisions for clarification, `build_study_plan`, and
  `search_travel` tool selection.
- Verified the full chain `spoken acknowledgement -> tool call -> grounded result ->
  model-synthesized final response` for both study and travel scenarios.
- Verified that an interruption was detected and a correction triggered replanning.
- The travel and study domain tools in this test remain deterministic demo tools;
  Gemini performs reasoning and final synthesis, but the itinerary is not yet based
  on live transport, hotel, map, weather, or booking data.
- This establishes a working provider-integrated MVP, not a production travel agent.

### September 18, 2026 - arbitrary request forwarding

- Found why custom questions outside travel/study did not work: the model received
  only a classified intent and extracted slots, not the user's original message.
- Added `request_text` to the provider-neutral model context and both Gemini/OpenAI
  payloads.
- Updated the controller prompt so general knowledge requests can return a direct
  final answer when no external tool is required.
- Added a regression test proving the complete custom request reaches the model.
- Updated the dashboard build to `2026.09.18.5`; all 32 tests pass.
- Live/current factual search remains separate work: it requires a real search or
  domain-data tool and source citations, rather than relying on model memory.

### September 18, 2026 - differentiation direction locked

- Defined **Live Context Surgery** as Relay's signature judge-facing capability.
- Chose a three-panel experience: conversation, live branch/plan graph, and agent
  inspector rather than copying an ordinary side-by-side chatbot.
- Planned visible preserved, changed, cancelled, and replanned states, including
  strike-through of obsolete work without deleting the audit history.
- Defined branch IDs and constraint-to-step/evidence dependencies as the basis for
  selective invalidation and clean multi-task isolation.
- Added `docs/UNIQUE_PRODUCT_PLAN.md` with architecture, demo scenario, build order,
  success metrics, and scope boundaries.

### September 18, 2026 - team handoff document

- Added `TEAM_HANDOFF.md` as a self-contained, shareable project explanation for the
  team and presentation preparation.
- Included the problem, solution, chatbot comparison, architecture, implementation,
  technology stack, completed work, limitations, completion estimate, roadmap,
  demonstration script, suggested slide structure, judge Q&A, run instructions, and
  key-file map.

### September 21, 2026 - branch-aware Live Context Surgery foundation

- Added `relay/plans.py` with structured context diffs, parent/child plan branches,
  branch-owned plan steps, dependency keys, and explicit execution statuses.
- Extended each task with branch history and an active branch checkpoint.
- Corrections during active work now supersede the previous branch and create a child
  branch containing changed, added, removed, and preserved constraints.
- Tool calls now carry a `branch_id` and appear as running plan steps; completion,
  failure, timeout, and cancellation update step state.
- Added foundational selective reuse: a completed step is copied as `preserved` only
  when none of its declared dependencies changed.
- Extended state snapshots with branch identity, context diff, active steps, and full
  branch history.
- Rebuilt the dashboard into three judge-facing panels: Conversation, Live Context
  Surgery, and Agent Inspector.
- Added visible context-diff cards, branch history, struck-through superseded work,
  step statuses, and a state legend.
- Updated the dashboard build to `2026.09.21.1`.
- Added context-diff and selective-preservation tests and expanded the correction test
  to verify branch 2, preserved duration, and a running plan step.
- All 34 automated tests pass; Python compilation, JavaScript syntax validation, and
  diff-format checks also pass.

### September 21, 2026 - evidence provenance and selective reasoning context

- Added structured evidence records with evidence ID, source tool, originating call,
  originating branch, dependency keys, valid branches, and invalidation branch.
- Tool results now become provenance-aware evidence instead of anonymous result
  dictionaries.
- When a new branch changes a constraint, evidence depending on that constraint is
  marked `invalidated`; unaffected evidence is marked `preserved` and explicitly made
  valid in the child branch.
- Gemini/OpenAI model context now receives only evidence valid for the active branch,
  with safe provenance metadata attached.
- Invalidated evidence remains in the task audit history so the UI can explain why it
  was excluded.
- Added an Evidence Provenance panel showing source, status, active-branch inclusion,
  and dependency keys.
- Updated the dashboard build to `2026.09.21.2`.
- Added a regression test proving a budget change invalidates price evidence while
  preserving country-dependent specification evidence.
- All 35 tests pass; Python compilation, JavaScript syntax validation, and diff checks
  pass.

### September 21, 2026 - live parallel cited research

- Added a `research` intent with persistent topic, budget, and priority corrections.
- Added `parallel_research` to the dynamic tool manifest and offline model routing.
- A single research plan now fans out into three independently cancellable calls:
  overview, applications, and limitations/risks.
- Added batch-aware orchestration: each completed call becomes cited evidence, while
  final model synthesis waits until every active parallel call has finished.
- Added `relay/research.py`, a key-free live connector using the public MediaWiki
  generator search, plain-text extracts, page information, and canonical URLs.
- Updated provider instructions to cite only URLs present in grounded evidence and
  never invent citations.
- Added visible progress messages while parallel evidence remains outstanding.
- Updated the dashboard build to `2026.09.21.3` and added a Live Research shortcut.
- Added tests for research intent correction, three-call fan-out/batch completion, and
  MediaWiki citation parsing.
- All 38 automated tests pass; Python compilation, JavaScript syntax, and diff checks
  pass.
- Live-smoke-tested the local connector against Wikipedia and retrieved the cited
  `Quantum computing` article successfully.
- Current scope limitation: MediaWiki provides reliable encyclopedic research, not
  live commerce prices, product inventory, news breadth, or general web ranking.

### September 21, 2026 - measurable interruption proof

- Added session-scoped runtime metrics for acknowledgement latency, cancellation
  latency, interruptions, replans, cancelled calls, stale results rejected, evidence
  preserved, and evidence invalidated.
- Exposed metrics through every state snapshot and added a live Reliability Metrics
  panel to the dashboard.
- Stale-result trace actions now include the updated state snapshot, allowing the
  rejection counter to change immediately in the UI.
- Added a one-click interruption demonstration: it starts a four-second Delhi tool
  call, interrupts after 1.2 seconds with Jaipur, and allows the obsolete Delhi result
  to return so Relay visibly rejects it.
- Added regression assertions for interruption, cancellation, replanning, and stale
  result counters.
- Updated the dashboard build to `2026.09.21.4`.
- All 38 tests pass; Python compilation, JavaScript validation, and diff checks pass.

### September 21, 2026 - interruption-window clarity

- Identified a demonstration/usability problem: the fast acknowledgement looked like
  a completed answer, and short reasoning-only requests could finish before a human
  had time to interrupt them.
- Added explicit `acknowledgement` and `interruptible` action metadata.
- Styled acknowledgements as `ACKNOWLEDGED · STILL LISTENING` instead of ordinary
  assistant answers.
- Added a live work indicator above the composer telling the user to send another
  message while Relay is working.
- Kept normal reasoning responses fast; only deterministic travel/study demo tools
  receive a configurable six-second demonstration delay.
- Updated the dashboard build to `2026.09.21.5`.
- Added acknowledgement-contract assertions; all 38 tests and validation checks pass.

### September 21, 2026 - multi-task workspace and context isolation

- Added structured summaries for every session task: ID, intent, status, active flag,
  branch identity, slot count, and valid evidence count.
- Exposed the session task registry through state snapshots.
- Added Session Tasks cards to the dashboard with active, paused, completed, and
  superseded states.
- Added one-click Resume controls for paused travel, study, and research tasks.
- Corrected model-final lifecycle behavior so completed model tasks are also marked
  complete in the task registry and active branch.
- Added task-switch and task-resume reliability metrics.
- Added a regression test proving evidence isolation: Delhi evidence is unavailable
  inside a database study task and is restored only after the travel checkpoint resumes.
- Extended the orchestrator pause/resume test to verify two task cards, the correct
  active task, and the resume metric.
- Updated the dashboard build to `2026.09.21.6`.
- All 39 tests pass; Python compilation, JavaScript validation, and diff checks pass.

### September 22, 2026 - semantic Interruption Impact Engine

- Added `relay/impact.py` with explainable dependency-impact classification.
- The engine combines exact key matching, dependency-name overlap, semantic concept
  aliases, changed-value token overlap, and configurable confidence thresholds.
- Added semantic concepts for cost, battery, performance, location, time, topic,
  priority, and platform constraints.
- Plan branches now record an impact decision for every prior step with target type,
  action, score, matched dependencies, and human-readable reasons.
- Evidence reconciliation now uses semantic impact decisions rather than only exact
  key intersection.
- Running affected steps are classified for cancellation; completed affected evidence
  is invalidated; unrelated completed work is preserved.
- Added an Interruption Impact Engine dashboard panel showing action, percentage impact,
  and reasoning for every decision.
- Updated the dashboard build to `2026.09.22.1`.
- Added four impact-engine regression tests, including `budget` -> `price_search` and
  `priority=battery` -> `battery_reviews` semantic relationships.
- Expanded the branch correction test to verify a 100% cancellation-impact decision.
- All 43 tests pass; Python compilation, JavaScript validation, and diff checks pass.
- Added `docs/VALIDATION_PLAN.md` defining the required full-system validation gate,
  failure injection, performance, security, UI, provider, and isolation scenarios.

### September 22, 2026 - full-system validation and hardening

- Expanded the suite from 43 to 62 automated tests.
- Added race and concurrency scenarios for three-call cancellation, reverse-order
  completion, duplicate/unknown/late results, rapid three-branch correction, and
  cancellation during model reasoning.
- Added HTTP-boundary tests for valid input, empty input, oversized bodies, dashboard
  delivery, and static path traversal.
- Fixed numeric schema validation so booleans cannot satisfy integer/number types.
- Added credential-pattern redaction and bounded, single-line external error text.
- Added a 2,000-action dashboard retention limit with offset-aware cursor continuity.
- Browser-smoke-tested the Delhi-to-Jaipur judge scenario, including visible
  acknowledgement, cancellation, context surgery, 100% impact explanation, stale
  result rejection, and Jaipur-only final output.
- Validated the 390 px responsive breakpoint with no horizontal document overflow.
- Found an older Gemini Relay process still occupying port 8000 and isolated the
  current offline build on port 8010; this explains why code changes could appear
  missing until the old server is stopped.
- Added exclusive Windows port binding and a clear occupied-port startup error so two
  Relay builds cannot silently share traffic again.
- Updated the source build to `2026.09.22.2`.
- Added `docs/VALIDATION_REPORT.md` with evidence, defects, remaining checks, and the
  release-gate decision.

### September 29, 2026 - general-purpose conversation and context ledger

- Replaced the domain-sounding provider instruction with a general-purpose assistant
  contract covering normal conversation, explanations, writing, brainstorming, coding
  guidance, and planning.
- Clarified that the tool manifest limits external actions, not conversational topics.
- Added an ambiguity rule so requests such as `I need fruits` produce a useful
  clarification instead of a false travel/study/research-only limitation.
- Added bounded session-scoped conversation memory with 40 retained turns.
- Passed the full memory ledger to both Gemini GenerateContent and OpenAI Responses
  adapters so follow-ups can use previously supplied preferences and details.
- Preserved the latest instruction as authoritative so older history cannot override a
  correction or goal switch.
- Added `conversation_history`, `memory_turn_count`, and `memory_turn_limit` to state
  snapshots.
- Added a visible Session Context Ledger showing the six most recent remembered turns
  and total bounded-memory usage.
- Generic branch forks now include a structured `goal` change in the context diff even
  when there are no domain-specific slots.
- Added a `reasoning_cancelled` trace and visible chat notification when an ordinary
  Gemini/OpenAI reasoning request is superseded before completion.
- Updated the dashboard build to `2026.09.29.1`.
- Added provider-payload, conversation-memory, retention, goal-diff, and reasoning-
  cancellation regression coverage.
- All 65 automated tests pass; Python compilation, JavaScript syntax, and diff checks
  pass.
- The currently running Gemini process is still build `2026.09.22.2`; it must be
  restarted through `scripts/start_gemini.ps1` before manually testing these changes.

### September 29, 2026 - dynamic capability registry and key-free integrations

- Added `relay/integrations.py` with two provider-independent read-only tools.
- Added `get_current_weather`, which geocodes a named place and retrieves current
  temperature, apparent temperature, humidity, precipitation, weather code, wind,
  timezone, coordinates, observation time, and citation URLs from Open-Meteo.
- Added `calculate`, a restricted AST arithmetic evaluator that rejects names, function
  calls, attributes, unsafe exponents, excessive nesting, and oversized results.
- Registered both integrations in the dynamic manifest with JSON-schema arguments,
  read-only retry policy, provenance, and normal Relay cancellation handling.
- Added a visible Live Capability Registry that lists every available tool, description,
  and whether it is read-only or requires approval.
- Changed completed same-intent requests to fork a fresh goal branch.
- Added goal-only evidence invalidation so data from a completed Delhi/weather question
  cannot silently ground a later Mumbai or unrelated question.
- Updated the dashboard build to `2026.09.29.2`.
- Added six integration, safety, capability-manifest, and goal-isolation tests.
- All 71 automated tests pass; compilation, JavaScript syntax, and diff checks pass.
- Live-smoke-tested Open-Meteo with Bengaluru and received cited current conditions.
- The user must restart the older Gemini process to load this new build; the API key is
  intentionally not read from or copied out of the running process.

### September 29, 2026 - cancel-and-replace and provider-resilient results

- Fixed replacement phrases such as `Actually cancel cars. Compare electric scooters`
  so they replan instead of cancelling the entire session task.
- Made the newest explicit research command authoritative and exposed the changed topic
  in the branch context diff.
- Added distinct weather and calculation intents; weather locations no longer appear as
  travel destinations, and arithmetic expressions are extracted for offline execution.
- Added deterministic routing for weather and calculator tools in offline mode.
- Added a grounded-evidence fallback: if Gemini/OpenAI fails only during the second,
  post-tool synthesis call, Relay returns the already accepted result and citations.
- Added a visible dashboard notice whenever this fallback is used.
- Updated the dashboard build to `2026.09.29.3`.
- Expanded regression coverage to 77 tests, including the exact failing screenshots'
  interruption wording and a simulated provider synthesis timeout.

### September 30, 2026 - GitHub submission preparation

- Audited the local repository against the required GitHub checklist.
- Confirmed source, README, validation evidence, and teammate documentation are present.
- Confirmed no GitHub remote or initial tracked commit exists yet; publication is waiting
  for the user's GitHub handle, repository name, and visibility choice.
- Added `AI_DISCLOSURE.md` describing runtime model use, development assistance,
  external evidence providers, key handling, and human verification.
- Added `docs/GITHUB_SUBMISSION_CHECKLIST.md` with truthful Ready, Pending, and Not
  Applicable states, the proposed repository structure, release gates, and tag steps.
- Added a submission-artifact index to the README.
- Presentation and video remain explicitly pending; no placeholder is represented as a
  completed submission artifact.
- Confirmed the intended GitHub owner as `KasarapuRajeev`. The GitHub CLI is not
  installed on the laptop, so repository creation/publishing is waiting for the final
  repository name and visibility and will use a secure browser or authenticated Git
  workflow without sharing credentials.
- Confirmed that the submission repository should be public.
- The user created the public repository at
  `https://github.com/KasarapuRajeev/relay-interruptible-agent`; remote verification
  confirmed it is reachable and empty before the first source push.
- Re-ran all 77 tests and the credential-pattern scan before publication.
- Created the reviewed initial commit `a1bd394` and pushed the `main` branch to the
  public GitHub repository. The final submission tag remains intentionally pending
  until the presentation and video artifacts are complete.
- The team confirmed that the presentation is complete. Its file or share link still
  needs to be added to the repository; the demonstration video remains pending.
- Selected a split production architecture: Vercel for the editable static dashboard
  and Git previews, Render for the stateful Python interruption runtime.
- Added Render-compatible host/port binding, `.python-version`, a secret-safe
  `render.yaml`, deployment documentation, and automated environment-binding coverage.
- Kept the Gemini key backend-only and deferred `vercel.json` until Render supplies the
  final backend hostname, avoiding a broken or placeholder production proxy.
- All 83 automated tests, Python compilation, JavaScript syntax, diff validation, and
  credential-pattern scanning pass for the deployment-ready source.
- Created the Render Blueprint and deployed `relay-interruptible-agent-api` on the
  free plan from commit `0412231`.
- Verified the public production health endpoint returned HTTP 200 with Gemini and
  build `2026.09.29.3`.
- Added `vercel.json` with `web` as the static output directory and a production
  `/api/:path*` rewrite to the stateful Render backend.
- The remaining hosting step is importing the repository into Vercel and validating
  the public frontend end to end.
- Deployed the static dashboard to Vercel and verified that it reached the Render
  backend, reported Gemini build `2026.09.29.3`, and loaded all five capabilities.
- The first production calculator smoke test exposed a provider/tool boundary defect:
  Gemini selected `calculate` but omitted its required argument even though Relay had
  already parsed the expression into live session state.
- Fixed the boundary so tool fields declared in the manifest are reconciled from the
  newest authoritative session slots before validation. Provider-only fields remain
  untouched, while stale or missing provider arguments can no longer discard the
  user's latest structured instruction.
- Production action inspection then identified the actual immediate failure: the
  Render secret had a trailing newline, which Python rejected as an HTTP header.
- Provider adapters now trim surrounding secret whitespace at startup. The external
  error sanitizer also redacts alternate Google `AQ.` credentials and complete invalid
  header-value diagnostics, with regression coverage. Because the previous public
  action payload contained the credential, the deployed Gemini key must be revoked and
  replaced even after the payload disappears on restart.
- Deployed and verified the stable public frontend at
  `https://relay-interruptible-agent.vercel.app`.
- Repeated the production calculator smoke test after the hardened Render deployment;
  Relay acknowledged immediately, emitted the `calculate` tool call, preserved its
  evidence, and returned `4249` with the expected state, ledger, and timeline updates.
- A later production check found that HTTP messages were accepted but remained at zero
  events. The state and capability endpoints still worked, isolating the fault to the
  asynchronous action collector rather than Vercel or Render routing.
- Fixed the runtime lifecycle by retaining a strong reference to the collector task for
  the server's lifetime. Added a regression test that starts the runtime task, verifies
  it remains owned and pending, and cancels it cleanly.
- Updated the dashboard build to `2026.09.30.1` and the suite to 83 passing tests.

## 14. Documentation rule going forward

After every meaningful work session:

1. Update **Completed work** with what actually works.
2. Update **Current limitations** to avoid overclaiming.
3. Update **Current test coverage** and run the suite.
4. Update **Work remaining** and the progress estimate.
5. Append a dated entry to **Change log** describing files and behavior changed.
