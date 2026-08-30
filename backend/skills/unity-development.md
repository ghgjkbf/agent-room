---
name: unity-development
description: Unity 6 C# development — coding standards, architecture patterns, performance, and editor tooling for Unity game projects.
---

# /unity-development — Unity C# Engineering

Professional Unity development workflow targeting **Unity 6 (C# 9)**. Enforces code quality, modern C# patterns, DI architecture, and performance awareness.

## Trigger

- Any `.cs` file in a Unity project (`Assets/`, `Packages/`)
- Writing or reviewing MonoBehaviour, ScriptableObject, Editor scripts
- Scene setup, prefab work, animation, shader discussions
- Build pipeline, Addressables, asset bundle questions
- Performance profiling, memory management, GC optimization

## Priority Hierarchy

| Tier | Focus | Examples |
|------|-------|----------|
| **1. Code Quality** | Correctness, safety, readability | Null checks, `[SerializeField]`, no magic strings |
| **2. Modern C#** | Language features, terseness | Expression-bodied members, pattern matching, `using` declarations |
| **3. Architecture** | DI, decoupling, testability | VContainer, SignalBus, interface segregation |
| **4. Performance** | GC-free hot paths, pooling | `NativeArray`, `ObjectPool<T>`, avoid `Update()` boxing |

## Coding Standards

### MonoBehaviour Pattern
```csharp
public sealed class PlayerController : MonoBehaviour
{
    // Serialized fields go to the top — private, with attribute
    [SerializeField] private float moveSpeed = 5f;
    [SerializeField] private Rigidbody rb;

    // Cached references
    private Transform _transform;

    private void Awake()
    {
        _transform = transform;
    }

    private void OnEnable()  => RegisterEvents();
    private void OnDisable() => UnregisterEvents();

    // Never magic strings — use nameof or constants
    private static readonly int MoveHash = Animator.StringToHash("Move");
}
```

### Key Rules
- **No `GameObject.Find`** / **No `FindObjectOfType`** in hot paths — wire through inspector or DI.
- **Prefer `TryGetComponent`** over `GetComponent` when missing is expected.
- **Use `[field: SerializeField]`** for auto-properties that need inspector exposure (C# 9).
- **Never `null`-propagate UnityEngine.Objects** — use implicit bool conversion: `if (gameObject)` not `gameObject?.`.
- **Coroutine allocation**: Cache `WaitForSeconds` / `WaitForEndOfFrame` — never `new` per call.
- **String concatenation** in `Update()` → use `StringBuilder` or `TextMeshPro.SetText()` overloads.
- **`CompareTag` over `tag ==`** — avoids allocation.

### DI & Architecture (VContainer / Zenject)
```
Project Root
├── LifetimeScope (entry point)
│   ├── Installer — binds services, factories, presenters
│   ├── UseCases — stateless logic, pure C# (no Mono)
│   └── Presenters — bridge between UseCase ↔ View (MonoBehaviour)
```
- Views (MonoBehaviours) should be **thin** — only display and input.
- Logic lives in **UseCases** (plain C# classes, injectable).
- Communication via **SignalBus / MessagePipe** — not direct GameObject references across contexts.

### Performance: GC-Free Hot Path Pattern
```csharp
// Cache these at class level
private readonly Collider[] _overlapBuffer = new Collider[32];
private static readonly int PropertyId = Shader.PropertyToID("_Property");

private void FixedUpdate()
{
    // Reuse buffers — zero allocation
    var count = Physics.OverlapSphereNonAlloc(
        _transform.position, radius, _overlapBuffer, layerMask);

    for (int i = 0; i < count; i++)
    {
        // Process _overlapBuffer[i]
    }
}
```

### Async — UniTask
```csharp
// Always pass CancellationToken, always .Forget() or await
private async UniTaskVoid LoadAssetAsync(CancellationToken ct)
{
    var handle = Addressables.LoadAssetAsync<GameObject>(key);
    await handle.ToUniTask(cancellationToken: ct);
    // Use handle.Result
}
```

## Editor Scripting

- Place under `Editor/` folder.
- Use `[MenuItem]`, `[CustomEditor]`, `[PropertyDrawer]` attributes.
- `SerializedObject.Update()` / `ApplyModifiedProperties()` in custom inspectors.
- Long editor operations use `EditorCoroutine` or `async UniTask`.

## Project Structure (Recommended)
```
Assets/
├── Scripts/
│   ├── Runtime/          # Gameplay code
│   │   ├── Core/         # DI installers, entry points
│   │   ├── Domain/       # UseCases, entities, value objects
│   │   ├── Presentation/ # Views, presenters, UI
│   │   └── Infrastructure/ # Addressables, save, network
│   └── Editor/           # Custom inspectors, tooling
├── Prefabs/
├── Scenes/
├── ScriptableObjects/
└── Settings/             # RenderPipelineAsset, Presets
```

## What to Check Before Writing Code

0. Does `UnityEngine` / `PackageManager` already have this? (e.g., `ObjectPool<T>` is built-in)
1. Can this be a pure C# class (not MonoBehaviour)? → Fewer lifecycle surprises.
2. Does this allocate per frame? → Profile with Deep Profile mode.
3. Can this be a ScriptableObject instead of a prefab variant? → Better data-driven design.
4. Is the domain logic Unity-independent? → Extract to a separate assembly for testability.

## Anti-Patterns

- **God MonoBehaviour** — 500+ lines in one component.
- **`Update()` for everything** — many things can be event-driven.
- **Direct scene references** — break prefab isolation.
- **`Resources.Load`** — use Addressables or direct references.
- **Coroutine as async replacement** — use UniTask for error handling and cancellation.
- **`[ExecuteAlways]` without cleanup** — always check `Application.IsPlaying`.
