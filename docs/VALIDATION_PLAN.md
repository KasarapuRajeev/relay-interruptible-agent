# Relay Full-System Validation Plan

This plan is the mandatory gate before deployment, presentation polish, or additional
experimental features. Every scenario must produce captured evidence and a clear
pass/fail result.

## 1. Core protocol

- Input and output queues remain independent.
- Fast acknowledgement occurs before slow work.
- Partial transcripts produce speculation traces without committing side effects.
- Every action and event remains JSON serializable.

## 2. Interruption lifecycle

- Interrupt during model reasoning.
- Interrupt during one deterministic tool call.
- Interrupt during three parallel research calls.
- Cancel every affected call exactly once.
- Create a child branch with the correct parent.
- Ensure the corrected branch alone can produce the final answer.

## 3. Impact engine

- Exact dependency match: `budget` -> `budget`.
- Semantic alias match: `budget` -> `price_search`.
- Changed-value match: `priority=battery` -> `battery_reviews`.
- Unrelated dependency preservation.
- Running affected step -> cancel.
- Completed affected evidence -> invalidate.
- Completed unaffected evidence -> preserve.
- Every decision includes score, dependency match, and human-readable reason.

## 4. Stale and out-of-order results

- Cancelled result returns late and is rejected.
- Old reasoning generation returns late and is ignored.
- Parallel results arrive in reverse order.
- Duplicate result delivery cannot duplicate evidence.
- Result with an unknown call ID is rejected.

## 5. Evidence integrity

- Every accepted result has evidence, task, branch, call, and source IDs.
- Invalid evidence never enters model context.
- Preserved evidence appears in the child branch.
- Citations originate only from accepted evidence.
- No invented URL appears in the final answer.

## 6. Multi-task isolation

- Pause travel and start study.
- Pause research and start travel.
- Resume each task from its own branch.
- Verify no evidence crosses task boundaries.
- Verify task cards and metrics match backend state.

## 7. Tool safety

- Invalid arguments are rejected before execution.
- Read-only failure retries only within its bound.
- Read-only timeout cancels and retries safely.
- State-changing timeout is not blindly retried.
- Duplicate idempotency key blocks a repeated side effect.

## 8. Provider behavior

- Offline deterministic provider.
- Gemini valid response.
- Gemini malformed structured response.
- Authentication failure.
- Rate-limit failure.
- HTTP 503 retry and recovery.
- Exhausted HTTP 503 retries.
- Cancellation while an HTTP worker remains in flight.

## 9. Live research

- Live MediaWiki overview search.
- Applications and limitations fan-out.
- Source title, extract, and canonical URL parsing.
- Empty search result failure.
- Network failure and bounded retry.
- Interruption before all research calls finish.

## 10. UI and observable state

- Acknowledgement is visibly different from final output.
- Work indicator appears only while interruptible work is active.
- Branch history and context diff match backend state.
- Impact decisions display action, score, and reason.
- Evidence panel displays valid, preserved, invalidated, and excluded states.
- Task cards resume the correct task.
- Metrics update after cancellation and stale-result rejection.
- Layout works at desktop, tablet, and mobile widths.

## 11. Performance targets

- Acknowledgement latency is measured, not estimated.
- Cancellation signal latency is measured.
- No event-loop blocking during provider or research HTTP requests.
- A burst of user corrections leaves only the latest branch active.
- Long sessions do not grow unbounded without a configured retention policy.

## 12. Security and privacy

- API keys never appear in actions, logs, HTML, screenshots, or Git files.
- Provider errors are sanitized.
- Static-file path traversal is rejected.
- Oversized message bodies are rejected.
- Session memory is not persisted across server restarts.

## Exit criteria

- All automated tests pass.
- All critical manual scenarios pass.
- No stale or invalid evidence reaches a final answer.
- No cross-task context contamination occurs.
- All failures are visible and recoverable.
- A validation report records evidence, defects, fixes, and remaining risks.
