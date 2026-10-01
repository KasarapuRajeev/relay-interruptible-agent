# Relay Differentiation Blueprint

## Product thesis

Relay is an interruptible execution layer, not another chat model. Its defining
experience is a live comparison between what the user says and how the running plan
changes. Every interruption produces an explainable context diff, selectively
invalidates affected work, preserves unaffected work, and starts a new plan branch.

## Signature feature: Live Context Surgery

When a user changes a requirement, Relay displays four categories:

- **Preserved**: facts, evidence, and steps still valid.
- **Changed**: constraints explicitly replaced by the user.
- **Cancelled**: calls and plan steps made irrelevant by the change.
- **Replanned**: new steps created for the latest goal.

Outdated content is visibly struck through in the execution view, but remains in the
audit history. It is never included in the active reasoning context or final answer.

## Judge-facing interface

### Left: Conversation

Normal user/assistant interaction, including immediate acknowledgements and final
answers.

### Right-side execution inspector

- Current goal and constraints.
- Plan steps with states: queued, running, preserved, cancelled, complete.
- Branch lines for interruptions.
- Red strike-through for invalidated work.
- Green links for reusable evidence.
- A context-diff card for each correction.

The inspector uses focused Execution, Context, and History tabs instead of several
simultaneously scrolling columns. The pipeline header remains visible while each tab
shows one level of detail.

### Agent Inspector contents

- Active task and branch ID.
- Current context supplied to the model.
- Tool calls and evidence provenance.
- Paused task stack.
- Interruption latency and stale-result count.

The interface must label model reasoning summaries and system events clearly; it must
not claim to reveal private chain-of-thought.

## Execution model

1. Append every input and system action to an immutable session event log.
2. Convert a request into a structured goal, constraints, and plan-step graph.
3. Give every plan branch, step, tool call, and result a stable identifier.
4. Track dependencies from constraints to steps and evidence.
5. On interruption, compute a structured state diff.
6. Traverse the dependency graph and invalidate only affected descendants.
7. Cancel active affected calls using cancellation tokens.
8. Preserve unaffected steps and evidence.
9. Increment the branch generation and replan missing work.
10. Reject every result whose call, branch, or dependency version is no longer active.
11. Build model context only from the active branch and valid evidence.

## Multi-task behavior

Each task owns an independent branch graph and evidence set. A user can pause research,
start a study plan, ask a general question, and resume research without mixing context.
The UI shows task cards and allows switching among them. Session memory is retained;
cross-session profiling remains out of scope.

## Demonstration scenario

1. User: "Research the best laptop under INR 70,000 for video editing."
2. Relay launches parallel product, benchmark, and price searches.
3. User interrupts: "Make it INR 55,000 and prioritize battery life."
4. Relay strikes out incompatible price searches and editing-only ranking work.
5. Relay preserves still-valid product specifications.
6. Relay launches replacement price and battery searches.
7. A late INR 70,000 result arrives and is visibly rejected.
8. User pauses the laptop task and starts an exam study plan.
9. User resumes the laptop task from its preserved checkpoint.
10. Relay returns a cited answer based only on the active branch.

## Build order

1. Persist full request text and immutable event records. **Done for request text;
   event history exists in memory.**
2. Add branch IDs, plan-step records, and dependency metadata. **Done for the
   foundational tool-step model.**
3. Add structured context-diff computation. **Done for tracked constraints.**
4. Add selective invalidation and preservation. **Foundational preservation is done;
   tool-result evidence dependency filtering is now done; multi-step graph traversal
   remains.**
5. Build the live plan-graph UI with strike-through transitions. **The chat-first,
   two-column interface is done; execution, context, and history are separated into
   tabs. Richer graph edges and replay animations remain.**
6. Add a real search connector with citations and parallel evidence gathering.
   **First working version done with three parallel MediaWiki searches; broader web
   and commercial/product data connectors remain.**
7. Add task cards for pause, switch, and resume. **Done for session-scoped tasks,
   isolated evidence, visible status, and one-click resume.**
8. Add measurable latency, cancellation, reuse, and stale-result metrics. **Done for
   the first live dashboard metrics and repeatable interruption demonstration.**
9. Add streaming transcript input and interrupt while the user is still speaking.
   **Browser input done: continuous microphone recognition sends observable interim
   transcript events and routes final speech through the normal interruption path.
   Real speculative retrieval from partial speech remains the next step.**
10. Create deterministic judge scenarios and failure-injection tests. **Core text,
    timing, retry, stale-result, and safety scenarios are automated; official audio
    and visual coverage remains.**

## Recommended winning addition: Interruption Replay Lab

Do not make decorative 3D the core feature. The scoring guide primarily rewards task
completion, interruption recovery, latency, and protocol safety. The highest-value
visual differentiator is a replayable execution graph driven by real trace data:

- scrub through the unified event timeline;
- animate the old branch turning red when it is cancelled;
- show valid evidence flowing into the replacement branch in green;
- display cancellation latency and acknowledgement latency at the exact events;
- replay late tool results being rejected;
- export the trace as the evidence judges can inspect.

A subtle 2.5D depth treatment can make this graph attractive, but a WebGL 3D scene
should wait until streaming audio, frame grounding, and evaluator scenarios pass.

The semantic Interruption Impact Engine foundation is now implemented. It combines
exact dependency matches, concept aliases, changed-value overlap, confidence scores,
and human-readable reasons. Full validation is specified in `VALIDATION_PLAN.md`.

## Success metrics

- Time to acknowledgement after interruption.
- Time to cancellation signal.
- Percentage of valid work preserved.
- Percentage of invalid work correctly rejected.
- Cross-task context contamination rate.
- Final-answer citation coverage.
- Recovery success under delayed and out-of-order tool results.

## Scope discipline

The winning claim is not "Relay can answer everything." The claim is: "Relay can
change direction during complex, concurrent work without losing valid progress or
allowing obsolete work to corrupt the answer—and it proves this live."
