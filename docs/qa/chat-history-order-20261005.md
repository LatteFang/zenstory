# Agent history event order regression

New assistant turns record `display_events` in the existing message metadata. Text/thinking chunks coalesce only within one uninterrupted segment; tool entries reference the final serialized tool call by index, so result updates do not duplicate or move a card. Agent selection, router, handoff and terminal controls retain stream order. Existing model-facing content/tool data and feedback remain unchanged; no schema migration is needed.

The frontend snapshots its synchronous (not throttled React-state) buffer on completion. Live and saved display sequences use one renderer; history metadata resolves each tool reference to its final state. Legacy or invalid metadata uses the previous renderer rather than inventing a past order. Old rows containing only concatenated text cannot be accurately reconstructed.

Coverage: regression-first component hydration/completion/order checks; synchronous-buffer, multi-tool/control and legacy parser checks; mocked SSE completion and reload at desktop1280 and phone390. All fixtures are local; no paid model calls. Backend service tests use the isolated test database and mocked workflow, including cancellation/error history persistence.

Reproduce browser checks via the normal E2E configuration: `pnpm exec playwright test e2e/chat-history-order-mocked.spec.ts --project=chromium`. No opt-in skip is required for these deterministic mocked endpoints.
