---
name: using-game-superpowers
description: Entrypoint routing skill for the Game Superpowers system. Assesses project state and dispatches to the right specialized gsp-* skill across the full game dev lifecycle — concept, design, build, audit, production.
origin: mike007jd/game-superpowers
---

# /using-game-superpowers — Game Dev Superpowers Router

Entrypoint and routing hub for the Game Superpowers skill ecosystem. Assesses project state, determines the right phase, and dispatches to specialized `gsp-*` skills.

## Trigger

- Starting a new game project
- "Where should I start with this game idea?"
- Hitting a wall and unsure which discipline to apply next
- Assessing a game's production readiness
- Wanting a systematic audit of game quality

## Lifecycle Phases & Skill Dispatch

```
┌──────────────────────────────────────────────────────────┐
│  1. CONCEPT        → gsp-concept-brainstorm              │
│                    → gsp-requirements-brainstorm          │
│                    → gsp-scope-profile                    │
│                    → gsp-scope-guard                      │
├──────────────────────────────────────────────────────────┤
│  2. DESIGN         → gsp-mechanics-systems-design        │
│                    → gsp-feedback-design                 │
│                    → gsp-ux-flow-designer                 │
│                    → gsp-procedural-art-direction         │
│                    → gsp-hud-feedback-polish              │
├──────────────────────────────────────────────────────────┤
│  3. BUILD          → gsp-first-playable                  │
│                    → gsp-polished-prototype              │
│                    → gsp-implementation-plan             │
│                    → gsp-super-build                     │
│                    → gsp-build-strategy                  │
│                    → gsp-build-review                    │
│                    → gsp-subagent-build-loop             │
│                    → gsp-loop-bootstrap                  │
├──────────────────────────────────────────────────────────┤
│  4. AUDIT          → gsp-project-state-assessment        │
│                    → gsp-project-audit                   │
│                    → gsp-feel-audit                      │
│                    → gsp-feedback-audit                  │
│                    → gsp-ux-flow-audit                   │
│                    → gsp-mechanics-systems-audit         │
│                    → gsp-playability-verifier            │
│                    → gsp-screenshot-critic               │
│                    → gsp-scope-completeness-audit         │
│                    → gsp-hud-readability-audit           │
│                    → gsp-live-risk-audit                 │
│                    → gsp-audio-feedback-audit            │
│                    → gsp-architecture-maintainability-audit│
│                    → gsp-audit-scorecard                 │
│                    → gsp-repair-roadmap                  │
├──────────────────────────────────────────────────────────┤
│  5. PRODUCTION     → gsp-production-code                 │
│                    → gsp-production-feature              │
│                    → gsp-production-readiness-audit      │
│                    → gsp-live-patch                      │
│                    → gsp-spec-driven-planning            │
├──────────────────────────────────────────────────────────┤
│  SPECIALIZED       → gsp-web-2d-specialist               │
│                    → gsp-web-3d-specialist               │
│                    → gsp-compare-backends                │
│                    → gsp-backend-selector                │
│                    → gsp-douyin-h5                       │
│                    → gsp-orchestrator                    │
│                    → gsp-rolling-supervisor              │
└──────────────────────────────────────────────────────────┘
```

## Phase Assessment — Quick Diagnostic

Ask these questions in order to determine which phase to enter:

| # | Question | If NO → Phase | If YES → |
|---|----------|---------------|----------|
| 1 | Is there a clear one-sentence hook? | Phase 1: Concept | Go to 2 |
| 2 | Are core mechanics documented? | Phase 2: Design | Go to 3 |
| 3 | Is there a playable build? | Phase 3: Build | Go to 4 |
| 4 | Has it been audited for feel/UX/balance? | Phase 4: Audit | Go to 5 |
| 5 | Is it production-ready (live ops, monitoring)? | Phase 5: Production | Ship it |

## How to Use

### New Project — Start from Concept
```
/using-game-superpowers
→ State: "I have a rough idea but nothing concrete"
→ Route: Phase 1 → gsp-concept-brainstorm
  └→ Then: gsp-scope-profile → gsp-first-playable
```

### Existing Project — Assess and Improve
```
/using-game-superpowers
→ State: "I have a playable prototype"
→ Route: Phase 4 → gsp-project-audit
  └→ Identify weakest area → dispatch to specific audit skill
  └→ gsp-repair-roadmap → actionable fix list
```

### Mid-Development — Unblock
```
/using-game-superpowers
→ State: "The game doesn't feel fun enough"
→ Route: gsp-feel-audit → gsp-feedback-design
  └→ Apply juice layer → gsp-playability-verifier
```

### Near-Complete — Production Check
```
/using-game-superpowers
→ State: "Ready to ship — I think"
→ Route: Phase 5 → gsp-production-readiness-audit
  └→ gsp-live-risk-audit → gsp-live-patch
```

## Skill Dependency Graph

### Design-Test-Refine Loop
```
gsp-mechanics-systems-design
        ↓
gsp-first-playable / gsp-polished-prototype
        ↓
gsp-feel-audit ← gsp-feedback-audit ← gsp-playability-verifier
        ↓                    ↓
gsp-feedback-design → gsp-hud-feedback-polish
        ↓
gsp-ux-flow-audit ← gsp-ux-flow-designer
```

### Audit Pipeline
```
gsp-project-state-assessment
        ↓
gsp-project-audit (broad)
        ↓
    ┌───┼───┬─────────┬──────────────┐
    ↓   ↓   ↓         ↓              ↓
  feel UX  mechanics scope-complete  HUD
    ↓   ↓   ↓         ↓              ↓
    └───┴───┴─────────┴──────────────┘
                    ↓
        gsp-audit-scorecard
                    ↓
        gsp-repair-roadmap
```

### Production Pipeline
```
gsp-implementation-plan
        ↓
gsp-super-build ──→ gsp-build-review
        ↓
gsp-production-readiness-audit
        ↓
gsp-production-code / gsp-production-feature
        ↓
gsp-live-risk-audit → gsp-live-patch
```

## Platform Detection

| Platform | Specialized Skill |
|----------|-------------------|
| Web (Canvas/2D) | `gsp-web-2d-specialist` |
| Web (WebGL/3D) | `gsp-web-3d-specialist` |
| Mobile (iOS/Android) | `gsp-production-readiness-audit` (mobile checklists) |
| Douyin/Mini-app H5 | `gsp-douyin-h5` |
| Desktop (Standalone) | Default pipeline |

## Audit Scorecard

Every audit produces a scorecard across these dimensions:

| Dimension | What It Measures | Target |
|-----------|-----------------|--------|
| **Feel** | Input response, juice, impact | ≥ 8/10 |
| **Feedback** | Audio, visual, haptic acknowledgment | ≥ 7/10 |
| **UX Flow** | Onboarding, menus, navigation clarity | ≥ 8/10 |
| **Mechanics** | Balance, depth, exploit-free | ≥ 7/10 |
| **Readability** | Threat telegraphing, UI clarity | ≥ 7/10 |
| **Scope** | Completeness vs. planned features | ≥ 90% |
| **Architecture** | Maintainability, coupling, testability | ≥ 7/10 |
| **Production** | Error handling, monitoring, live ops | ≥ 8/10 |

## Orcherstrator Mode

For complex projects, use `gsp-orchestrator` + `gsp-rolling-supervisor`:

```
gsp-orchestrator
  ├→ gsp-project-state-assessment (baseline)
  ├→ [parallel audit skills] (comprehensive health check)
  ├→ gsp-audit-scorecard (aggregate)
  ├→ gsp-repair-roadmap (prioritized fix list)
  ├→ gsp-implementation-plan (phased execution)
  └→ gsp-rolling-supervisor (continuous oversight)
```

## Anti-Patterns

- **Skipping audit before shipping** — always run `gsp-production-readiness-audit`.
- **Designing without scope guard** — feature creep kills timelines.
- **Building without first-playable milestone** — you can't feel a GDD.
- **Ignoring platform-specific audit** — 3D web perf is different from mobile perf.
- **Orchestrating too early** — for small projects, direct dispatch is faster.
