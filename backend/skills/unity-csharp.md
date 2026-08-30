---
name: unity-csharp
description: Unity C# script generation — MonoBehaviour patterns, ScriptableObjects, editor scripts, and code generation targets for Assets/Generated.
---

# /unity-csharp — C# Script Generation

Generate production-grade Unity C# scripts. Targets Unity 6 / C# 9. Follows the `unity-development` coding standards.

## Trigger

- Writing or reviewing MonoBehaviour, ScriptableObject, Editor, plain C# classes
- Component logic, gameplay systems, tooling scripts

## Rules

- New scripts default to `Assets/Generated` (namespace `Generated.*` when applicable).
- `[SerializeField]` private fields instead of public fields; cache references in `Awake`.
- No `GameObject.Find` / `FindObjectOfType` in hot paths — inspector or DI wiring.
- Prefer `TryGetComponent`; use implicit bool conversion for UnityEngine.Object null checks (`if (gameObject)`).
- Cache `WaitForSeconds` etc.; avoid per-frame allocation and string concatenation in `Update()`.
- Async via UniTask with `CancellationToken`; never fire-and-forget without `.Forget()`.

## Workflow

1. Confirm script intent and required components/data.
2. Write script to `Assets/Generated`, keeping it thin and focused.
3. If an editor is connected, attach/integrate via unity-mcp; otherwise hand off for manual wiring.
4. Verify compilation via unity-mcp console output when available.
