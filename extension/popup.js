// ─── Storage helpers ──────────────────────────────────────────────────────────
const store = (obj) => chrome.storage.sync.set(obj);
const retrieve = (...keys) => chrome.storage.sync.get(keys);
const remove = (...keys) => chrome.storage.sync.remove(keys);

// ─── Notion API (via backend proxy) ──────────────────────────────────────────
async function fetchTargets(token) {
  const res = await fetch('http://localhost:8000/notion/targets', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Failed to load targets — is the backend running?');
  const { targets } = await res.json();
  return targets; // [{ id, type: "page"|"database", name }]
}

async function saveNotionConfig(token, targetId, targetType, targetName) {
  await fetch('http://localhost:8000/notion/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, target_id: targetId, target_type: targetType, target_name: targetName }),
  });
}

// ─── UI helpers ───────────────────────────────────────────────────────────────
const el = (id) => document.getElementById(id);
const show = (id) => { el(id).hidden = false; };
const hide = (id) => { el(id).hidden = true; };
const setText = (id, val) => { el(id).textContent = val; };

function setError(id, msg) {
  const node = el(id);
  node.textContent = msg;
  node.hidden = !msg;
}

// ─── Render ───────────────────────────────────────────────────────────────────
async function render() {
  const {
    notion_token, notion_workspace,
    notion_target_id, notion_target_name, notion_target_type,
  } = await retrieve(
    'notion_token', 'notion_workspace',
    'notion_target_id', 'notion_target_name', 'notion_target_type',
  );

  ['s-disconnected', 's-picker', 's-configured'].forEach(hide);
  setError('authError', '');

  if (!notion_token) {
    show('s-disconnected');
    return;
  }

  if (!notion_target_id) {
    setText('workspaceName1', notion_workspace);
    show('s-picker');
    loadTargets(notion_token);
    return;
  }

  const badge = notion_target_type === 'database' ? '[DB]' : '[Page]';
  setText('workspaceName2', notion_workspace);
  setText('targetName', `${badge} ${notion_target_name}`);
  show('s-configured');
}

async function loadTargets(token) {
  const select = el('targetSelect');
  const saveBtn = el('saveTargetBtn');

  select.innerHTML = '<option value="">— loading... —</option>';
  select.disabled = true;
  saveBtn.disabled = true;
  setError('pickerError', '');

  try {
    const targets = await fetchTargets(token);

    if (targets.length === 0) {
      select.innerHTML = '<option value="">— no pages or databases found —</option>';
      return;
    }

    select.innerHTML = '<option value="">— select a page or database —</option>';
    targets.forEach(({ id, type, name }) => {
      const opt = document.createElement('option');
      opt.value = id;
      opt.dataset.type = type;
      opt.dataset.name = name;
      opt.textContent = `${type === 'database' ? '[DB]' : '[Page]'} ${name}`;
      select.appendChild(opt);
    });
    select.disabled = false;
  } catch (err) {
    setError('pickerError', err.message);
  }
}

// ─── Element picker ───────────────────────────────────────────────────────────
async function activatePicker() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'ACTIVATE_PICKER' });
  } catch {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
    await chrome.tabs.sendMessage(tab.id, { type: 'ACTIVATE_PICKER' });
  }
  window.close();
}

// ─── Bootstrap ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  render();

  // State 1 → Connect Notion
  el('connectBtn').addEventListener('click', async () => {
    const btn = el('connectBtn');
    btn.disabled = true;
    btn.textContent = 'Connecting...';
    setError('authError', '');

    const res = await chrome.runtime.sendMessage({ type: 'NOTION_AUTH' });
    if (res?.error) {
      setError('authError', res.error);
      btn.disabled = false;
      btn.textContent = 'Connect to Notion';
    } else {
      render();
    }
  });

  // State 2 → enable Save when a target is chosen
  el('targetSelect').addEventListener('change', () => {
    el('saveTargetBtn').disabled = !el('targetSelect').value;
  });

  // State 2 → Save target selection
  el('saveTargetBtn').addEventListener('click', async () => {
    const select = el('targetSelect');
    if (!select.value) return;

    const opt = select.options[select.selectedIndex];
    const targetId = select.value;
    const targetType = opt.dataset.type;
    const targetName = opt.dataset.name;

    const { notion_token } = await retrieve('notion_token');

    await store({ notion_target_id: targetId, notion_target_type: targetType, notion_target_name: targetName });
    await saveNotionConfig(notion_token, targetId, targetType, targetName).catch(() => {});

    render();
  });

  // State 3 → Change target
  el('changeTargetBtn').addEventListener('click', async () => {
    await remove('notion_target_id', 'notion_target_type', 'notion_target_name');
    render();
  });

  // Always → Sync notes with Notion
  el('makeNotesBtn').addEventListener('click', async () => {
    const btn = el('makeNotesBtn');
    const log = el('syncLog');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Processing...';
    log.innerHTML = '';
    log.className = 'sync-log visible';

    const appendLine = (text, cls = '') => {
      const div = document.createElement('div');
      if (cls) div.className = cls;
      div.textContent = text;
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
    };

    try {
      let res;
      try {
        res = await fetch('http://localhost:8000/make-notes', { method: 'POST' });
      } catch {
        appendLine('Backend is not running. Start the server first.', 'log-error');
        return;
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        appendLine(data.detail || `Server error (${res.status})`, 'log-error');
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const part of parts) {
          const line = part.startsWith('data: ') ? part.slice(6) : part.trim();
          if (!line) continue;
          if (line === '[DONE]') break;
          if (line.startsWith('[ERROR]')) {
            appendLine(line.slice(8).trim(), 'log-error');
          } else {
            appendLine(line);
          }
        }
      }

      // Mark last line green if no errors
      if (!log.querySelector('.log-error') && log.lastElementChild) {
        log.lastElementChild.className = 'log-success';
      }

    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Sync Notes with Notion';
    }
  });

  // Help
  el('helpBtn').addEventListener('click', () => {
    chrome.tabs.create({ url: chrome.runtime.getURL('help.html') });
  });

  // Always → Pick element
  el('pickBtn').addEventListener('click', activatePicker);
});
