"""
PostToolUse hook — fires after every Write tool call.
Triggers Notion sync when a .md file is written inside the notes/ directory.
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "backend" / "notion_config.json"
BACKEND_URL = "http://localhost:8000/notion/sync"


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name") != "Write":
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    path = Path(file_path)

    # Only act on .md files written inside a "notes" directory
    if path.suffix != ".md" or "notes" not in path.parts:
        sys.exit(0)

    # Skip if Notion isn't configured yet
    if not CONFIG_PATH.exists():
        sys.exit(0)

    payload = json.dumps({"file_path": str(path)}).encode()
    req = urllib.request.Request(
        BACKEND_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            result = json.loads(res.read())
            print(f"[Notion] Synced '{result.get('title')}' → {result.get('url')}", file=sys.stderr)
    except urllib.error.URLError:
        # Backend not running — skip silently
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
