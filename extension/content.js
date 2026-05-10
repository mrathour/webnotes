(() => {
  if (window.__ecInitialized) return;
  window.__ecInitialized = true;
  window.__ecActive = false;

  let hoveredEl = null;

  function injectStyle() {
    if (document.getElementById('__ec_style__')) return;
    const s = document.createElement('style');
    s.id = '__ec_style__';
    s.textContent = `
      .__ec_hl__ {
        outline: 2px solid #4f46e5 !important;
        outline-offset: 2px !important;
        background-color: rgba(79, 70, 229, 0.08) !important;
        cursor: crosshair !important;
      }
      #__ec_toast__ {
        position: fixed !important;
        bottom: 24px !important;
        right: 24px !important;
        padding: 12px 18px !important;
        border-radius: 8px !important;
        font-size: 14px !important;
        font-family: system-ui, sans-serif !important;
        z-index: 2147483647 !important;
        max-width: 340px !important;
        word-break: break-all !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25) !important;
        color: white !important;
        transition: opacity 0.4s ease !important;
        pointer-events: none !important;
      }
    `;
    document.head.appendChild(s);
  }

  function showToast(msg, type) {
    injectStyle();
    let toast = document.getElementById('__ec_toast__');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = '__ec_toast__';
      document.body.appendChild(toast);
    }
    const colors = { success: '#065f46', error: '#991b1b', info: '#3730a3', warning: '#92400e' };
    toast.style.background = colors[type] || colors.info;
    toast.style.display = 'block';
    toast.style.opacity = '1';
    toast.textContent = msg;
    clearTimeout(toast._timer);
    clearTimeout(toast._hideTimer);
    toast._timer = setTimeout(() => {
      toast.style.opacity = '0';
      toast._hideTimer = setTimeout(() => { toast.style.display = 'none'; }, 400);
    }, 3000);
  }

  function onMouseOver(e) {
    if (hoveredEl) hoveredEl.classList.remove('__ec_hl__');
    hoveredEl = e.target;
    hoveredEl.classList.add('__ec_hl__');
    e.stopPropagation();
  }

  function onMouseOut() {
    if (hoveredEl) hoveredEl.classList.remove('__ec_hl__');
  }

  function onClick(e) {
    e.preventDefault();
    e.stopPropagation();

    const el = e.target;
    el.classList.remove('__ec_hl__');
    deactivate();
    showToast('Saving...', 'info');

    chrome.runtime.sendMessage({
      type: 'ELEMENT_CAPTURED',
      data: {
        text: el.innerText || el.textContent || '',
        html: el.outerHTML,
        tag: el.tagName,
        url: window.location.href,
        title: document.title,
      }
    });
  }

  function onKeyDown(e) {
    if (e.key === 'Escape') {
      deactivate();
      showToast('Cancelled', 'info');
    }
  }

  function activate() {
    if (window.__ecActive) return;
    window.__ecActive = true;
    injectStyle();
    document.addEventListener('mouseover', onMouseOver, true);
    document.addEventListener('mouseout', onMouseOut, true);
    document.addEventListener('click', onClick, true);
    document.addEventListener('keydown', onKeyDown, true);
    document.body.style.cursor = 'crosshair';
    showToast('Hover over an element and click to capture — ESC to cancel', 'info');
  }

  function deactivate() {
    window.__ecActive = false;
    if (hoveredEl) {
      hoveredEl.classList.remove('__ec_hl__');
      hoveredEl = null;
    }
    document.removeEventListener('mouseover', onMouseOver, true);
    document.removeEventListener('mouseout', onMouseOut, true);
    document.removeEventListener('click', onClick, true);
    document.removeEventListener('keydown', onKeyDown, true);
    document.body.style.cursor = '';
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'ACTIVATE_PICKER') activate();
    else if (msg.type === 'SAVE_SUCCESS') {
      if (msg.overwritten)
        showToast(`Overwritten: ${msg.path}`, 'warning');
      else
        showToast(`Saved to: ${msg.path}`, 'success');
    }
    else if (msg.type === 'SAVE_ERROR') showToast(`Error: ${msg.error}`, 'error');
  });
})();
