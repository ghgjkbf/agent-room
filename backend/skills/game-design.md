---
name: game-design
description: Game design methodology — core loops, player psychology, difficulty curves, game feel, level design, and prototyping. Use when discussing mechanics, progression, balance, or player experience.
---

# /game-design — Game Design Craft

Systematic game design methodology covering the full lifecycle: concept → prototype → polish → ship. Applies to any genre, platform, or engine.

## Trigger

- Designing or tuning game mechanics, systems, or rules
- Creating or iterating on levels, encounters, or content
- Discussing player experience, difficulty, progression, or retention
- Adding "game feel" — juice, feedback, camera, audio
- Prototyping a new idea or evaluating an existing design
- Balancing numbers — economy, damage curves, spawn rates

## Core Loop Design

```
┌──────────────────────────────────────┐
│  CORE LOOP — the 30-second heartbeat │
│                                      │
│   ACTION  →  REWARD  →  UPGRADE     │
│     ↑                      │         │
│     └──────────────────────┘         │
│         (escalating challenge)        │
└──────────────────────────────────────┘
```

### Loop Validation Checklist
- **Clarity**: Does the player understand the goal within 5 seconds?
- **Agency**: Do player decisions meaningfully change outcomes?
- **Feedback**: Is every action acknowledged? (visual + audio + haptic)
- **Escalation**: Does difficulty rise organically, not as a brick wall?
- **Variety**: Does the loop evolve over a session, or stay identical?

## Player Motivation (Self-Determination Theory)

| Drive | Design Tool | Example |
|-------|-------------|---------|
| **Autonomy** | Meaningful choices | Multiple valid builds, branching paths |
| **Competence** | Clear feedback + growth | Combo counters, rank badges, speed lines |
| **Relatedness** | Social or narrative connection | Leaderboards, companions, worldbuilding |

### Octalysis Quick Reference
1. **Meaning** — narrative stakes, world-saving
2. **Accomplishment** — trophies, progress bars, boss defeats
3. **Empowerment** — creative tools, combo systems
4. **Ownership** — customization, base-building, collections
5. **Social** — co-op, guilds, leaderboards
6. **Scarcity** — limited-time events, rare loot
7. **Unpredictability** — procedural generation, random drops
8. **Avoidance** — loss aversion, streak saver, energy systems

## Difficulty & Progression

### Difficulty Curve Design
```
Difficulty
    │                                    ╭── Final Boss
    │                               ╭───╯
    │                          ╭────╯
    │                    ╭────╯
    │              ╭────╯      ← "valleys" for breathing room
    │        ╭────╯
    │  ╭────╯
    │─╯  ← tutorial
    └─────────────────────────────────→ Time / Progress
```

### Key Rules
- **Ramp, don't wall**: Each new mechanic gets a safe introduction before being tested.
- **Valleys after peaks**: After a boss or hard section, give the player a power fantasy moment.
- **No unfair deaths**: Player must feel "I could have avoided that" — never "the game cheated."
- **Silent assist**: Slightly magnetize landings, widen hit windows on easy mode, slow projectiles near the player. Never announce it.

### Progression Types
| Type | Player Feels | Best For |
|------|-------------|----------|
| Linear | Predictable, steady | Narrative games |
| Exponential | Rapid snowball | Idle, roguelike |
| Logarithmic | Early burst, then grind | MMO, live service |
| Step-function | Eureka moments | Metroidvania, puzzle |

## Game Feel (The "Juice" Layer)

### The 12 Principles of Game Feel
1. **Input response** — < 16ms from press to result (less than one frame at 60fps)
2. **Screen shake** — scaled to event magnitude, directional when possible
3. **Hit stop / freeze frame** — 2-6 frames on impact, enemy-specific
4. **Camera work** — lerp with overshoot, look-ahead, FOV kick on speed
5. **Sound design** — layered: transient (impact) + body (texture) + tail (ambient)
6. **Particles** — burst on impact, trail on movement, ambient for environment
7. **Animation squash & stretch** — preserve volume, exaggerate for impact
8. **Color flash** — white flash on hit, red on damage, gold on collect
9. **Controller rumble** — asymmetric L/R for direction, wave form for texture
10. **UI pop** — scale bounce, color pulse, number ticker (not instant set)
11. **Speed lines / FOV** — increase FOV slightly at high speed, add peripheral streaks
12. **After-images** — ghost copies trailing behind during special moves

### Juice Priority by Budget
```
FREE ──────────────────→ EXPENSIVE
color flash,             custom animation,
screen shake,            physics-based VFX,
UI tween,                dynamic music layers,
FOV shift,               controller haptics,
hit stop (1 line)        RTC smoke/fluid sim
```

## Level & Encounter Design

### Pacing Graph
```
Intensity
  10 │         ██ boss
   8 │    ██   ██
   6 │   ████ ████ combat
   4 │  ██ ████ ██
   2 │ ██       ██ exploration
   0 │█           █ rest
     └─────────────────→ Time
```

### Encounter Design Checklist
- **Purpose**: Is this teaching a mechanic, testing mastery, or providing spectacle?
- **Composition**: What's the threat mix? (ranged + melee + environmental)
- **Space**: Does the arena shape enable or constrain the intended playstyle?
- **Rhythm**: Attack → dodge window → counter → repeat?
- **Readability**: Can the player see threats before they're hit? (contrast, silhouette, telegraph)
- **Escalation within encounter**: Phase 1 → Phase 2 → desperate finale?

### Level Design: Breadcrumb Theory
1. **Light** — players move toward brightness
2. **Contrast** — interactable objects differ from background
3. **Motion** — moving elements draw the eye
4. **Negative space** — empty areas frame the path
5. **Collectibles as guides** — coins/gems trace the intended path
6. **Landmarks** — unique silhouettes for spatial orientation

## Balance & Tuning

### Spreadsheet-Driven Design
For any numeric system, build a tuning table:

```
| Parameter      | Base | Per Level | Curve    | Cap   |
|----------------|------|-----------|----------|-------|
| Player HP      | 100  | +15       | linear   | none  |
| Enemy damage   | 8    | ×1.12     | exp      | 200   |
| Score per gem  | 10   | static    | —        | —     |
| Speed          | 6    | +0.5      | linear   | 18    |
```

### Balance Heuristics
- **50% win rate is not the goal** — a 70% win rate with close calls feels better than 50% with blowouts.
- **Best-imagined vs worst-case**: Test every system at floor and ceiling values.
- **Dominant strategy**: If one weapon/character/route is always optimal, the design has a problem.
- **Time to kill (TTK)**: For action games, 3-8 seconds for basic enemies, 30-90s for bosses.

## Prototyping

### The 4-Question Prototype
Before writing code, answer:
1. **What is the single emotion** I want the player to feel?
2. **What is the minimum interaction** to create that feeling?
3. **How do I fake everything else?** (placeholders, scripted sequences, mock UI)
4. **Can I test this today?** If not, scope down.

### Greybox Standards
- Use primitive geometry only (cubes, spheres, capsules).
- Color-code: white = player interacts, red = danger, blue = collectible, green = goal.
- No textures, no lighting beyond ambient + single directional.
- Test with target input method (touch, gamepad, M+KB) from day one.

## Game Design Document (GDD) — Lean Format

A GDD should fit on one page until prototype validates the fun:

```
TITLE: [Game name]
HOOK:  [One sentence why someone cares]
GENRE: [Genre + closest reference game]
PLATFORM: [Web, mobile, PC, console]
AESTHETIC: [3 reference images/words]

CORE LOOP:
  [Action] → [Reward] → [Upgrade] → repeat

KEY MECHANICS (max 5):
  1. [Mechanic] — [Why it's fun]
  2. ...

WIN/LOSE: [Victory condition] / [Failure condition]

MONETIZATION (if applicable):
  [Ads, IAP, premium, none]
```

## Anti-Patterns

- **Kitchen sink design**: "Let's add a crafting system!" — No. Does the core loop need it?
- **Difficulty = HP sponge**: Making enemies tankier is not harder, it's longer.
- **Tutorial wall**: 20 pop-ups before the player presses a button. Let them play first.
- **Feedback desert**: Player does something cool and gets... silence. Juice it.
- **Copying without understanding**: Dark Souls' difficulty works because of fair telegraphing, not just high damage numbers.
- **Design by committee**: Every stakeholder adding their pet feature until the game has no identity.
