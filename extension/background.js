// Browseye — background script
// Connects to local WebSocket server and executes browser commands

const WS_URL = 'ws://127.0.0.1:8765';
const RECONNECT_DELAY = 3000;

let ws = null;
let reconnectTimer = null;
let commandId = 0;
let pendingCommands = new Map();
let capturedRequests = [];
let monitoringNetwork = false;

// ---------------------------------------------------------------------------
// WebSocket connection management
// ---------------------------------------------------------------------------

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(WS_URL);
  } catch (e) {
    console.error('[FFC] WebSocket creation failed:', e.message);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log('[FFC] Connected to controller server');
    updateStatus('connected');
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    // Send handshake so the server knows we're the extension agent
    sendRaw({ type: 'agent_hello', agent: 'firefox-extension', version: '1.0.0' });
  };

  ws.onclose = (ev) => {
    console.log('[FFC] Disconnected (code=' + ev.code + '). Reconnecting in ' + (RECONNECT_DELAY/1000) + 's');
    updateStatus('disconnected');
    ws = null;
    scheduleReconnect();
  };

  ws.onerror = (err) => {
    console.error('[FFC] WebSocket error');
    // onclose will fire after this
  };

  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      handleCommand(data);
    } catch (e) {
      console.error('[FFC] Failed to parse message:', e.message);
    }
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_DELAY);
}

function sendRaw(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn('[FFC] Cannot send — not connected');
    return false;
  }
  try {
    ws.send(JSON.stringify(obj));
    return true;
  } catch (e) {
    console.error('[FFC] Send failed:', e.message);
    return false;
  }
}

function sendResponse(cmdId, success, data, error) {
  sendRaw({
    type: 'response',
    id: cmdId,
    success: success,
    data: data,
    error: error ? String(error) : null
  });
}

function updateStatus(status) {
  sendRaw({ type: 'status_update', status: status });
  browser.browserAction.setBadgeText({ text: status === 'connected' ? 'ON' : 'OFF' });
  browser.browserAction.setBadgeBackgroundColor({ color: status === 'connected' ? '#00aa00' : '#aa0000' });
}

// ---------------------------------------------------------------------------
// Command dispatcher
// ---------------------------------------------------------------------------

async function handleCommand(msg) {
  const cmdId = msg.id || 'anon-' + (commandId++);
  const cmd = msg.command;
  const params = msg.params || {};

  console.log('[FFC] Command:', cmd, params);

  try {
    switch (cmd) {

      // === System ===
      case 'ping':
        sendResponse(cmdId, true, { pong: true, ts: Date.now() });
        break;

      case 'get_info':
        sendResponse(cmdId, true, {
          extension: 'Browseye v1.0.0',
          browser: navigator.userAgent,
          platform: navigator.platform,
          ws_connected: !!(ws && ws.readyState === WebSocket.OPEN)
        });
        break;

      // === Tab Management ===
      case 'tab_list':
        const tabs = await browser.tabs.query({});
        sendResponse(cmdId, true, tabs.map(t => ({
          id: t.id,
          windowId: t.windowId,
          index: t.index,
          title: t.title,
          url: t.url,
          active: t.active,
          pinned: t.pinned,
          status: t.status,
          incognito: t.incognito
        })));
        break;

      case 'tab_get':
        const tabGet = params.tabId
          ? await browser.tabs.get(params.tabId)
          : await getActiveTab();
        sendResponse(cmdId, true, tabGet);
        break;

      case 'tab_create':
        const tabCreate = await browser.tabs.create({
          url: params.url || 'about:blank',
          active: params.active !== false,
          pinned: !!params.pinned,
          windowId: params.windowId || undefined,
          index: params.index || undefined
        });
        sendResponse(cmdId, true, { id: tabCreate.id, url: tabCreate.url });
        break;

      case 'tab_close':
        if (params.tabId) {
          await browser.tabs.remove(params.tabId);
        } else if (params.tabIds) {
          await browser.tabs.remove(params.tabIds);
        } else {
          const active = await getActiveTab();
          await browser.tabs.remove(active.id);
        }
        sendResponse(cmdId, true, { closed: true });
        break;

      case 'tab_activate':
        const tabAct = params.tabId
          ? await browser.tabs.update(params.tabId, { active: true })
          : await browser.tabs.update(await getActiveTabId(), { active: true });
        if (params.windowId) {
          await browser.windows.update(params.windowId, { focused: true });
        } else if (tabAct && tabAct.windowId) {
          await browser.windows.update(tabAct.windowId, { focused: true });
        }
        sendResponse(cmdId, true, { id: tabAct.id, url: tabAct.url, windowId: tabAct.windowId });
        break;

      case 'tab_update':
        const updateOpts = {};
        if (params.url) updateOpts.url = params.url;
        if (params.hasOwnProperty('active')) updateOpts.active = params.active;
        if (params.hasOwnProperty('pinned')) updateOpts.pinned = params.pinned;
        if (params.hasOwnProperty('muted')) updateOpts.muted = params.muted;
        const tabUpd = await browser.tabs.update(params.tabId || (await getActiveTabId()), updateOpts);
        sendResponse(cmdId, true, { id: tabUpd.id, url: tabUpd.url });
        break;

      case 'tab_reload':
        await browser.tabs.reload(params.tabId || undefined, { bypassCache: !!params.bypassCache });
        sendResponse(cmdId, true, { reloaded: true });
        break;

      case 'tab_duplicate':
        const tabDup = await browser.tabs.duplicate(params.tabId || (await getActiveTabId()));
        sendResponse(cmdId, true, { id: tabDup.id, url: tabDup.url });
        break;

      case 'tab_move':
        const moveOpts = {};
        if (params.index !== undefined) moveOpts.index = params.index;
        if (params.windowId) moveOpts.windowId = params.windowId;
        const moved = await browser.tabs.move(params.tabId || (await getActiveTabId()), moveOpts);
        sendResponse(cmdId, true, moved);
        break;

      // === Window Management ===
      case 'window_list':
        const windows = await browser.windows.getAll({ populate: true });
        sendResponse(cmdId, true, windows.map(w => ({
          id: w.id,
          focused: w.focused,
          incognito: w.incognito,
          type: w.type,
          state: w.state,
          title: w.title,
          tabsCount: w.tabs ? w.tabs.length : 0
        })));
        break;

      case 'window_create':
        const winCreate = await browser.windows.create({
          url: params.url || undefined,
          type: params.type || 'normal',
          state: params.state || undefined,
          width: params.width || undefined,
          height: params.height || undefined,
          incognito: !!params.incognito
        });
        sendResponse(cmdId, true, { id: winCreate.id, tabsCount: winCreate.tabs ? winCreate.tabs.length : 0 });
        break;

      case 'window_close':
        await browser.windows.remove(params.windowId || (await getCurrentWindowId()));
        sendResponse(cmdId, true, { closed: true });
        break;

      // === Page / DOM ===
      case 'page_eval':
        const evalResult = await executeInTab(params.tabId, params.code);
        sendResponse(cmdId, true, evalResult);
        break;

      case 'page_get_html':
        const html = await executeInTab(params.tabId, 'document.documentElement.outerHTML');
        sendResponse(cmdId, true, html);
        break;

      case 'page_get_text':
        const text = await executeInTab(params.tabId, 'document.body ? document.body.innerText : ""');
        sendResponse(cmdId, true, text);
        break;

      case 'page_get_title':
        const title = await executeInTab(params.tabId, 'document.title');
        sendResponse(cmdId, true, title);
        break;

      case 'page_get_url':
        let urlTab;
        if (params.tabId) {
          urlTab = await browser.tabs.get(params.tabId);
        } else {
          urlTab = await getActiveTab();
        }
        sendResponse(cmdId, true, urlTab.url);
        break;

      case 'page_screenshot':
        const sshot = await browser.tabs.captureVisibleTab(params.windowId || null, {
          format: params.format || 'png',
          quality: params.quality || 90
        });
        sendResponse(cmdId, true, { dataUrl: sshot, format: params.format || 'png' });
        break;

      case 'page_click':
        await executeInTab(params.tabId, `
          (function() {
            const el = document.querySelector(${JSON.stringify(params.selector)});
            if (!el) throw new Error('Element not found: ' + ${JSON.stringify(params.selector)});
            el.click();
            return 'clicked ' + ${JSON.stringify(params.selector)};
          })()
        `);
        sendResponse(cmdId, true, { clicked: params.selector });
        break;

      case 'page_fill':
        await executeInTab(params.tabId, `
          (function() {
            const el = document.querySelector(${JSON.stringify(params.selector)});
            if (!el) throw new Error('Element not found: ' + ${JSON.stringify(params.selector)});
            const tag = el.tagName.toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select') {
              el.value = ${JSON.stringify(params.value)};
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (el.isContentEditable) {
              el.textContent = ${JSON.stringify(params.value)};
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }
            return 'filled';
          })()
        `);
        sendResponse(cmdId, true, { filled: params.selector, value: params.value });
        break;

      case 'page_select':
        await executeInTab(params.tabId, `
          (function() {
            const el = document.querySelector(${JSON.stringify(params.selector)});
            if (!el || el.tagName.toLowerCase() !== 'select') throw new Error('Select not found: ' + ${JSON.stringify(params.selector)});
            el.value = ${JSON.stringify(params.value)};
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return 'selected';
          })()
        `);
        sendResponse(cmdId, true, { selected: params.value });
        break;

      case 'page_scroll':
        await executeInTab(params.tabId, `
          window.scrollBy({
            top: ${params.y || 0},
            left: ${params.x || 0},
            behavior: '${params.smooth ? 'smooth' : 'auto'}'
          });
        `);
        sendResponse(cmdId, true, { scrolled: true });
        break;

      case 'page_scroll_to':
        await executeInTab(params.tabId, `
          window.scrollTo({
            top: ${params.y || 0},
            left: ${params.x || 0},
            behavior: '${params.smooth ? 'smooth' : 'auto'}'
          });
        `);
        sendResponse(cmdId, true, { scrolledTo: { x: params.x || 0, y: params.y || 0 } });
        break;

      case 'page_wait':
        if (params.timeout) {
          await new Promise(r => setTimeout(r, params.timeout));
          sendResponse(cmdId, true, { waited: params.timeout });
        } else if (params.selector) {
          await executeInTab(params.tabId, `
            (function() {
              return new Promise((resolve, reject) => {
                const el = document.querySelector(${JSON.stringify(params.selector)});
                if (el) { resolve('already present'); return; }
                const observer = new MutationObserver(() => {
                  if (document.querySelector(${JSON.stringify(params.selector)})) {
                    observer.disconnect();
                    resolve('found');
                  }
                });
                observer.observe(document.body, { childList: true, subtree: true, attributes: false });
                setTimeout(() => { observer.disconnect(); reject(new Error('Timeout waiting for ' + ${JSON.stringify(params.selector)})); }, ${params.waitTimeout || 10000});
              });
            })()
          `);
          sendResponse(cmdId, true, { found: params.selector });
        } else {
          sendResponse(cmdId, true, { waited: true });
        }
        break;

      case 'page_get_links':
        const links = await executeInTab(params.tabId, `
          Array.from(document.querySelectorAll('a[href]')).map(a => ({
            text: a.textContent.trim().substring(0, 200),
            href: a.href,
            target: a.target || '_self',
            rel: a.rel || ''
          }))
        `);
        sendResponse(cmdId, true, links);
        break;

      case 'page_get_forms':
        const forms = await executeInTab(params.tabId, `
          Array.from(document.forms).map(f => ({
            id: f.id,
            name: f.name,
            action: f.action,
            method: f.method,
            fields: Array.from(f.elements).map(e => ({
              name: e.name,
              id: e.id,
              type: e.type || e.tagName.toLowerCase(),
              value: e.value,
              disabled: e.disabled,
              readonly: e.readOnly
            }))
          }))
        `);
        sendResponse(cmdId, true, forms);
        break;

      case 'page_get_attributes':
        const attrs = await executeInTab(params.tabId, `
          (function() {
            const el = document.querySelector(${JSON.stringify(params.selector)});
            if (!el) throw new Error('Element not found');
            const att = {};
            for (const a of el.attributes) { att[a.name] = a.value; }
            return { tag: el.tagName, id: el.id, className: el.className, attributes: att, innerText: el.innerText?.substring(0, 500) };
          })()
        `);
        sendResponse(cmdId, true, attrs);
        break;

      // === Cookies ===
      case 'cookies_get':
        const cookieOpts = {};
        if (params.url) cookieOpts.url = params.url;
        if (params.domain) cookieOpts.domain = params.domain;
        if (params.name) cookieOpts.name = params.name;
        if (!cookieOpts.url && !cookieOpts.domain) {
          const activeTab = await getActiveTab();
          cookieOpts.url = activeTab.url;
        }
        const cookies = await browser.cookies.getAll(cookieOpts);
        sendResponse(cmdId, true, cookies.map(c => ({
          name: c.name,
          value: c.value,
          domain: c.domain,
          path: c.path,
          secure: c.secure,
          httpOnly: c.httpOnly,
          session: c.session,
          sameSite: c.sameSite,
          hostOnly: c.hostOnly,
          expirationDate: c.expirationDate || null
        })));
        break;

      case 'cookies_set':
        const setOpts = {};
        if (params.url) setOpts.url = params.url;
        else {
          const act = await getActiveTab();
          setOpts.url = act.url;
        }
        if (params.name) setOpts.name = params.name;
        if (params.value) setOpts.value = params.value;
        if (params.domain) setOpts.domain = params.domain;
        if (params.path) setOpts.path = params.path;
        if (params.secure !== undefined) setOpts.secure = params.secure;
        if (params.httpOnly !== undefined) setOpts.httpOnly = params.httpOnly;
        if (params.expirationDate) setOpts.expirationDate = params.expirationDate;
        if (params.sameSite) setOpts.sameSite = params.sameSite;
        const cookieSet = await browser.cookies.set(setOpts);
        sendResponse(cmdId, true, { name: cookieSet.name, domain: cookieSet.domain });
        break;

      case 'cookies_remove':
        if (!params.name) { sendResponse(cmdId, false, null, 'name required'); break; }
        let rmUrl = params.url;
        if (!rmUrl) {
          const act = await getActiveTab();
          rmUrl = act.url;
        }
        await browser.cookies.remove({ url: rmUrl, name: params.name });
        sendResponse(cmdId, true, { removed: params.name });
        break;

      case 'cookies_clear':
        const allCookies = await browser.cookies.getAll({});
        for (const c of allCookies) {
          try {
            // Need to construct a valid URL from the cookie domain
            const url = (c.secure ? 'https://' : 'http://') + c.domain.replace(/^\./, '') + c.path;
            await browser.cookies.remove({ url: url, name: c.name });
          } catch (e) {
            // skip cookies we can't construct URLs for
          }
        }
        sendResponse(cmdId, true, { cleared: allCookies.length });
        break;

      // === Storage ===
      case 'storage_get_local':
        const localData = params.key
          ? { [params.key]: (await browser.storage.local.get(params.key))[params.key] }
          : await browser.storage.local.get(null);
        sendResponse(cmdId, true, localData);
        break;

      case 'storage_set_local':
        await browser.storage.local.set(params.data || {});
        sendResponse(cmdId, true, { set: true });
        break;
