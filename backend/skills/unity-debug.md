---
name: unity-debug
description: Unity debugging and diagnostics — console logs, play mode, performance profiling, and common runtime error fixes.
---

# /unity-debug — Debug & Diagnostics

Diagnose Unity runtime and editor issues: console errors, missing references, performance problems, null references.

## Trigger

- Console errors, exceptions, missing scripts/components
- Performance profiling, GC spikes, memory analysis
- Play mode behavior and state inspection

## Rules

- Reproduce first, fix second — confirm the error path before changing code.
- Runtime fixes respect the `unity-development` standards (no `Find` hacks, no per-frame allocation).
- Generated debug/utility scripts go to `Assets/Generated`.

## Workflow

1. Pull console log and stack trace via unity-mcp; identify root cause.
2. Inspect relevant scene/object state; reproduce if needed.
3. Apply minimal fix; verify via console and play mode where possible.
4. Report cause, fix, and verification result.
