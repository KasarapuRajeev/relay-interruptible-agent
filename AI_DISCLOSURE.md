# AI Disclosure

## Project use of AI

Relay is an interruptible-agent control layer. At runtime it can connect to an
external language model through a provider adapter. The current implementation
supports Google Gemini and OpenAI, with an offline deterministic adapter for
demonstration and testing without an API key.

The external model is used for language understanding, choosing one validated next
action, and writing a natural-language response. Relay—not the external model—owns
task state, branch history, interruption handling, cancellation, stale-result
rejection, evidence provenance, tool validation, retry rules, and session memory.

No foundation model was trained or fine-tuned for this project. Relay does not store
a cross-session user profile. API keys are entered locally at runtime, remain outside
the repository, and are excluded through `.gitignore`.

## AI assistance during development

OpenAI Codex was used as a development assistant for architecture discussion, code
implementation, debugging, test creation, documentation, and review. Google Gemini
was used as a live runtime provider while testing the provider-adapter path.

The team remains responsible for the submitted design and implementation. Generated
or suggested changes were reviewed in the project workspace and checked through the
automated test suite. The release candidate currently passes 82 automated tests,
including interruption races, cancellation, stale-result rejection, evidence
isolation, provider failure, HTTP boundaries, and secret redaction.

## External data services

- Open-Meteo supplies live geocoding and current-weather evidence.
- Wikipedia/MediaWiki supplies cited research evidence.
- The local calculator uses a restricted Python AST evaluator and does not execute
  arbitrary code.

External evidence is labelled with its source in Relay's provenance view. Relay does
not claim that a booking, purchase, or other real-world action occurred unless an
explicit state-changing integration reports a confirmed result.

## Human verification

Before submission, the team should review the source, presentation, recorded demo,
claims, citations, and this disclosure. Provider names and API usage must remain
consistent with the final configuration demonstrated to the judges.
