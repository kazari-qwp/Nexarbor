# Access, signal and module protocol implementation

## Scope agreed 2026-10-18

- Access is a hand: follow graph paths, constrained by channels/strength; independent requests start concurrently. An invoked component uses its own mount grant. Forwarding is allowed.
- Signal is a wave: core owns its lifetime after emission. Same breadth-first layer runs concurrently; next layer waits for completion. Receivers use their own authority.
- Components use one fixed async entry, execute(ctx, activation), and a fixed result envelope. Business data remains JSON inside the activation. Core binds identity and validates registration, request and result.
- Ordinary modules have local data and network access/signal APIs; raw host objects stay outside. The official network gateway is an explicitly granted exception. This is API isolation, not an operating system sandbox for hostile Python.
- External tools are separate from modules. Nodes store registered tool references; an Agent visit acquires them. Every execution rechecks current reachability. Initially expose the installed DeepSeek Harness official tool catalog in the workbench.
- No compatibility migration for existing applications or generated modules. Use a fresh development workspace and current blank template.

## Implementation and validation

1. Fixed component protocol and registration, local execution, concurrent access and callee authority.
2. Detached signal emission, receipt/wait/cancel and layer barriers.
3. Trusted external tool catalog, node offers, acquisition and execution validation; persisted offers.
4. Harness official tool provider and workbench catalog/assignment UI.
5. Maker template, contract validator, worker and documentation updated to the current protocol.
6. Tests: malformed registration; parallel access; forwarding; caller identity; detached waves and barriers; tool reference spoofing and revocation; serialization; real installed Harness tool discovery and one bounded harmless execution; frontend build and UI flow.

## Record

Baseline: 6699f9b. Implementation in progress. Existing application manifests remain unmigrated intentionally.

## Completion record

Implemented v3 fixed async ABI, caller path checks with callee mount authority, eager structured access tasks, core-owned detached waves, persisted node tool offers, trusted external-tool references with per-call reauthorization, and the official Harness tool provider. Updated the maker instructions/templates/validator and the workbench tool assignment UI. Old application components/configurations remain untouched and incompatible by design.

Desktop end-to-end evidence: build/protocol-e2e-1792296935330/verification.json. Ten installed official tools were discovered; official read executed successfully after a visit; a disconnected path rejected the retained declaration; v3 validation/publish/mount and restart restoration passed. Model calls: zero.

Final verification is recorded in the implementation response and docs/LOCAL_MODULES.md. This is API locality for trusted Python, not an OS sandbox.

Final checks: 69 targeted Python core tests, 11 network-editor tests, 1 desktop connection test, and the real desktop protocol flow passed. Latest desktop evidence: build/protocol-e2e-1792297480190/verification.json. Request payload copy-at-start was additionally verified. Frontend production build and git diff --check passed. Paid model/API calls: 0.
