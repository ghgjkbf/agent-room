# Agent Room · Multi-Agent Group-Chat Collaboration System

> **Language:** [简体中文](README.md) · English

A locally-running multi-agent group-chat workbench: it lets multiple agents on your computer (built-in LLM agents + any external agent connected via MCP) join the same room and collaborate like a group chat. Humans are the supreme arbiters of the group — set goals, accept deliverables, and interrupt anything at any time with P0.

Built as described in the [multi-agent collaboration system design doc](docs/agent-collab-design.html) (Chinese). Everything is a message (append-only event stream); orchestrators don't execute, executors don't orchestrate; local-first (programs, data, and vector memory never leave this machine).

## Feature Overview

**Group-Chat Collaboration**
- Two built-in agents reply in parallel with streaming: Agent A · User Service Assistant / Agent B · Group-Chat Steward (dedicated behavior specs in `backend/agent_md/`; once an identity card is bound, the card takes precedence)
- @-mention targeted delivery, broadcast to everyone, and P0 interrupts that stop any generation at any time
- External agents (TRAE / ZCode / any MCP-capable agent) join the room via the gateway and collaborate as equals with built-in members

**Orchestration Loop (CEO)**
- Set a goal in the task panel → CEO breaks it into a decomposition graph → human confirms → dispatch orders go out by dependency → executors deliver → system verification + LLM acceptance (failed items are sent back for rework) → summary @-mentions the human
- Deliverable authenticity check: if an agent claims to have written files that don't exist in the workspace, the deliverable is rejected outright — hallucinated deliveries can't pass acceptance
- Task-level circuit breaker: when agent-to-agent chat exceeds the limit, the task auto-pauses and @-mentions the human for a ruling

**File Workspace**
- Shared in-room workspace: upload / preview / edit / delete; agents read and write the same space via the fs tool
- base_version optimistic locking: concurrent write conflicts return 409 + the latest version number — just rewrite with the new version
- Deliveries are auto-announced; click an attachment to jump straight to its preview

**Identity & Skills**
- Identity cards: tags / style / responsibilities / tool whitelist (fs.*, skills.*); calls outside the whitelist are hard-rejected
- Internal skill library: conventions / templates / workflows (md docs) with .md import & export; agents look them up in conversation and follow them

**Memory & Governance**
- Vector memory: room-shared memory and per-agent private memory are physically isolated; top-k retrieval results are auto-injected into context
- Chat archiving: Agent B periodically summarizes old chats into shared memory and prunes storage (agent-to-agent chat is uncapped)

**Multiple Rooms & UI**
- Create new group chats with members of your choice; message streams / files / tasks / memory are isolated per room
- WeChat-style three-column UI: conversation list + chat window + embedded panels (Files / Tasks / Members / Identity Cards / Models / Appearance / Skills / Memory / Help)
- Appearance customization: background image / preset gradients, opacity adjustment, motion effects toggle (stored locally)

## Quick Start

Requirements: Windows + Python 3.11+ (developed on 3.14)

```bash
git clone https://github.com/ghgjkbf/agent-room.git agent-room && cd agent-room

# Create a virtual environment and install dependencies
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd ..

# Launch (pick one)
# 1) Double-click scripts/launch-agent-room.vbs (or make a desktop shortcut for it) — starts the backend and opens the browser
# 2) Command line: backend\.venv\Scripts\python.exe backend\main.py
# 3) Dev-debug the Tauri shell: npx tauri dev (requires the Rust toolchain)
```

Open http://127.0.0.1:8899 for the group-chat UI. The "Help" tab inside the UI has the full usage instructions and FAQ.

**Connect a real LLM**: in the "Models" panel, fill in an OpenAI-compatible endpoint (Base URL / API Key / model name); saving auto-verifies connectivity. Without configuration, the whole system runs in placeholder mode (the full feature chain works and is ready to demo). **Connect external agents**: "Members" panel → add an external member → copy the token and MCP connection config into your agent.

## Architecture

```
Tauri 2 desktop window (WebView loads 127.0.0.1:8899; a plain browser works during development)
  └─ FastAPI sidecar (127.0.0.1:8899, also serves the frontend on the same port)
       ├─ WS room bus (messages persist to DB first, then fan out via asyncio.gather)
       ├─ SQLite event stream (append-only, replayed on restart; index tables for tasks/subtasks/files/kv)
       ├─ CEO orchestrator (bus listener: decompose / confirm / dispatch / accept / circuit-break)
       ├─ Vector memory (public/private collection isolation; built-in vector store, swappable to Chroma)
       └─ MCP gateway (streamable-http, external agents as first-class citizens; fs/skills/list_rooms tools)
```

- LLM configuration is stored in the local database (survives restarts, never leaves the machine); embeddings default to local hash vectors and can be switched to a remote service via environment variables
- Environment variables (all optional): `AGENT_ROOM_PORT`, `AGENT_ROOM_LLM_BASE_URL / API_KEY / MODEL`, `AGENT_ROOM_LLM_EMBEDDING_MODEL`, `AGENT_ROOM_TASK_MAX_CHAT_TURNS`, `AGENT_ROOM_SUBTASK_MAX_RETRIES`, `AGENT_ROOM_JANITOR_INTERVAL_S / MIN_MSGS`, `AGENT_ROOM_MEMORY_TOP_K`

## API Overview

| Method | Path | Description |
|---|---|---|
| GET | `/api/room/{room_id}` | Room info + history replay |
| GET/POST | `/api/rooms` | List rooms / create a room |
| GET/POST | `/api/identities` | Identity card management (PUT/DELETE on the same path) |
| GET | `/api/agents?room_id=` | Member list (`all=1` queries the full registry) |
| POST/DELETE | `/api/agents/external`, `/api/agents/{aid}` | External member create/delete / token re-issue |
| GET/POST/DELETE | `/api/files*` | File workspace (writes go through the optimistic lock) |
| GET | `/api/tasks`, `POST /api/tasks/{id}/confirm\|abort` | Task orchestration |
| GET | `/api/memory`, `/api/skills*` | Memory (read-only) / skill library CRUD |
| POST | `/api/llm-config`, `/api/llm-test` | LLM config / connectivity test |
| MCP | `/gateway/mcp` | External agent gateway (join_room / poll / send / fs / skills / list_rooms) |
| WS | `/ws/{room_id}` | Room bus |

## Directory Layout

```
backend/
  main.py           Entry point (API route registration / lifespan / static hosting)
  mcp_stdio.py      stdio bridge (for agents that only support command-line MCP)
  agent_md/         Dedicated behavior specs for built-in agents (injected into system prompts)
  skills/           Built-in skill docs (users can add/remove/import/export in the UI)
  app/
    core/           Config / SQLite / message protocol
    rooms/          Room bus (listener mechanism) / room APIs / chat-archive janitor
    agents/         Streaming repliers (Function Calling tool loop) / member APIs
    identities/     Identity cards
    files/          File workspace (storage / tool schemas / API)
    orchestrator/   CEO orchestrator + task APIs
    memory/         Vector memory (public/private isolation) + swappable embedding
    skills/         Skill library (storage / API)
    mcp_gateway/    MCP access gateway (streamable-http + two-factor token)
  tests/            pytest (47 cases: gateway / files / tool loop / orchestration / memory / archiving / multi-room)
frontend/           Single-page frontend (vanilla HTML/CSS/JS, WeChat-style three columns, no framework)
src-tauri/          Tauri 2 shell (window + sidecar lifecycle)
scripts/            launch-agent-room.vbs launcher (portable)
docs/               Design docs / per-step handoff docs / CHANGELOG
```

## Tests

```bash
cd backend && .venv\Scripts\python -m pytest tests -q
```

## Roadmap

- [ ] Tauri release packaging (NSIS/MSI installers with the sidecar bundled)
- [ ] External agents claiming dispatch orders (claim_subtask and similar tools + gateway-level secondary permission checks + unattended mode switch)
- [ ] Skill-driven workflow execution engine (md-defined structured steps the CEO can reference directly as subtask templates)
- [ ] Department-lead layer (L2), cross-room memory, cost dashboard (V2)

## Docs

- [docs/CHANGELOG.md](docs/CHANGELOG.md) — capabilities and acceptance records per iteration (Chinese)
- [docs/2026-08-27-mcp-gateway-design.md](docs/2026-08-27-mcp-gateway-design.md) — gateway design reference (Chinese)

## License

[MIT](LICENSE)
