# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Project

**Backend (must be started first):**
```bash
cd backend
uv run uvicorn main:app --reload
```
Server runs on `http://localhost:8000`. Check `GET /health` to confirm it's up.

**Generate notes for pending captures:**
```bash
# From project root
python sync_notes.py
```

**Chrome Extension (no build step):**
1. Open `chrome://extensions/`, enable "Developer mode"
2. Click "Load unpacked" → select the `extension/` folder

**Environment — `backend/.env` must contain:**
```
NOTION_CLIENT_ID=...
NOTION_CLIENT_SECRET=...
```

## Architecture

The project is a three-stage pipeline: **Capture → Notes → Notion**.

```
extension/              Chrome extension (Manifest V3, no bundler)
  manifest.json
  background.js         Service worker: relays captures to /save, handles Notion OAuth
  content.js            Injected into pages: hover highlight, click capture, toast feedback
  popup.js / popup.html 3-state UI: disconnected → target picker → configured

backend/
  main.py               FastAPI: all HTTP endpoints (capture, Notion OAuth proxy, SSE streaming)
  notion_sync.py        Markdown→Notion blocks converter + Notion page creator
  notion_config.json    Runtime config: token, target_id, target_type (gitignored)
  .env                  NOTION_CLIENT_ID + NOTION_CLIENT_SECRET (gitignored)
  saved/                Raw .txt captures from the extension (gitignored)

notes/                  Generated .md notes (gitignored)
notes_db.py             SQLite tracker (notes_tracker.db) for capture→note lifecycle
sync_notes.py           Orchestrator: finds pending captures, calls /make-notes per file
hooks/notion_sync.py    PostToolUse hook: fires on Write, syncs .md files to Notion

.claude/
  commands/make-notes.md  Slash command: reads a .txt capture, writes a structured .md note
  settings.local.json     Registers the PostToolUse hook
```

## Full Pipeline

**Stage 1 — Capture**
User clicks "Pick Element" in the popup → `content.js` activates picker → on click, sends `ELEMENT_CAPTURED` message → `background.js` POSTs to `/save` → file written to `backend/saved/<page-title>.txt`.

**Stage 2 — Note generation**
`sync_notes.py` calls `notes_db.py` to find captures without notes, then for each calls `claude -p "/make-notes <stem> <saved_dir> <notes_dir>" --output-format json --allowedTools Read,Write`. The slash command reads the `.txt`, generates structured markdown, and writes `notes/<stem>.md`. Token usage is tracked in `notes_tracker.db`.

The popup's "Sync Notes with Notion" button calls `POST /make-notes`, which runs `sync_notes.py` as a subprocess and streams its stdout back to the popup as Server-Sent Events.

**Stage 3 — Notion sync**
The PostToolUse hook (`hooks/notion_sync.py`) fires automatically after every Write tool call. It checks if the written file is a `.md` inside the `notes/` directory, then POSTs to `/notion/sync`. The backend reads the file, converts it to Notion blocks via `notion_sync.markdown_to_blocks()`, and creates a page in the configured database or page via the Notion API.

Manual sync: `POST /notion/sync` with `{"file_path": "<absolute path to .md>"}`.

## Key Implementation Details

**Notion OAuth** — Client secret stays on the backend. `background.js` uses `chrome.identity.launchWebAuthFlow` to get an auth code, then posts the code to `/notion/token`, which exchanges it server-side with Basic Auth. Token and target are stored in `chrome.storage.sync` (extension) and `backend/notion_config.json` (backend).

**All Notion API calls are proxied through the backend** — Notion blocks `chrome-extension://` origins directly.

**Markdown→Notion converter** (`notion_sync.py`) — Handles: headings (h1–h3), fenced code blocks (with language mapping e.g. `jsx`→`javascript`), blockquotes (merges consecutive `>` lines), tables (`table.children` holds rows — not top-level), bulleted/numbered lists with one level of nesting (2-space indent), to-do checkboxes (`- [ ]`/`- [x]`), images, dividers. Notion limits 100 blocks per request; `create_notion_page` chunks and appends.

**SSE streaming** (`POST /make-notes`) — Uses `subprocess.Popen` in a daemon thread feeding a `queue.Queue`, which an async generator drains via `loop.run_in_executor`. This avoids Windows asyncio subprocess compatibility issues. The popup reads the stream with `fetch` + `ReadableStream`.

**`notes_db.py` migrations** — `init_db()` uses `ALTER TABLE … ADD COLUMN` inside try/except to handle databases created before token columns were added.

**Toast auto-close** — `content.js` sets `opacity: 0` (not `!important`, so inline style wins), then `display: none` after the 0.4s CSS transition.
