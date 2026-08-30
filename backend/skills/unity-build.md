---
name: unity-build
description: Unity build and release pipeline — build configuration, platforms, Addressables, and post-build verification via unity-mcp.
---

# /unity-build — Build & Release

Configure and run Unity builds (Windows/macOS/Linux/Android/iOS/WebGL) with repeatable settings.

## Trigger

- Building the project, configuring build targets, switching platforms
- Addressables / asset bundle preparation, build scripts (editor automation)

## Rules

- Never change project settings without confirming scope; record every changed setting.
- Generated build scripts go under `Assets/Generated/Editor/`.
- Prefer build automation through unity-mcp editor invocation over manual steps.

## Workflow

1. Confirm target platform and build output path.
2. Inspect Build Settings and player settings; apply changes via unity-mcp.
3. Trigger build; monitor console output.
4. Verify build artifacts exist and report size/time/errors.
