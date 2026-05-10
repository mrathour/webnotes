// ─── Notion Setup ────────────────────────────────────────────────────────────
// Each developer needs their own Notion integration:
// 1. Go to https://www.notion.so/my-integrations → New integration
// 2. Set integration type to "Public" and add this redirect URI:
//      https://<YOUR_EXTENSION_ID>.chromiumapp.org/
//    (find your extension ID at chrome://extensions after loading unpacked)
// 3. Replace the CLIENT_ID below with your integration's OAuth Client ID
// 4. Add your Client Secret to backend/.env as NOTION_CLIENT_SECRET
const NOTION_CLIENT_ID = 'YOUR_NOTION_OAUTH_CLIENT_ID';

// ─── Element Capture ─────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'ELEMENT_CAPTURED') {
    const tabId = sender.tab.id;
    fetch('http://localhost:8000/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.data),
    })
      .then((res) => res.json())
      .then((result) => {
        chrome.tabs.sendMessage(tabId, {
          type: 'SAVE_SUCCESS',
          path: result.path,
          overwritten: result.overwritten,
        });
      })
      .catch(() => {
        chrome.tabs.sendMessage(tabId, {
          type: 'SAVE_ERROR',
          error: 'Server unreachable — is the Python server running?',
        });
      });
    return;
  }

  if (msg.type === 'NOTION_AUTH') {
    handleNotionAuth()
      .then(sendResponse)
      .catch((err) => sendResponse({ error: err.message }));
    return true; // keep channel open for async response
  }
});

// ─── Notion OAuth ─────────────────────────────────────────────────────────────
async function handleNotionAuth() {
  const redirectUri = `https://${chrome.runtime.id}.chromiumapp.org/`;
  const state = crypto.randomUUID();

  const authUrl = new URL('https://api.notion.com/v1/oauth/authorize');
  authUrl.searchParams.set('client_id', NOTION_CLIENT_ID);
  authUrl.searchParams.set('redirect_uri', redirectUri);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('owner', 'user');
  authUrl.searchParams.set('state', state);

  const redirected = await chrome.identity.launchWebAuthFlow({
    url: authUrl.toString(),
    interactive: true,
  });

  const params = new URL(redirected).searchParams;
  if (params.get('state') !== state) {
    throw new Error('State mismatch — possible CSRF attack');
  }

  const code = params.get('code');
  if (!code) throw new Error('No authorization code received from Notion');

  const res = await fetch('http://localhost:8000/notion/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Token exchange failed');
  }

  const { access_token, workspace_name, workspace_id } = await res.json();

  await chrome.storage.sync.set({
    notion_token: access_token,
    notion_workspace: workspace_name,
    notion_workspace_id: workspace_id,
  });

  return { workspace: workspace_name };
}
