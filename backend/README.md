# WebNotes — Backend

FastAPI server that powers the WebNotes Chrome extension.

## Setup

```bash
# Install dependencies
uv sync

# Copy and fill in credentials
cp .env.example .env

# Start the server
uv run uvicorn main:app --reload
```

Server runs on `http://localhost:8000`.

## Environment variables

| Variable | Description |
|---|---|
| `NOTION_CLIENT_ID` | OAuth Client ID from your Notion integration |
| `NOTION_CLIENT_SECRET` | OAuth Client Secret from your Notion integration |

Create your Notion integration at https://www.notion.so/my-integrations.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/save` | Save a captured element as a `.txt` file |
| POST | `/notion/token` | Exchange OAuth code for access token |
| GET | `/notion/targets` | List pages and databases the user can sync to |
| POST | `/notion/config` | Save the selected Notion target |
| POST | `/make-notes` | Run AI note generation (SSE stream) |
| POST | `/notion/sync` | Sync a single `.md` note to Notion |
