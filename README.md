# WebNotes

A Chrome extension that captures any webpage element, generates structured AI study notes, and syncs them to Notion.

## How it works

```
Pick Element → saved as .txt → AI generates .md note → synced to Notion page
```

1. **Capture** — Click any element on a webpage to save its content locally
2. **Generate** — AI (Claude) converts raw captures into structured revision-ready notes
3. **Sync** — Notes are pushed to your chosen Notion database or page as formatted pages

## Setup

### 1. Notion Integration

- Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → New integration
- Set type to **Public**, add redirect URI: `https://<YOUR_EXTENSION_ID>.chromiumapp.org/`
- Copy your **OAuth Client ID** into `extension/background.js`
- Copy your **OAuth Client Secret** into `backend/.env`

### 2. Backend

```bash
cd backend
cp .env.example .env   # fill in your Notion credentials
uv sync
uv run uvicorn main:app --reload
```

Server runs on `http://localhost:8000`.

### 3. Chrome Extension

1. Open `chrome://extensions/` → enable **Developer mode**
2. Click **Load unpacked** → select the `extension/` folder
3. Find your extension ID and add it to your Notion integration's redirect URI
4. Click **Connect to Notion** in the popup

## Generating Notes

Click **Sync Notes with Notion** in the extension popup. A live log streams progress as each capture is processed and pushed to Notion.

Alternatively, run from the project root:

```bash
python sync_notes.py
```

## Project Structure

```
extension/        Chrome extension (Manifest V3)
backend/          FastAPI server
hooks/            Claude Code PostToolUse hook (auto-syncs notes on write)
notes_db.py       SQLite tracker for capture → note lifecycle
sync_notes.py     Orchestrator: runs AI note generation for pending captures
notes/            Generated .md notes (local only, gitignored)
```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- [Claude Code](https://claude.ai/code) (for AI note generation via `/make-notes`)
- Chrome or Chromium browser
