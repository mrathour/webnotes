"""
Markdown-to-Notion-blocks converter and Notion page creator.
"""
import json
import re
from pathlib import Path

import httpx

NOTION_VERSION = "2022-06-28"
CONFIG_PATH = Path(__file__).parent / "notion_config.json"


# ─── Config ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("notion_config.json not found — save a Notion target in the extension first")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict):
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


# ─── Inline (rich_text) parser ────────────────────────────────────────────────

def _rt(content: str, bold=False, italic=False, code=False) -> dict:
    return {
        "type": "text",
        "text": {"content": content},
        "annotations": {
            "bold": bold, "italic": italic, "code": code,
            "strikethrough": False, "underline": False, "color": "default",
        },
    }


def _link_rt(text: str, url: str) -> dict:
    return {
        "type": "text",
        "text": {"content": text, "link": {"url": url}},
        "annotations": {
            "bold": False, "italic": False, "code": False,
            "strikethrough": False, "underline": False, "color": "default",
        },
    }


_INLINE = re.compile(
    r'\*\*(.+?)\*\*'        # **bold**
    r'|\*(.+?)\*'            # *italic*
    r'|`(.+?)`'              # `code`
    r'|\[([^\]]+)\]\(([^)]+)\)'  # [text](url)
)


def parse_inline(text: str) -> list[dict]:
    result = []
    last = 0
    for m in _INLINE.finditer(text):
        if m.start() > last:
            result.append(_rt(text[last:m.start()]))
        if m.group(1) is not None:
            result.append(_rt(m.group(1), bold=True))
        elif m.group(2) is not None:
            result.append(_rt(m.group(2), italic=True))
        elif m.group(3) is not None:
            result.append(_rt(m.group(3), code=True))
        elif m.group(4) is not None:
            result.append(_link_rt(m.group(4), m.group(5)))
        last = m.end()
    if last < len(text):
        result.append(_rt(text[last:]))
    return result or [_rt(text)]


# ─── Block builders ───────────────────────────────────────────────────────────

_LANG_MAP = {
    "js": "javascript", "jsx": "javascript",
    "ts": "typescript", "tsx": "typescript",
    "py": "python",
    "sh": "shell", "bash": "shell",
    "zsh": "shell",
    "": "plain text",
}


def _heading(level: int, text: str) -> dict:
    t = f"heading_{level}"
    return {"type": t, t: {"rich_text": parse_inline(text), "color": "default"}}


def _para(text: str) -> dict:
    return {"type": "paragraph", "paragraph": {"rich_text": parse_inline(text), "color": "default"}}


def _bullet(text: str) -> dict:
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": parse_inline(text), "color": "default"}}


def _numbered(text: str) -> dict:
    return {"type": "numbered_list_item", "numbered_list_item": {"rich_text": parse_inline(text), "color": "default"}}


def _code(code: str, lang: str) -> dict:
    notion_lang = _LANG_MAP.get(lang.lower(), lang.lower() or "plain text")
    return {"type": "code", "code": {
        "rich_text": [_rt(code[:2000])],
        "language": notion_lang,
    }}


def _quote(text: str) -> dict:
    return {"type": "quote", "quote": {"rich_text": parse_inline(text), "color": "default"}}


def _todo(text: str, checked: bool = False) -> dict:
    return {"type": "to_do", "to_do": {
        "rich_text": parse_inline(text),
        "checked": checked,
        "color": "default",
    }}


def _image(url: str) -> dict:
    return {"type": "image", "image": {"type": "external", "external": {"url": url}}}


def _bullet_nested(text: str, children: list[dict]) -> dict:
    block = {"type": "bulleted_list_item", "bulleted_list_item": {
        "rich_text": parse_inline(text), "color": "default",
    }}
    if children:
        block["children"] = children
    return block


def _numbered_nested(text: str, children: list[dict]) -> dict:
    block = {"type": "numbered_list_item", "numbered_list_item": {
        "rich_text": parse_inline(text), "color": "default",
    }}
    if children:
        block["children"] = children
    return block


def _table(raw_lines: list[str]) -> dict:
    row_data: list[list[str]] = []
    for line in raw_lines:
        if re.fullmatch(r'\|[\s\-:|]+\|', line.strip()):   # skip separator |---|
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        row_data.append(cells)

    if not row_data:
        return _para("")

    table_width = max(len(row) for row in row_data)
    row_blocks = []
    for row in row_data:
        padded = row + [''] * (table_width - len(row))
        row_blocks.append({
            "type": "table_row",
            "table_row": {"cells": [parse_inline(cell) for cell in padded]},
        })

    return {
        "type": "table",
        "table": {
            "table_width": table_width,
            "has_column_header": True,
            "has_row_header": False,
            "children": row_blocks,
        },
    }


_DIVIDER = {"type": "divider", "divider": {}}

_IMAGE_MD = re.compile(r'^!\[([^\]]*)\]\(([^)]+)\)$')
_TODO_MD  = re.compile(r'^- \[([ xX])\] (.*)')
_BULLET   = re.compile(r'^[-*+] (.*)')
_NUMBERED = re.compile(r'^\d+\.\s+(.*)')
_INDENT   = re.compile(r'^  [-*+] (.*)')          # 2-space indent = sub-bullet


# ─── Markdown → blocks ────────────────────────────────────────────────────────

def markdown_to_blocks(md: str) -> list[dict]:
    blocks: list[dict] = []
    lines = md.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ────────────────────────────────────────────────
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(_code("\n".join(code_lines), lang))
            i += 1
            continue

        # ── Headings ─────────────────────────────────────────────────────────
        if line.startswith("### "):
            blocks.append(_heading(3, line[4:].strip()))

        elif line.startswith("## "):
            blocks.append(_heading(2, line[3:].strip()))

        elif line.startswith("# "):
            blocks.append(_heading(1, line[2:].strip()))

        # ── Divider ──────────────────────────────────────────────────────────
        elif re.fullmatch(r'[-*=]{3,}', line.strip()):
            blocks.append(_DIVIDER)

        # ── Blockquote — merge consecutive > lines into one quote block ──────
        elif line.startswith('>'):
            quote_lines = []
            while i < len(lines) and lines[i].startswith('>'):
                quote_lines.append(lines[i][2:] if lines[i].startswith('> ') else lines[i][1:])
                i += 1
            blocks.append(_quote('\n'.join(quote_lines)))
            continue

        # ── Table — collect all consecutive | lines ───────────────────────────
        elif line.startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].startswith('|'):
                table_lines.append(lines[i])
                i += 1
            blocks.append(_table(table_lines))
            continue

        # ── Image ────────────────────────────────────────────────────────────
        elif m := _IMAGE_MD.match(line):
            blocks.append(_image(m.group(2)))

        # ── To-do checkbox ───────────────────────────────────────────────────
        elif m := _TODO_MD.match(line):
            blocks.append(_todo(m.group(2).strip(), checked=m.group(1).lower() == 'x'))

        # ── Bulleted list (with optional one level of indented sub-bullets) ──
        elif m := _BULLET.match(line):
            text = m.group(1).strip()
            children = []
            while i + 1 < len(lines) and (sm := _INDENT.match(lines[i + 1])):
                children.append(_bullet(sm.group(1).strip()))
                i += 1
            blocks.append(_bullet_nested(text, children))

        # ── Numbered list ────────────────────────────────────────────────────
        elif m := _NUMBERED.match(line):
            blocks.append(_numbered(m.group(1).strip()))

        # ── Blank line ───────────────────────────────────────────────────────
        elif line.strip() == '':
            pass

        # ── Regular paragraph ────────────────────────────────────────────────
        else:
            blocks.append(_para(line))

        i += 1

    return blocks


# ─── Notion API ───────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def _get_title_prop_name(client: httpx.AsyncClient, token: str, database_id: str) -> str:
    """Return the name of the title-type property in a database."""
    res = await client.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=_headers(token),
    )
    if res.status_code != 200:
        return "title"
    for name, prop in res.json().get("properties", {}).items():
        if prop.get("type") == "title":
            return name
    return "title"


async def create_notion_page(
    token: str,
    target_id: str,
    target_type: str,
    title: str,
    blocks: list[dict],
) -> str:
    """Create a Notion page and return its URL."""
    # Notion allows max 100 children per request
    chunks = [blocks[i:i + 100] for i in range(0, max(len(blocks), 1), 100)]

    async with httpx.AsyncClient(timeout=30) as client:
        if target_type == "database":
            title_prop = await _get_title_prop_name(client, token, target_id)
            parent = {"database_id": target_id}
            properties = {title_prop: {"title": [{"text": {"content": title}}]}}
        else:
            parent = {"page_id": target_id}
            properties = {"title": {"title": [{"text": {"content": title}}]}}

        # Create page with first chunk of blocks
        res = await client.post(
            "https://api.notion.com/v1/pages",
            headers=_headers(token),
            json={"parent": parent, "properties": properties, "children": chunks[0]},
        )
        if res.status_code != 200:
            raise RuntimeError(f"Notion page creation failed ({res.status_code}): {res.text}")

        page = res.json()
        page_id = page["id"]

        # Append remaining chunks
        for chunk in chunks[1:]:
            await client.patch(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=_headers(token),
                json={"children": chunk},
            )

        return page.get("url", "")
