1|// Browseye — popup UI logic
2|
3|const statusDot = document.getElementById('statusDot');
4|const statusText = document.getElementById('statusText');
5|const activeTabEl = document.getElementById('activeTab');
6|const logContainer = document.getElementById('logContainer');
7|
8|// Background script sends us connection status updates via storage
9|browser.storage.onChanged.addListener((changes, area) => {
10|  if (area === 'local') {
11|    if (changes.ffc_status) updateUI(changes.ffc_status.newValue);
12|  }
13|});
14|
15|// Request current state from background
16|browser.runtime.sendMessage({ type: 'popup_init' }).catch(() => {});
17|
18|// Listen for direct messages from background
19|browser.runtime.onMessage.addListener((msg) => {
20|  if (msg.type === 'status_update') {
21|    updateUI(msg.status);
22|  }
23|  if (msg.type === 'log') {
24|    addLog(msg.level, msg.text);
25|  }
26|});
27|
28|function updateUI(status) {
29|  if (status === 'connected') {
30|    statusDot.className = 'status-badge connected';
31|    statusText.textContent = 'Connected';
32|  } else {
33|    statusDot.className = 'status-badge disconnected';
34|    statusText.textContent = 'Disconnected';
35|  }
36|}
37|
38|// Get active tab info
39|browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
40|  if (tabs[0]) {
41|    const t = tabs[0];
42|    activeTabEl.textContent = (t.title || 'untitled').substring(0, 40) + '...';
43|  }
44|}).catch(() => {});
45|
46|function addLog(level, text) {
47|  const entry = document.createElement('div');
48|  entry.className = 'log-entry ' + (level || 'info');
49|  const time = new Date().toLocaleTimeString();
50|  entry.textContent = `[${time}] ${text}`;
51|  logContainer.appendChild(entry);
52|  logContainer.scrollTop = logContainer.scrollHeight;
53|  // Keep last 50 entries
54|  while (logContainer.children.length > 50) {
55|    logContainer.removeChild(logContainer.firstChild);
56|  }
57|}
58|
59|// Button actions
60|document.getElementById('btnScreenshot').addEventListener('click', () => {
61|  browser.runtime.sendMessage({ type: 'popup_action', action: 'screenshot' });
62|  addLog('info', 'Taking screenshot...');
63|});
64|
65|document.getElementById('btnGetLinks').addEventListener('click', () => {
66|  browser.runtime.sendMessage({ type: 'popup_action', action: 'get_links' });
67|  addLog('info', 'Retrieving page links');
68|});
69|
70|document.getElementById('btnGetHTML').addEventListener('click', () => {
71|  browser.runtime.sendMessage({ type: 'popup_action', action: 'get_html' });
72|  addLog('info', 'Retrieving page HTML');
73|});
74|
75|document.getElementById('btnReconnect').addEventListener('click', () => {
76|  browser.runtime.sendMessage({ type: 'popup_action', action: 'reconnect' });
77|  addLog('info', 'Reconnecting WebSocket...');
78|});
79|
80|// Listen for action results
81|browser.runtime.onMessage.addListener((msg) => {
82|  if (msg.type === 'action_result') {
83|    if (msg.success) {
84|      addLog('success', msg.action + ': OK');
85|    } else {
86|      addLog('error', msg.action + ': ' + (msg.error || 'failed'));
87|    }
88|  }
89|});
90|