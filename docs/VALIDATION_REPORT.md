# Relay Validation Report

**Date:** September 29, 2026
**Build:** `2026.09.29.3`
**Scope:** Core runtime, interruptions, evidence, tools, providers, HTTP boundary,
security, dashboard behavior, and responsive layout.

## Executive result

Relay passed all **79 automated tests**. The earlier interruption browser smoke test
also passed; a Gemini-backed browser recheck of the September 29 conversation-memory
upgrade requires restarting the currently running older Gemini process.
No stale or duplicate result entered active evidence, no cancelled branch produced the
final answer, and no tested tool error exposed a credential-shaped secret.

The build is suitable for continued feature development and hackathon demonstrations.
Live paid-provider verification remains conditional on a valid private API key, quota,
and network availability; it is not represented as completed by this report.

## Automated validation

| Area | Result | Evidence |
|---|---:|---|
| Protocol and serialization | Pass | Actions, events, traces, and snapshots are JSON-safe |
| Fast acknowledgement | Pass | Acknowledgement precedes model/tool work |
| Model interruption | Pass | An in-flight reasoning coroutine receives cancellation |
| Tool interruption | Pass | Active calls emit cancellation exactly once |
| Parallel interruption | Pass | Three research calls cancel independently |
| Stale results | Pass | Late, duplicate, and unknown call IDs are rejected |
| Out-of-order results | Pass | Reverse-order results complete once without duplicate evidence |
| Rapid corrections | Pass | Only the third/latest branch remains active |
| Context preservation | Pass | Unchanged duration and unrelated evidence remain valid |
| Semantic impact | Pass | Exact, alias, changed-value, and unrelated dependencies are classified |
| Multi-task isolation | Pass | Travel and study checkpoints do not share evidence |
| Tool safety | Pass | Schema validation, bounded retry, timeout, and idempotency pass |
| Provider adapters | Pass (mocked) | OpenAI/Gemini structured parsing and safe error mapping pass |
| Research connector | Pass (mocked) | Canonical citation parsing and empty-result failure pass |
| Secret handling | Pass | Credential-shaped secrets are redacted and errors are bounded |
| HTTP boundary | Pass | Empty/oversized bodies and static path traversal are rejected |
| Retention | Pass | Timeline is capped at 2,000 actions without breaking its cursor |

Command used:

```powershell
$python = "C:\Users\rajee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python -m unittest discover -s tests -v
```

Result: `Ran 79 tests ... OK`.

September 29 additions covered by the automated gate:

- Arbitrary general-conversation history reaches Gemini and OpenAI payloads.
- Session memory is capped and retains the most recent turns.
- Assistant and user turns appear in the returned state snapshot.
- Generic goal revisions appear in structured branch diffs.
- Superseded model reasoning emits an explicit cancellation trace.
- Restricted calculator rejects code execution and unsafe numeric operations.
- Weather geocoding/current-condition parsing includes source provenance and truthful
  unknown-location failure.
- Goal-only changes exclude evidence belonging to the superseded request.
- Cancel-and-replace wording creates a corrected research branch instead of stopping.
- Weather and arithmetic requests receive distinct intents and validated arguments.
- Accepted grounded evidence becomes the final result if provider synthesis times out.

The Open-Meteo integration was also live-smoke-tested with Bengaluru and returned
current cited conditions successfully.

## Browser smoke test

The browser test used the offline deterministic provider on port `8010` so the
current build could be isolated from an older server still using port `8000`.

Scenario:

1. Start a three-day Delhi plan under ₹30,000.
2. Confirm acknowledgement and the active-work indicator appear before completion.
3. Interrupt with Jaipur under ₹20,000.
4. Confirm the Delhi call is cancelled.
5. Allow the obsolete Delhi result to return.
6. Confirm Relay rejects it and completes only the Jaipur branch.

Observed results:

- The final build badge was verified as `Offline demo · 2026.09.22.2`.
- Branch 1 became `SUPERSEDED` and its step became `CANCELLED`.
- Branch 2 became `COMPLETED` with Jaipur, ₹20,000, and the preserved three-day duration.
- The impact panel showed `CANCEL`, `100% impact`, and both changed-dependency reasons.
- The stale-result counter increased to one.
- The final answer contained only the Jaipur plan.
- At a 390 px viewport, document width remained within the viewport and the workspace
  used its single-column breakpoint.

## Defects found and fixed during validation

1. **Numeric schema accepted booleans.** Python treats `bool` as a subtype of `int`.
   The validator now rejects booleans for integer and number fields.
2. **Tool errors could reach traces verbatim.** External errors now have credential
   redaction, newline removal, and a 300-character bound.
3. **Dashboard action history was unbounded.** It is capped at 2,000 actions with an
   offset-aware cursor so long sessions cannot grow indefinitely.
4. **An old local server can make new changes appear missing.** Port `8000` was serving
   build `2026.09.21.6`; the current build was tested separately on port `8010`.
   Windows also allowed two reusable listeners on the test port. Relay now uses
   exclusive port binding and exits with a clear message when a port is occupied.

## Conditional and remaining checks

- Run one live Gemini session with a valid key and available free-tier quota.
- Run one live OpenAI session only if the project has API billing/quota.
- Re-run the live MediaWiki smoke test on the presentation network.
- Test a real phone/tablet browser in addition to the emulated 390 px viewport.
- Perform a clean-machine installation test on Python 3.10, 3.11, and 3.12.
- Add a cancellable async HTTP client so a running provider socket can be terminated,
  not merely logically detached and ignored.

## Gate decision

**Automated gate: PASS**
**Offline browser demonstration gate: PASS**
**Live-provider gate: CONDITIONAL / credentials and quota required**
**Deployment gate: NOT YET REQUESTED**
