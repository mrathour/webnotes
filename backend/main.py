import asyncio
import base64
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

NOTION_CLIENT_ID = os.getenv('NOTION_CLIENT_ID', '')
NOTION_CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET', '')

app = FastAPI(title="Element Capture Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

SAVE_DIR = Path("saved")
SAVE_DIR.mkdir(exist_ok=True)

MD_SAVE_DIR = Path("md_captures")
MD_SAVE_DIR.mkdir(exist_ok=True)

INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')


def title_to_filename(title: str) -> str:
    clean = re.sub(r'\s*\|.*$', '', title).strip()
    clean = INVALID_CHARS.sub('_', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return (clean or "capture")[:100]


# ─── Element Capture ──────────────────────────────────────────────────────────

class ElementData(BaseModel):
    text: str
    html: str
    tag: str
    url: str
    title: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/save")
def save_element(data: ElementData):
    filename = SAVE_DIR / f"{title_to_filename(data.title)}.txt"
    overwritten = filename.exists()

    content = (
        f"URL:       {data.url}\n"
        f"Title:     {data.title}\n"
        f"Tag:       {data.tag}\n"
        f"Captured:  {datetime.now().isoformat()}\n"
        f"{'=' * 60}\n\n"
        f"{data.text.strip()}\n"
    )

    filename.write_text(content, encoding="utf-8")
    return {"status": "ok", "path": str(filename.resolve()), "overwritten": overwritten}


# ─── Notion OAuth ─────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    code: str
    redirect_uri: str


@app.post("/notion/token")
async def notion_token(req: TokenRequest):
    if not NOTION_CLIENT_ID or not NOTION_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Notion credentials not configured — set NOTION_CLIENT_ID and NOTION_CLIENT_SECRET in backend/.env",
        )

    credentials = base64.b64encode(
        f"{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.notion.com/v1/oauth/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "code": req.code,
                "redirect_uri": req.redirect_uri,
            },
        )

    if res.status_code != 200:
        body = res.json()
        raise HTTPException(
            status_code=res.status_code,
            detail=body.get("error_description") or body.get("error") or "Token exchange failed",
        )

    data = res.json()
    return {
        "access_token": data["access_token"],
        "workspace_name": data.get("workspace_name", ""),
        "workspace_id": data.get("workspace_id", ""),
    }


# ─── Notion Targets (pages + databases) ──────────────────────────────────────

@app.get("/notion/targets")
async def notion_targets(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": authorization,
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": 100,
            },
        )

    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail="Failed to fetch from Notion")

    targets = []
    for r in res.json().get("results", []):
        obj_type = r.get("object")
        if obj_type not in ("page", "database"):
            continue

        if obj_type == "database":
            name = "".join(t.get("plain_text", "") for t in r.get("title", []))
        else:
            # Pages: find the title-type property
            name = ""
            for prop in r.get("properties", {}).values():
                if prop.get("type") == "title":
                    name = "".join(t.get("plain_text", "") for t in prop.get("title", []))
                    break

        targets.append({"id": r["id"], "type": obj_type, "name": name or "Untitled"})

    return {"targets": targets}


# ─── Notion Config ────────────────────────────────────────────────────────────

class NotionConfig(BaseModel):
    token: str
    target_id: str
    target_type: str   # "page" | "database"
    target_name: str


@app.post("/notion/config")
def save_notion_config(config: NotionConfig):
    from notion_sync import save_config
    save_config(config.model_dump())
    return {"status": "ok"}


# ─── Notion Sync ──────────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
    file_path: str


@app.post("/make-notes")
async def make_notes():
    project_root = Path(__file__).parent.parent
    sync_script = project_root / "sync_notes.py"

    if not sync_script.exists():
        raise HTTPException(status_code=500, detail="sync_notes.py not found in project root")

    log_queue: queue.Queue = queue.Queue()

    def run():
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = subprocess.Popen(
            [sys.executable, str(sync_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(project_root),
            env=env,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            log_queue.put(("line", line.rstrip()))
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().strip()
            if err:
                log_queue.put(("error", err))
        log_queue.put(("done", None))

    threading.Thread(target=run, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_running_loop()
        while True:
            try:
                kind, value = await loop.run_in_executor(None, lambda: log_queue.get(timeout=600))
            except queue.Empty:
                yield "data: [ERROR] Timed out waiting for sync_notes.py\n\n"
                yield "data: [DONE]\n\n"
                break

            if kind == "line" and value:
                yield f"data: {value}\n\n"
            elif kind == "error":
                yield f"data: [ERROR] {value}\n\n"
            elif kind == "done":
                yield "data: [DONE]\n\n"
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _preprocess_html(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Replace Monaco editor blocks with plain <pre><code> so markdownify handles them correctly
    for block in soup.select("div.rc-CodeBlock"):
        lang = block.get("data-mode-id", "")
        lines = []
        for vl in block.select("div.view-line"):
            lines.append(vl.get_text().replace("\xa0", " ").rstrip())
        pre = soup.new_tag("pre")
        code = soup.new_tag("code")
        if lang:
            code["class"] = f"language-{lang}"
        code.string = "\n".join(lines)
        pre.append(code)
        block.replace_with(pre)

    # Strip Monaco notification banners ("Pressing Tab in the current editor...")
    for alert in soup.select("div[role='alert']"):
        alert.decompose()

    return str(soup)


@app.post("/save-md")
async def save_md(data: ElementData):
    from markdownify import markdownify as md_convert
    from notion_sync import load_config, markdown_to_blocks, create_notion_page

    cleaned_html = _preprocess_html(data.html)
    markdown = (
        f"URL: {data.url}\n\n"
        + md_convert(cleaned_html, heading_style="ATX", bullets="-").strip()
    )

    stem = title_to_filename(data.title)
    file_path = MD_SAVE_DIR / f"{stem}.md"
    file_path.write_text(markdown, encoding="utf-8")

    try:
        config = load_config()
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Notion not configured — connect it in the extension first")

    blocks = markdown_to_blocks(markdown)
    url = await create_notion_page(
        token=config["token"],
        target_id=config["target_id"],
        target_type=config["target_type"],
        title=stem,
        blocks=blocks,
    )
    return {"status": "ok", "url": url, "title": stem, "path": str(file_path.resolve())}


@app.post("/notion/sync")
async def notion_sync(req: SyncRequest):
    from notion_sync import load_config, markdown_to_blocks, create_notion_page

    path = Path(req.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")

    try:
        config = load_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    title = path.stem
    content = path.read_text(encoding="utf-8")
    blocks = markdown_to_blocks(content)

    url = await create_notion_page(
        token=config["token"],
        target_id=config["target_id"],
        target_type=config["target_type"],
        title=title,
        blocks=blocks,
    )
    return {"status": "ok", "url": url, "title": title}
