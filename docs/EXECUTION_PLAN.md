# Relay - execution plan

## Product thesis

Relay is a protocol-first runtime for agents that remain responsive while perception,
reasoning, and tools execute concurrently. Its defensible contribution is reliable
interruption recovery: cancel invalid work, update only changed slots, suppress stale
results, and continue from a consistent session snapshot.

## Scoring-first priorities

| Priority | Guide weight | Engineering focus | Proof |
|---|---:|---|---|
| P0 | 40% | Correct tools, arguments, snapshots, grounded final | Golden trace tests |
| P0 | 35% | Cancellation, no stale reruns, clean replanning | Adversarial timing tests |
| P1 | 15% | Substantive fast-path action in a few hundred ms | Virtual-clock latency metric |
| P1 | 10% | JSON schema, identifiers, exactly-once side effects | Contract and idempotency tests |
| Multiplier | up to 1.2x / multimodal 1.5x | Natural, truthful responses plus audio/frame grounding | Audio and PNG scenarios |

## Scope lock

### Build

- Two asynchronous queues: timestamped input events and output actions.
- Fast path for acknowledgement, clarification, and restrained progress narration.
- Slow path for model reasoning, tools, audio, and image grounding.
- Versioned state snapshots with intent, slots, status, and active call IDs.
- Cancellation and stale-result suppression for superseded calls.
- Dynamic tool manifests and exactly-once protection for state-changing calls.
- Deterministic virtual clock, latency/fault injection, and full trace logs.
- Text, WAV, and PNG scenarios.

### Do not build

- Wake-word detection, speech synthesis tuning, long-term profiles, or UI polish.
- A new foundation model. Model providers remain adapters behind the runtime.

## Daily execution, September 17-25

### Sep 17 - foundation (complete when all base tests pass)

- Python 3.10-3.12 project structure.
- Protocol dataclasses and JSON-safe action schema.
- Dual-queue orchestrator with fast and slow paths.
- Localized slot correction, cancellation, stale-result suppression, and task checkpoints.
- Dynamic tool registry and idempotency guard.
- Virtual clock skeleton, CLI demo, and unit tests.

### Sep 18 - protocol and task completion

- Freeze JSON schemas against the released evaluation examples, if available.
- [x] Implement tool-result correlation, timeouts, bounded retries, and error grounding.
- [x] Prevent automatic retries for state-modifying tools with uncertain outcomes.
- Add state-modifying tool lifecycle: propose, reserve, commit, reconcile.
- Golden tests for flight search, booking, and ticket creation.

### Sep 19 - interruption recovery

- Build an explicit dependency graph from slots to tool calls.
- Cancel only calls invalidated by corrected slots.
- Reuse unaffected read-only results.
- Add adversarial races: result-before-cancel, cancel-before-result, double result.
- Record interruption-to-cancellation latency.

### Sep 20 - floor management and latency

- Add fast-path response policy: substantive, truthful, and non-repetitive.
- Add speculative read-only execution with confidence gates.
- Prohibit speculative state modification.
- Measure input-to-first-action and interruption-to-cancel percentiles.

### Sep 21 - multimodal grounding

- Decode supplied WAV and PNG inputs behind an immediate acknowledgement.
- Add pluggable transcription and vision adapters.
- Ground frame/manual answers and ask clarification when perception is ambiguous.
- Add 30% audio and 20% visual scenarios to the local suite.

### Sep 22 - deterministic evaluation harness

- Complete virtual scheduling, mock tool latency, faults, and event replay.
- Produce machine-readable trace logs and per-scenario score reports.
- Implement nine canonical public-style scenarios.
- Run all tests on Python 3.10, 3.11, and 3.12 where available.

### Sep 23 - model integration and quality

- [x] Define and test a provider-independent structured model-adapter contract.
- Connect one real model behind a strict structured-output adapter.
- Add validation and deterministic fallback when model output is malformed.
- Tune transcript naturalness without sacrificing truthfulness or latency.
- Eliminate duplicate calls and ungrounded completion claims.

### Sep 24 - submission rehearsal and freeze

- Run repeated clean-room installs and the complete scenario suite.
- Record the main interruption demo and one multimodal demo.
- Finish architecture, protocol, limitations, and reproducibility documentation.
- Freeze features; fix only correctness, safety, and packaging defects.

### Sep 25 - submission

- Run final smoke test from a clean environment.
- Verify the 120-second scenario cap and 300-second warm-up cap.
- Package source, setup command, test command, traces, and demo assets.
- Submit early enough to leave recovery time for upload problems.

## MVP acceptance gates

1. The first substantive action is emitted before slow-path work begins.
2. Every tool call has a unique `call_id` and appears in the state snapshot.
3. A corrected slot invalidates obsolete work and preserves unaffected slots.
4. A cancelled call can never produce a final answer.
5. Repeated state-changing requests cannot execute twice.
6. Every final response includes a valid state snapshot and grounded result.
7. Tests replay deterministically and produce a complete input/action trace.
8. No state survives the session boundary.

## Primary demo

1. Stream: "Plan a three-day trip to Delhi under INR 30,000."
2. Emit an acknowledgement immediately; start a travel search.
3. Interrupt: "Actually, Jaipur, and make it INR 20,000."
4. Emit cancellation for the Delhi call; retain the three-day slot.
5. Start a Jaipur call with the corrected snapshot.
6. Deliver a late Delhi result; visibly drop it as stale.
7. Accept the Jaipur result and emit a grounded final response.
