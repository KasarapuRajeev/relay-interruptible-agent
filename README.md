# Relay

DEMO VIDEO :  [DEMO VIDEO LINK](https://drive.google.com/drive/folders/12roblHvvfEmmFSEY_IlV6sM0Td-cYTmi?usp=drive_link)

GitHub: [KasarapuRajeev/relay-interruptible-agent](https://github.com/KasarapuRajeev/relay-interruptible-agent)

Live application: [relay-interruptible-agent.vercel.app](https://relay-interruptible-agent.vercel.app)

Production backend: [relay-interruptible-agent-api.onrender.com](https://relay-interruptible-agent-api.onrender.com)

The Vercel frontend uses relative `/api/*` requests that proxy to the stateful Render
service, so the provider key remains server-side.

Relay is a protocol-first Python runtime for Samsung Theme 05: Interruptible
Real-Time Agents. It coordinates a responsive fast path with asynchronous slow
work while keeping session state consistent across interruptions.

## Submission artifacts

| Artifact | Location / status |
|---|---|
| Source code | This repository |
| Reproduction guide | This README |
| AI disclosure | [`AI_DISCLOSURE.md`](AI_DISCLOSURE.md) |
| Validation evidence | [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md) |
| Team handoff | [`TEAM_HANDOFF.md`](TEAM_HANDOFF.md) |
| GitHub checklist | [`docs/GITHUB_SUBMISSION_CHECKLIST.md`](docs/GITHUB_SUBMISSION_CHECKLIST.md) |
| Deployment guide | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |
| Render backend | [Live](https://relay-interruptible-agent-api.onrender.com) |
| Vercel frontend | [Live](https://relay-interruptible-agent.vercel.app) |
| Presentation | Pending final deck |
| Demonstration video | Pending recording/link |
| APK/SDK | Not applicable to the current Python web/CLI runtime |

## What already works

- Timestamped input events and structured output actions on separate async queues
- Partial-transcript speculation trace
- Fast acknowledgement before slow work
- Intent and slot snapshots
- Localized slot corrections
- In-flight call cancellation
- Late/stale result suppression
- Session task registry with pause, switch, and resume checkpoints
- Branch-aware plans with parent/child history and structured context diffs
- Dependency-aware preservation of unaffected completed plan steps
- Evidence provenance with branch validity and dependency-based exclusion
- Key-free live MediaWiki research fanned out across three parallel aspects
- Citation-bearing evidence buffered until every parallel search completes
- Live acknowledgement, cancellation, interruption, stale-result, and reuse metrics
- One-click judge demo that deliberately produces an obsolete late result
- Visible session task cards with isolated evidence and one-click checkpoint resume
- Explainable semantic interruption-impact scoring for preserve/cancel/invalidate decisions
- General-purpose Gemini/OpenAI conversation instead of domain-only chat behavior
- Bounded session conversation memory for follow-ups, preferences, and prior details
- Visible Session Context Ledger showing exactly what Relay currently remembers
- Explicit cancellation traces when ordinary model reasoning is superseded
- Secret-redacted and length-bounded external error reporting
- Bounded 2,000-event dashboard retention with cursor continuity
- Dynamic tool manifests
- Live capability registry showing every available tool and its safety class
- Key-free cited current weather through Open-Meteo geocoding and forecast APIs
- Restricted local arithmetic calculator with no code/name/function execution
- Cancel-and-replace parsing so `cancel X; do Y instead` replans rather than stopping
- Grounded-result fallback when provider synthesis fails after a tool has succeeded
- JSON-schema argument validation for tool calls
- Timeouts and bounded retry for read-only tools
- No automatic retry for state-changing tools with uncertain outcomes
- Idempotency protection for state-changing tools
- Deterministic virtual-clock harness skeleton
- OpenAI Responses API adapter with strict structured decisions
- Gemini API adapter with free-tier-capable Flash model and strict structured decisions
- Three-panel dashboard with chat, Live Context Surgery, state, and event timeline

## Run

Relay requires Python 3.10-3.12 and has no runtime dependencies.

```powershell
cd "C:\Users\rajee\OneDrive\Documents\ChatGPT\projectsamsung"
$python = "C:\Users\rajee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python -m unittest discover -s tests -v
& $python -m relay.demo
```

Try these messages in order:

```text
Plan a 3-day trip to Delhi under ₹30,000
Actually change it to Jaipur under ₹20,000
Stop
```

The CLI prints the same JSON action objects that an evaluation harness consumes.

## Run the visual dashboard

Offline mode needs no API key:

```powershell
& $python -m relay.web
```

Open `http://127.0.0.1:8000` in a browser. To use OpenAI instead of the offline
adapter, set the key only in the current PowerShell session before starting:

```powershell
$env:OPENAI_API_KEY = "your-project-api-key"
$env:OPENAI_MODEL = "gpt-5.4-mini"
& $python -m relay.web
```

The simplest secure option on this Windows workspace is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_openai.ps1
```

The script prompts for the key invisibly, configures the model, rejects a duplicate
server on port 8000, and starts Relay in the same correctly configured process.

For the Gemini free-tier-capable path, create a key in Google AI Studio and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_gemini.ps1
```

Gemini is selected before OpenAI when both environment variables are present.

Build `2026.10.01.2` also protects completed tool work from a provider-side synthesis
timeout: Relay shows the accepted weather, calculation, or cited research evidence
directly and marks that fallback in the conversation.

Never paste the key into source code or commit it. The dashboard still uses
deterministic mock domain tools so interruptions can be demonstrated repeatably;
the model selects the action and synthesizes the grounded final response.

## Structure

- `relay/protocol.py`: input, action, and state-snapshot contract
- `relay/orchestrator.py`: dual-queue fast/slow coordinator
- `relay/intent.py`: deterministic baseline for intent and slot correction
- `relay/impact.py`: semantic dependency scoring and explainable impact decisions
- `relay/tasks.py`: session checkpoints and branch ownership
- `relay/plans.py`: context diffs, branches, plan steps, evidence provenance, and dependency preservation
- `relay/tools.py`: dynamic manifests and side-effect idempotency
- `relay/models.py`: provider-independent model contract and offline adapter
- `relay/openai_adapter.py`: structured OpenAI Responses API integration
- `relay/gemini_adapter.py`: structured Gemini GenerateContent API integration
- `relay/research.py`: live cited MediaWiki research connector
- `relay/integrations.py`: key-free weather and safe calculation integrations
- `relay/web.py` and `web/`: local dashboard backend and frontend
- `relay/harness.py`: virtual-clock scenario replay
- `tests/`: behavior and safety tests
- `docs/EXECUTION_PLAN.md`: scoring-first plan through September 25
- `docs/VALIDATION_PLAN.md`: complete validation matrix and exit criteria
- `docs/VALIDATION_REPORT.md`: latest evidence, defects, fixes, and remaining risks
- `docs/GITHUB_SUBMISSION_CHECKLIST.md`: publication and release checklist
- `docs/DEPLOYMENT.md`: Vercel frontend and Render backend deployment procedure
- `AI_DISCLOSURE.md`: transparent runtime and development AI usage
- `PROJECT_NOTES.md`: living teammate handoff and detailed change log

The current intent parser and domain work are deterministic baselines. A model,
speech recognizer, vision model, and scenario tools should be connected through
adapters without changing the queue protocol.

With Gemini or OpenAI configured, normal conversation is not limited to the domain
tools. The provider can answer arbitrary general questions directly, while Relay
supplies session history, latest-instruction priority, interruption cancellation, and
tool/evidence controls. External real-world actions still require an installed tool.
