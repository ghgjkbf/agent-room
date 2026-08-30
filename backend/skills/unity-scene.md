---
name: unity-scene
description: Unity scene and GameObject operations — creating scenes, objects, prefabs, components, and hierarchy management via unity-mcp.
---

# /unity-scene — Scene & Object Operations

Manage Unity scenes and object hierarchies. All operations target the connected editor via unity-mcp (`http://127.0.0.1:8080`).

## Trigger

- Creating or modifying scenes, GameObjects, prefabs, components
- Object hierarchy, parenting, transforms, layers, tags
- Prefab instantiation and variant creation

## Rules

- Generated objects/assets go to `Assets/Generated` unless the user specifies otherwise.
- Prefer editor operations via unity-mcp over direct `.unity`/`.prefab` YAML edits. If YAML editing is necessary, validate against the serialized version before and after.
- Never use `GameObject.Find` at runtime; wire references through the inspector, `[SerializeField]`, or DI.

## Workflow

1. Connect unity-mcp; if unreachable, ask the user to start the backend manually.
2. Inspect current scene/project state (hierarchy, selection, loaded scenes).
3. Create/modify objects or prefabs; save assets under `Assets/Generated`.
4. Verify changes and report.

## Useful Commands

- Scene load/save, object create/rename/delete, transform set, component add/remove
- Prefab save, instantiate, variant creation
- Tag/layer assignment, parent-child re-parenting
