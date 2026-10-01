# Relay — Team Handoff and Presentation Brief

**Hackathon:** Samsung PRISM — Theme 05: Interruptible Real-Time Agents
**Project name:** Relay
**Document purpose:** Share this file with the team before preparing the presentation,
demo, report, or final submission.
**Current development status:** Working provider-integrated MVP; approximately 75%
of the intended hackathon submission is complete.
**Latest dashboard build:** `2026.10.01.6`
**Automated verification:** 90 tests passing

---

## 1. One-line description

> Relay is an interruption-safe execution layer for AI agents that preserves valid
> work, cancels obsolete work, rejects late results, and replans from the user's
> newest context while making the entire process visible.

Relay is not intended to be another large language model. Gemini or OpenAI supplies
reasoning; Relay controls task state, interruptions, tools, cancellation, recovery,
and result validity.

---

## 2. Problem statement

Most AI assistants follow a turn-based pattern:

1. Listen to the request.
2. Think or call tools.
3. Return an answer.
4. Accept the next request.

Real users do not behave this cleanly. They interrupt, correct a detail, change a
constraint, pause one task, start another task, or change their goal while work is
still executing.

For example:

```text
User: Find the best laptop under INR 70,000 for video editing.
User, during the search: Actually keep it under INR 55,000 and prioritize battery life.
```

A conventional assistant may finish the original search, mix the two requirements,
restart everything, or show a late result based on the obsolete budget. Relay is
designed to prevent those failures.

---

## 3. Our solution

Relay keeps accepting input while reasoning and tools run asynchronously. When new
input arrives, it determines whether the user is correcting, cancelling, pausing,
resuming, or switching the active task.

Relay then:

1. Acknowledges the user immediately.
2. Detects the interruption.
3. Cancels outdated calls where possible.
4. Updates structured state instead of relying only on chat history.
5. Preserves constraints and results that remain valid.
6. Invalidates results that conflict with corrected constraints.
7. Replans using the latest complete request and valid evidence.
8. Rejects late results from cancelled or obsolete calls.
9. Produces a final answer based only on the active task state.

---

## 4. Difference between Relay and an ordinary chatbot

| Ordinary chatbot | Relay |
|---|---|
| Primarily generates replies | Manages ongoing asynchronous work |
| Treats new text as another prompt | Classifies corrections, pauses, cancellations and task switches |
| May complete an outdated request | Cancels or invalidates outdated work |
| Uses conversation history as memory | Uses structured tasks, constraints, versions and checkpoints |
| May display a late response | Verifies task/call validity before accepting a result |
| Often regenerates the entire answer | Preserves valid context and changes affected parts |
| Usually exposes only messages | Exposes state, calls, cancellations and execution events |
| Commonly focuses on one active flow | Supports paused and resumable session tasks |
| Model controls most behavior | Relay controls execution; the model provides reasoning |

The key distinction is:

> A chatbot answers messages. Relay controls which ongoing work is still allowed to
> influence the answer.

---

## 5. Signature differentiation: Live Context Surgery

The planned signature feature is called **Live Context Surgery**.

Every user correction will visibly classify work into four categories:

- **Preserved:** still-valid steps, facts and evidence.
- **Changed:** requirements explicitly replaced by the user.
- **Cancelled:** running work that has become irrelevant.
- **Replanned:** replacement work created for the latest goal.

Obsolete work will be struck through in the plan view but kept in the audit history.
It will not be included in the active model context or final answer.

Example:

```text
Original goal: Laptop under INR 70,000 for video editing

User correction:
Budget: INR 70,000 -> INR 55,000
Priority: Video editing -> Battery life

PRESERVED   Product specifications
CANCELLED   INR 70,000 price searches
INVALIDATED Editing-first ranking
REPLANNED   INR 55,000 product search
NEW         Battery comparison
```

This is the core feature that should make Relay visually and technically memorable
to judges.

---

## 6. Current system flow

```text
User message
    |
    v
Input event queue
    |
    +----> Fast path: immediate acknowledgement
    |
    v
Intent and constraint update
    |
    +----> Detect interruption
    |          |
    |          +----> Cancel active obsolete calls
    |          +----> Invalidate conflicting evidence
    |
    v
Build current model context
    |
    v
Gemini / OpenAI structured decision
    |
    +----> Clarification
    +----> Final response
    +----> Validated tool call
                     |
                     v
              Tool result received
                     |
                     v
        Verify task ID and call ID validity
                     |
          +----------+----------+
          |                     |
      Valid result          Stale result
          |                     |
      Store evidence       Reject and trace
          |
      Model synthesis
          |
      Final response
```

---

## 7. How interruption handling is implemented

### 7.1 Independent asynchronous queues

Relay uses separate `asyncio.Queue` objects for input and output. The input queue
continues accepting messages while slow model or tool work is running.

### 7.2 Fast and slow paths

- The fast path immediately acknowledges the user.
- The slow path performs reasoning and launches tools.

The user therefore does not have to wait for the complete task before interrupting.

### 7.3 Structured state

Relay stores information such as:

```json
{
  "intent": "travel_planning",
  "slots": {
    "destination": "Delhi",
    "budget_inr": 30000,
    "duration_days": 3
  },
  "version": 1,
  "status": "working",
  "task_id": "...",
  "active_call_ids": ["..."]
}
```

If the user changes Delhi to Jaipur and INR 30,000 to INR 20,000, Relay preserves
the three-day duration and changes only the corrected constraints.

### 7.4 Call correlation

Every external call receives a unique `call_id`. A returned result is accepted only
if that call is still active for the current task.

### 7.5 Task generation/version

Every replan advances the task generation. A reasoning result from an earlier
generation cannot overwrite the current task.

### 7.6 Stale-result rejection

Some HTTP operations cannot be physically stopped after reaching an external server.
Relay therefore combines cancellation with result validation. Late results are
dropped and recorded as `stale_tool_result_dropped`.

### 7.7 Pause, switch and resume

Relay stores session-scoped task checkpoints. A user can pause travel research,
complete a study task, and resume the travel task with its task ID and constraints.

---

## 8. Technologies used

### Backend and orchestration

- Python 3.10–3.12
- `asyncio`
- `asyncio.Queue`
- Asynchronous tasks and cancellation
- Dataclasses for typed protocol records
- UUIDs for event, task and tool-call correlation
- Thread-safe bridge between the HTTP server and async runtime

Python follows the Theme 05 execution requirements and is well suited to asynchronous
agent orchestration. Node.js or React can still be used later for the presentation
layer without replacing the Python runtime.

### Reasoning providers

- Gemini GenerateContent API
  - Current primary provider
  - Structured JSON decisions
  - Free-tier-capable Flash-Lite model
  - Bounded retry for temporary HTTP 503 failures
- OpenAI Responses API
  - Alternative provider
  - Strict structured decisions
- Offline deterministic model
  - No key required
  - Useful for repeatable demonstrations and automated tests

### Tool framework

- Dynamic tool manifests
- Parameter validation
- Read-only timeout and bounded retry
- No automatic retry for uncertain state-changing operations
- Idempotency protection for side effects
- Grounded result storage

### Frontend

- HTML
- CSS
- Browser JavaScript
- Local Python HTTP server
- Polling-based action updates

### Testing

- Python `unittest`
- 32 currently passing tests
- Compilation and diff-format checks

---

## 9. What has been built

### Completed core capabilities

- Timestamped input events
- Structured output actions
- Separate asynchronous input and output queues
- Fast acknowledgement before slow work
- Partial-transcript speculation trace
- Deterministic intent and slot extraction baseline
- Localized constraint correction
- Interruption detection
- Active-call cancellation
- Late/stale result rejection
- Result invalidation after corrected constraints
- Pause, switch and resume checkpoints
- Session-scoped task registry
- Dynamic tool manifests
- Tool-argument validation
- Read-only retry and timeout behavior
- State-changing idempotency protection
- Provider-independent model contract
- Gemini integration
- OpenAI integration
- Offline model
- Complete custom-request forwarding to the model
- Local dashboard
- Live state snapshot
- Tracked-slot display
- Agent event timeline
- Secure PowerShell launchers
- Safe provider error diagnostics
- 83 automated tests

### Successfully demonstrated

The live Gemini test produced a 35-event timeline and verified:

- Model clarification
- `search_travel` selection
- `build_study_plan` selection
- Tool-result grounding
- Model-generated final responses
- Interruption detection
- Correction and replanning

---

## 10. What is currently simulated or incomplete

- Travel and study tools return deterministic demo data.
- Travel output is not yet based on live transport, hotel, price or booking services.
- General questions reach Gemini, but current-information research is not yet backed
  by a live search connector with citations.
- The current invalidation mechanism is slot-based, not yet a full dependency graph.
- Plan branches are not yet displayed visually.
- Audio and video events exist in the protocol but are not decoded or grounded.
- Browser speech interruption is implemented with continuous recognition, interim
  transcript events, and final phrases routed through Relay's normal cancellation path.
  Raw WAV transcription and semantic audio grounding are not yet implemented.
- The dashboard uses polling and is not production infrastructure.
- The evaluation harness needs complete scenario scoring and failure injection.
- The project is not deployed publicly yet.

These limitations must be stated honestly during the presentation.

---

## 11. Current completion estimate

Overall hackathon submission readiness: **approximately 75%**.

| Area | Approximate completion |
|---|---:|
| Async agent foundation | 100% |
| Interruption and cancellation | 95% |
| Structured session state | 90% |
| Pause/switch/resume | 85% |
| Gemini integration | 90% |
| General custom requests | 85% |
| Dynamic tool framework | 80% |
| Dashboard MVP | 75% |
| Automated tests | 80% |
| Live search and citations | 10% |
| Real domain tools | 25% |
| Plan dependency graph | 10% |
| Voice/multimodal behavior | 35% |
| Evaluation metrics | 35% |
| Deployment and final pitch | 10% |

These percentages are planning estimates, not formal measurements.

---

## 12. Recommended future implementation roadmap

### Phase 1 — Branch-aware execution core

1. Add immutable session event records.
2. Add `branch_id`, `step_id` and `evidence_id`.
3. Represent plans as steps with explicit dependencies.
4. Map constraints to affected steps and evidence.
5. Compute a structured context diff after each interruption.
6. Preserve unaffected graph nodes and invalidate affected descendants.

**Result:** Relay performs selective recovery instead of coarse replanning.

### Phase 2 — Unique judge-facing interface

Build a three-panel interface:

1. **Conversation:** user messages, acknowledgements and answers.
2. **Live Plan Graph:** queued, running, preserved, cancelled and completed steps.
3. **Agent Inspector:** active context, task branches, calls, evidence and metrics.

Obsolete plan steps should visibly strike through while the new branch animates.

### Phase 3 — Live research

1. Add a real search connector.
2. Launch multiple read-only searches concurrently.
3. Store source URLs and evidence provenance.
4. Cancel searches affected by new constraints.
5. Reuse still-valid evidence.
6. Produce citation-backed final answers.

### Phase 4 — Multi-task workspace

1. Add visible task cards.
2. Allow pause, switch and resume from the interface.
3. Keep context and evidence isolated per task.
4. Add a test for zero cross-task contamination.

### Phase 5 — Metrics and evaluation

Measure and display:

- Acknowledgement latency
- Cancellation-signal latency
- Interruption-to-replan latency
- Percentage of valid work preserved
- Number of obsolete calls cancelled
- Number of stale results rejected
- Citation coverage
- Cross-task context contamination
- Recovery success under delayed/out-of-order results

### Phase 6 — Streaming and multimodal input

1. Stream transcript chunks while the user is speaking.
2. Begin safe speculative retrieval before end-of-utterance.
3. Detect corrections during speech.
4. Add image/document context as a later multimodal input.

### Phase 7 — Finalization

1. Complete evaluation scenarios.
2. Add failure injection.
3. Polish UI and accessibility.
4. Deploy the dashboard.
5. Record a backup demonstration video.
6. Prepare architecture diagram, pitch deck and judge Q&A.

---

## 13. Recommended final demonstration

Use one strong scenario instead of many shallow examples.

### Scenario

```text
User: Research the best laptop under INR 70,000 for video editing.
```

Relay begins parallel product, benchmark and price searches.

```text
User: Actually make it INR 55,000 and prioritize battery life.
```

The dashboard should show:

- `interruption_detected`
- Changed budget and priority
- Obsolete searches cancelled
- Still-valid specifications preserved
- New price and battery searches started
- Deliberately delayed old result rejected

Next:

```text
User: Pause this and create a three-day database exam study plan.
```

Relay switches tasks and completes the study plan.

Finally:

```text
User: Resume the laptop research.
```

Relay restores the laptop branch and produces a cited answer based exclusively on
the corrected INR 55,000/battery-first goal.

This single demonstration proves responsiveness, cancellation, selective recovery,
stale-result safety, multitasking, context isolation and explainability.

---

## 14. Suggested presentation structure

### Slide 1 — Title

**Relay: Live Context Surgery for Interruptible AI Agents**

### Slide 2 — Problem

Show how conventional agents mishandle mid-task corrections and late results.

### Slide 3 — Insight

Users do not merely chat; they redirect ongoing work. The execution layer must be
interruptible and state-aware.

### Slide 4 — Solution

Explain fast acknowledgement, cancellation, selective context updates and replanning.

### Slide 5 — Architecture

Show queues, state engine, reasoning adapter, tool registry and result validator.

### Slide 6 — Live Context Surgery

Show preserved, changed, cancelled and replanned work.

### Slide 7 — Demonstration

Use the laptop research interruption scenario.

### Slide 8 — Reliability

Show call IDs, stale-result rejection, retries, idempotency and automated tests.

### Slide 9 — Technology

Python asyncio, Gemini/OpenAI adapters, structured protocol, tool manifests and web UI.

### Slide 10 — Current results

Provider-integrated MVP, 32 tests, live interruption flow and task checkpoints.

### Slide 11 — Roadmap

Dependency graph, live search, voice interruption, metrics and deployment.

### Slide 12 — Closing

> Other agents restart after interruption. Relay preserves valid progress, cancels
> obsolete work, and proves the recovery live.

---

## 15. Judge questions and concise answers

### Is Relay just a Gemini wrapper?

No. Gemini makes structured reasoning decisions. Relay owns the event queues, task
state, interruption detection, cancellation, tool lifecycle, checkpoint recovery,
stale-result rejection and visualization. The model can be replaced without replacing
the Relay runtime.

### Why not open a new chat?

A new chat abandons running work and context. Relay changes direction inside an active
task, preserves valid evidence and prevents obsolete work from influencing the result.

### Can an HTTP request always be cancelled?

No. Relay sends cancellation where possible and also validates every returned result.
If a cancelled request returns late, its call ID and task generation are obsolete, so
the result is rejected.

### Why Python?

The Theme 05 guide targets Python 3.10–3.12, and Python's asynchronous ecosystem is
appropriate for concurrent models, tools and evaluation. The frontend can be upgraded
independently.

### What is the main innovation?

Branch-aware selective recovery: identify exactly which work became invalid, preserve
everything else, and display the change live.

### What is real today?

The async runtime, provider integration, structured state, interruption detection,
cancellation, stale-result rejection, checkpoints, tool contract, UI timeline and test
suite are implemented. Live search and full dependency-based plan repair are next.

---

## 16. Running the current project

Open PowerShell:

```powershell
cd "C:\Users\rajee\OneDrive\Documents\ChatGPT\projectsamsung"
powershell -ExecutionPolicy Bypass -File .\scripts\start_gemini.ps1
```

Paste the Gemini API key when prompted. Input remains invisible for security.

Open:

```text
http://127.0.0.1:8000
```

The provider badge should show:

```text
Gemini · 2026.10.01.6
```

Never paste API keys into code, documentation, screenshots, Git commits, or team chat.

To run tests:

```powershell
$python = "C:\Users\rajee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python -m unittest discover -s tests -v
```

---

## 17. Important project files

| File/folder | Purpose |
|---|---|
| `relay/protocol.py` | Input, action and state-snapshot contracts |
| `relay/orchestrator.py` | Fast/slow paths, interruption and tool lifecycle |
| `relay/intent.py` | Baseline intent and constraint extraction |
| `relay/tasks.py` | Task checkpoints and result invalidation |
| `relay/tools.py` | Dynamic tools, validation, retry and idempotency |
| `relay/models.py` | Provider-independent model contract |
| `relay/gemini_adapter.py` | Gemini structured-output integration |
| `relay/openai_adapter.py` | OpenAI structured-output integration |
| `relay/web.py` | Local dashboard backend |
| `web/` | Dashboard frontend |
| `tests/` | Automated behavior and safety tests |
| `scripts/start_gemini.ps1` | Secure Gemini launcher |
| `PROJECT_NOTES.md` | Detailed chronological development log |
| `docs/UNIQUE_PRODUCT_PLAN.md` | Differentiation and future architecture |

---

## 18. Final team message

The project already has the difficult orchestration foundation. The next objective is
not to add random chatbot features. The team should concentrate on making Relay's
unique behavior undeniable:

1. Represent plans and dependencies explicitly.
2. Show context changes visually.
3. Preserve valid work selectively.
4. Add real parallel search with citations.
5. Measure and demonstrate interruption recovery.

The final project should be presented as an execution-control system for any AI model,
not as a travel planner, study planner, or general chatbot.
