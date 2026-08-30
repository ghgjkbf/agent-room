---
name: unity-assets
description: Unity asset management — importing, organizing, referencing, Addressables groups, and cleanup of project assets.
---

# /unity-assets — Asset Management

Organize and maintain project assets: models, textures, audio, prefabs, ScriptableObjects, Addressables.

## Trigger

- Importing or organizing assets, fixing missing references
- Addressables group setup, asset bundle configuration, dependency checks

## Rules

- Generated assets go to `Assets/Generated` unless the user specifies otherwise.
- Prefer direct references or Addressables over `Resources.Load`.
- Keep folder structure aligned with the recommended layout (`Scripts/Runtime|Editor`, `Prefabs`, `Scenes`, `ScriptableObjects`, `Settings`).

## Workflow

1. Scan asset folder and report structure, sizes, and obvious issues.
2. Move/rename/organize per convention; update references through unity-mcp.
3. Configure Addressables groups if required.
4. Report final structure and any unresolved references.
