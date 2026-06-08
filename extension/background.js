1|// Browseye — background script
2|// Connects to local WebSocket server and executes browser commands
3|
4|const WS_URL = 'ws://127.0.0.1:8765';
5|const RECONNECT_DELAY = 3000;
6|
7|let ws = null;
8|let reconnectTimer = null;
9|let commandId = 0;
10|let pendingCommands = new Map();
11|let capturedRequests = [];
12|let monitoringNetwork = false;
13|
14|// ---------------------------------------------------------------------------
15|// WebSocket connection management
16|// ---------------------------------------------------------------------------
17|
18|function connect() {
19|  if (ws && ws.readyState === WebSocket.OPEN) return;
20|
21|  try {
22|    ws = new WebSocket(WS_URL);
23|  } catch (e) {
24|    console.error('[FFC] WebSocket creation failed:', e.message);
25|    scheduleReconnect();
26|    return;
27|  }
28|
29|  ws.onopen = () => {
30|    console.log('[FFC] Connected to controller server');
31|    updateStatus('connected');
32|    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
33|    // Send handshake so the server knows we're the extension agent
34|    sendRaw({ type: 'agent_hello', agent: 'firefox-extension', version: '1.0.0' });
35|  };
36|
37|  ws.onclose = (ev) => {
38|    console.log('[FFC] Disconnected (code=' + ev.code + '). Reconnecting in ' + (RECONNECT_DELAY/1000) + 's');
39|    updateStatus('disconnected');
40|    ws = null;
41|    scheduleReconnect();
42|  };
43|
44|  ws.onerror = (err) => {
45|    console.error('[FFC] WebSocket error');
46|    // onclose will fire after this
47|  };
48|
49|  ws.onmessage = (msg) => {
50|    try {
51|      const data = JSON.parse(msg.data);
52|      handleCommand(data);
53|    } catch (e) {
54|      console.error('[FFC] Failed to parse message:', e.message);
55|    }
56|  };
57|}
58|
59|function scheduleReconnect() {
60|  if (reconnectTimer) return;
61|  reconnectTimer = setTimeout(() => {
62|    reconnectTimer = null;
63|    connect();
64|  }, RECONNECT_DELAY);
65|}
66|
67|function sendRaw(obj) {
68|  if (!ws || ws.readyState !== WebSocket.OPEN) {
69|    console.warn('[FFC] Cannot send — not connected');
70|    return false;
71|  }
72|  try {
73|    ws.send(JSON.stringify(obj));
74|    return true;
75|  } catch (e) {
76|    console.error('[FFC] Send failed:', e.message);
77|    return false;
78|  }
79|}
80|
81|function sendResponse(cmdId, success, data, error) {
82|  sendRaw({
83|    type: 'response',
84|    id: cmdId,
85|    success: success,
86|    data: data,
87|    error: error ? String(error) : null
88|  });
89|}
90|
91|function updateStatus(status) {
92|  sendRaw({ type: 'status_update', status: status });
93|  browser.browserAction.setBadgeText({ text: status === 'connected' ? 'ON' : 'OFF' });
94|  browser.browserAction.setBadgeBackgroundColor({ color: status === 'connected' ? '#00aa00' : '#aa0000' });
95|}
96|
97|// ---------------------------------------------------------------------------
98|// Command dispatcher
99|// ---------------------------------------------------------------------------
100|
101|async function handleCommand(msg) {
102|  const cmdId = msg.id || 'anon-' + (commandId++);
103|  const cmd = msg.command;
104|  const params = msg.params || {};
105|
106|  console.log('[FFC] Command:', cmd, params);
107|
108|  try {
109|    switch (cmd) {
110|
111|      // === System ===
112|      case 'ping':
113|        sendResponse(cmdId, true, { pong: true, ts: Date.now() });
114|        break;
115|
116|      case 'get_info':
117|        sendResponse(cmdId, true, {
118|          extension: 'Browseye v1.0.0',
119|          browser: navigator.userAgent,
120|          platform: navigator.platform,
121|          ws_connected: !!(ws && ws.readyState === WebSocket.OPEN)
122|        });
123|        break;
124|
125|      // === Tab Management ===
126|      case 'tab_list':
127|        const tabs = await browser.tabs.query({});
128|        sendResponse(cmdId, true, tabs.map(t => ({
129|          id: t.id,
130|          windowId: t.windowId,
131|          index: t.index,
132|          title: t.title,
133|          url: t.url,
134|          active: t.active,
135|          pinned: t.pinned,
136|          status: t.status,
137|          incognito: t.incognito
138|        })));
139|        break;
140|
141|      case 'tab_get':
142|        const tabGet = params.tabId
143|          ? await browser.tabs.get(params.tabId)
144|          : await getActiveTab();
145|        sendResponse(cmdId, true, tabGet);
146|        break;
147|
148|      case 'tab_create':
149|        const tabCreate = await browser.tabs.create({
150|          url: params.url || 'about:blank',
151|          active: params.active !== false,
152|          pinned: !!params.pinned,
153|          windowId: params.windowId || undefined,
154|          index: params.index || undefined
155|        });
156|        sendResponse(cmdId, true, { id: tabCreate.id, url: tabCreate.url });
157|        break;
158|
159|      case 'tab_close':
160|        if (params.tabId) {
161|          await browser.tabs.remove(params.tabId);
162|        } else if (params.tabIds) {
163|          await browser.tabs.remove(params.tabIds);
164|        } else {
165|          const active = await getActiveTab();
166|          await browser.tabs.remove(active.id);
167|        }
168|        sendResponse(cmdId, true, { closed: true });
169|        break;
170|
171|      case 'tab_activate':
172|        const tabAct = params.tabId
173|          ? await browser.tabs.update(params.tabId, { active: true })
174|          : await browser.tabs.update(await getActiveTabId(), { active: true });
175|        if (params.windowId) {
176|          await browser.windows.update(params.windowId, { focused: true });
177|        } else if (tabAct && tabAct.windowId) {
178|          await browser.windows.update(tabAct.windowId, { focused: true });
179|        }
180|        sendResponse(cmdId, true, { id: tabAct.id, url: tabAct.url, windowId: tabAct.windowId });
181|        break;
182|
183|      case 'tab_update':
184|        const updateOpts = {};
185|        if (params.url) updateOpts.url = params.url;
186|        if (params.hasOwnProperty('active')) updateOpts.active = params.active;
187|        if (params.hasOwnProperty('pinned')) updateOpts.pinned = params.pinned;
188|        if (params.hasOwnProperty('muted')) updateOpts.muted = params.muted;
189|        const tabUpd = await browser.tabs.update(params.tabId || (await getActiveTabId()), updateOpts);
190|        sendResponse(cmdId, true, { id: tabUpd.id, url: tabUpd.url });
191|        break;
192|
193|      case 'tab_reload':
194|        await browser.tabs.reload(params.tabId || undefined, { bypassCache: !!params.bypassCache });
195|        sendResponse(cmdId, true, { reloaded: true });
196|        break;
197|
198|      case 'tab_duplicate':
199|        const tabDup = await browser.tabs.duplicate(params.tabId || (await getActiveTabId()));
200|        sendResponse(cmdId, true, { id: tabDup.id, url: tabDup.url });
201|        break;
202|
203|      case 'tab_move':
204|        const moveOpts = {};
205|        if (params.index !== undefined) moveOpts.index = params.index;
206|        if (params.windowId) moveOpts.windowId = params.windowId;
207|        const moved = await browser.tabs.move(params.tabId || (await getActiveTabId()), moveOpts);
208|        sendResponse(cmdId, true, moved);
209|        break;
210|
211|      // === Window Management ===
212|      case 'window_list':
213|        const windows = await browser.windows.getAll({ populate: true });
214|        sendResponse(cmdId, true, windows.map(w => ({
215|          id: w.id,
216|          focused: w.focused,
217|          incognito: w.incognito,
218|          type: w.type,
219|          state: w.state,
220|          title: w.title,
221|          tabsCount: w.tabs ? w.tabs.length : 0
222|        })));
223|        break;
224|
225|      case 'window_create':
226|        const winCreate = await browser.windows.create({
227|          url: params.url || undefined,
228|          type: params.type || 'normal',
229|          state: params.state || undefined,
230|          width: params.width || undefined,
231|          height: params.height || undefined,
232|          incognito: !!params.incognito
233|        });
234|        sendResponse(cmdId, true, { id: winCreate.id, tabsCount: winCreate.tabs ? winCreate.tabs.length : 0 });
235|        break;
236|
237|      case 'window_close':
238|        await browser.windows.remove(params.windowId || (await getCurrentWindowId()));
239|        sendResponse(cmdId, true, { closed: true });
240|        break;
241|
242|      // === Page / DOM ===
243|      case 'page_eval':
244|        const evalResult = await executeInTab(params.tabId, params.code);
245|        sendResponse(cmdId, true, evalResult);
246|        break;
247|
248|      case 'page_get_html':
249|        const html = await executeInTab(params.tabId, 'document.documentElement.outerHTML');
250|        sendResponse(cmdId, true, html);
251|        break;
252|
253|      case 'page_get_text':
254|        const text = await executeInTab(params.tabId, 'document.body ? document.body.innerText : ""');
255|        sendResponse(cmdId, true, text);
256|        break;
257|
258|      case 'page_get_title':
259|        const title = await executeInTab(params.tabId, 'document.title');
260|        sendResponse(cmdId, true, title);
261|        break;
262|
263|      case 'page_get_url':
264|        let urlTab;
265|        if (params.tabId) {
266|          urlTab = await browser.tabs.get(params.tabId);
267|        } else {
268|          urlTab = await getActiveTab();
269|        }
270|        sendResponse(cmdId, true, urlTab.url);
271|        break;
272|
273|      case 'page_screenshot':
274|        const sshot = await browser.tabs.captureVisibleTab(params.windowId || null, {
275|          format: params.format || 'png',
276|          quality: params.quality || 90
277|        });
278|        sendResponse(cmdId, true, { dataUrl: sshot, format: params.format || 'png' });
279|        break;
280|
281|      case 'page_click':
282|        await executeInTab(params.tabId, `
283|          (function() {
284|            const el = document.querySelector(${JSON.stringify(params.selector)});
285|            if (!el) throw new Error('Element not found: ' + ${JSON.stringify(params.selector)});
286|            el.click();
287|            return 'clicked ' + ${JSON.stringify(params.selector)};
288|          })()
289|        `);
290|        sendResponse(cmdId, true, { clicked: params.selector });
291|        break;
292|
293|      case 'page_fill':
294|        await executeInTab(params.tabId, `
295|          (function() {
296|            const el = document.querySelector(${JSON.stringify(params.selector)});
297|            if (!el) throw new Error('Element not found: ' + ${JSON.stringify(params.selector)});
298|            const tag = el.tagName.toLowerCase();
299|            if (tag === 'input' || tag === 'textarea' || tag === 'select') {
300|              el.value = ${JSON.stringify(params.value)};
301|              el.dispatchEvent(new Event('input', { bubbles: true }));
302|              el.dispatchEvent(new Event('change', { bubbles: true }));
303|            } else if (el.isContentEditable) {
304|              el.textContent = ${JSON.stringify(params.value)};
305|              el.dispatchEvent(new Event('input', { bubbles: true }));
306|            }
307|            return 'filled';
308|          })()
309|        `);
310|        sendResponse(cmdId, true, { filled: params.selector, value: params.value });
311|        break;
312|
313|      case 'page_select':
314|        await executeInTab(params.tabId, `
315|          (function() {
316|            const el = document.querySelector(${JSON.stringify(params.selector)});
317|            if (!el || el.tagName.toLowerCase() !== 'select') throw new Error('Select not found: ' + ${JSON.stringify(params.selector)});
318|            el.value = ${JSON.stringify(params.value)};
319|            el.dispatchEvent(new Event('change', { bubbles: true }));
320|            return 'selected';
321|          })()
322|        `);
323|        sendResponse(cmdId, true, { selected: params.value });
324|        break;
325|
326|      case 'page_scroll':
327|        await executeInTab(params.tabId, `
328|          window.scrollBy({
329|            top: ${params.y || 0},
330|            left: ${params.x || 0},
331|            behavior: '${params.smooth ? 'smooth' : 'auto'}'
332|          });
333|        `);
334|        sendResponse(cmdId, true, { scrolled: true });
335|        break;
336|
337|      case 'page_scroll_to':
338|        await executeInTab(params.tabId, `
339|          window.scrollTo({
340|            top: ${params.y || 0},
341|            left: ${params.x || 0},
342|            behavior: '${params.smooth ? 'smooth' : 'auto'}'
343|          });
344|        `);
345|        sendResponse(cmdId, true, { scrolledTo: { x: params.x || 0, y: params.y || 0 } });
346|        break;
347|
348|      case 'page_wait':
349|        if (params.timeout) {
350|          await new Promise(r => setTimeout(r, params.timeout));
351|          sendResponse(cmdId, true, { waited: params.timeout });
352|        } else if (params.selector) {
353|          await executeInTab(params.tabId, `
354|            (function() {
355|              return new Promise((resolve, reject) => {
356|                const el = document.querySelector(${JSON.stringify(params.selector)});
357|                if (el) { resolve('already present'); return; }
358|                const observer = new MutationObserver(() => {
359|                  if (document.querySelector(${JSON.stringify(params.selector)})) {
360|                    observer.disconnect();
361|                    resolve('found');
362|                  }
363|                });
364|                observer.observe(document.body, { childList: true, subtree: true, attributes: false });
365|                setTimeout(() => { observer.disconnect(); reject(new Error('Timeout waiting for ' + ${JSON.stringify(params.selector)})); }, ${params.waitTimeout || 10000});
366|              });
367|            })()
368|          `);
369|          sendResponse(cmdId, true, { found: params.selector });
370|        } else {
371|          sendResponse(cmdId, true, { waited: true });
372|        }
373|        break;
374|
375|      case 'page_get_links':
376|        const links = await executeInTab(params.tabId, `
377|          Array.from(document.querySelectorAll('a[href]')).map(a => ({
378|            text: a.textContent.trim().substring(0, 200),
379|            href: a.href,
380|            target: a.target || '_self',
381|            rel: a.rel || ''
382|          }))
383|        `);
384|        sendResponse(cmdId, true, links);
385|        break;
386|
387|      case 'page_get_forms':
388|        const forms = await executeInTab(params.tabId, `
389|          Array.from(document.forms).map(f => ({
390|            id: f.id,
391|            name: f.name,
392|            action: f.action,
393|            method: f.method,
394|            fields: Array.from(f.elements).map(e => ({
395|              name: e.name,
396|              id: e.id,
397|              type: e.type || e.tagName.toLowerCase(),
398|              value: e.value,
399|              disabled: e.disabled,
400|              readonly: e.readOnly
401|            }))
402|          }))
403|        `);
404|        sendResponse(cmdId, true, forms);
405|        break;
406|
407|      case 'page_get_attributes':
408|        const attrs = await executeInTab(params.tabId, `
409|          (function() {
410|            const el = document.querySelector(${JSON.stringify(params.selector)});
411|            if (!el) throw new Error('Element not found');
412|            const att = {};
413|            for (const a of el.attributes) { att[a.name] = a.value; }
414|            return { tag: el.tagName, id: el.id, className: el.className, attributes: att, innerText: el.innerText?.substring(0, 500) };
415|          })()
416|        `);
417|        sendResponse(cmdId, true, attrs);
418|        break;
419|
420|      // === Cookies ===
421|      case 'cookies_get':
422|        const cookieOpts = {};
423|        if (params.url) cookieOpts.url = params.url;
424|        if (params.domain) cookieOpts.domain = params.domain;
425|        if (params.name) cookieOpts.name = params.name;
426|        if (!cookieOpts.url && !cookieOpts.domain) {
427|          const activeTab = await getActiveTab();
428|          cookieOpts.url = activeTab.url;
429|        }
430|        const cookies = await browser.cookies.getAll(cookieOpts);
431|        sendResponse(cmdId, true, cookies.map(c => ({
432|          name: c.name,
433|          value: c.value,
434|          domain: c.domain,
435|          path: c.path,
436|          secure: c.secure,
437|          httpOnly: c.httpOnly,
438|          session: c.session,
439|          sameSite: c.sameSite,
440|          hostOnly: c.hostOnly,
441|          expirationDate: c.expirationDate || null
442|        })));
443|        break;
444|
445|      case 'cookies_set':
446|        const setOpts = {};
447|        if (params.url) setOpts.url = params.url;
448|        else {
449|          const act = await getActiveTab();
450|          setOpts.url = act.url;
451|        }
452|        if (params.name) setOpts.name = params.name;
453|        if (params.value) setOpts.value = params.value;
454|        if (params.domain) setOpts.domain = params.domain;
455|        if (params.path) setOpts.path = params.path;
456|        if (params.secure !== undefined) setOpts.secure = params.secure;
457|        if (params.httpOnly !== undefined) setOpts.httpOnly = params.httpOnly;
458|        if (params.expirationDate) setOpts.expirationDate = params.expirationDate;
459|        if (params.sameSite) setOpts.sameSite = params.sameSite;
460|        const cookieSet = await browser.cookies.set(setOpts);
461|        sendResponse(cmdId, true, { name: cookieSet.name, domain: cookieSet.domain });
462|        break;
463|
464|      case 'cookies_remove':
465|        if (!params.name) { sendResponse(cmdId, false, null, 'name required'); break; }
466|        let rmUrl = params.url;
467|        if (!rmUrl) {
468|          const act = await getActiveTab();
469|          rmUrl = act.url;
470|        }
471|        await browser.cookies.remove({ url: rmUrl, name: params.name });
472|        sendResponse(cmdId, true, { removed: params.name });
473|        break;
474|
475|      case 'cookies_clear':
476|        const allCookies = await browser.cookies.getAll({});
477|        for (const c of allCookies) {
478|          try {
479|            // Need to construct a valid URL from the cookie domain
480|            const url = (c.secure ? 'https://' : 'http://') + c.domain.replace(/^\./, '') + c.path;
481|            await browser.cookies.remove({ url: url, name: c.name });
482|          } catch (e) {
483|            // skip cookies we can't construct URLs for
484|          }
485|        }
486|        sendResponse(cmdId, true, { cleared: allCookies.length });
487|        break;
488|
489|      // === Storage ===
490|      case 'storage_get_local':
491|        const localData = params.key
492|          ? { [params.key]: (await browser.storage.local.get(params.key))[params.key] }
493|          : await browser.storage.local.get(null);
494|        sendResponse(cmdId, true, localData);
495|        break;
496|
497|      case 'storage_set_local':
498|        await browser.storage.local.set(params.data || {});
499|        sendResponse(cmdId, true, { set: true });
500|        break;
501|