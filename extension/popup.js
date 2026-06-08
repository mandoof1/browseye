// Browseye — popup UI logic

const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const activeTabEl = document.getElementById('activeTab');
const logContainer = document.getElementById('logContainer');

// Background script sends us connection status updates via storage
browser.storage.onChanged.addListener((changes, area) => {
  if (area === 'local') {
    if (changes.ffc_status) updateUI(changes.ffc_status.newValue);
  }
});

// Request current state from background
browser.runtime.sendMessage({ type: 'popup_init' }).catch(() => {});

// Listen for direct messages from background
browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'status_update') {
    updateUI(msg.status);
  }
  if (msg.type === 'log') {
    addLog(msg.level, msg.text);
  }
});

function updateUI(status) {
  if (status === 'connected') {
    statusDot.className = 'status-badge connected';
    statusText.textContent = 'Connected';
  } else {
    statusDot.className = 'status-badge disconnected';
    statusText.textContent = 'Disconnected';
  }
}

// Get active tab info
browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
  if (tabs[0]) {
    const t = tabs[0];
    activeTabEl.textContent = (t.title || 'untitled').substring(0, 40) + '...';
  }
}).catch(() => {});

function addLog(level, text) {
  const entry = document.createElement('div');
  entry.className = 'log-entry ' + (level || 'info');
  const time = new Date().toLocaleTimeString();
  entry.textContent = `[${time}] ${text}`;
  logContainer.appendChild(entry);
  logContainer.scrollTop = logContainer.scrollHeight;
  // Keep last 50 entries
  while (logContainer.children.length > 50) {
    logContainer.removeChild(logContainer.firstChild);
  }
}

// Button actions
document.getElementById('btnScreenshot').addEventListener('click', () => {
  browser.runtime.sendMessage({ type: 'popup_action', action: 'screenshot' });
  addLog('info', 'Taking screenshot...');
});

document.getElementById('btnGetLinks').addEventListener('click', () => {
  browser.runtime.sendMessage({ type: 'popup_action', action: 'get_links' });
  addLog('info', 'Retrieving page links');
});

document.getElementById('btnGetHTML').addEventListener('click', () => {
  browser.runtime.sendMessage({ type: 'popup_action', action: 'get_html' });
  addLog('info', 'Retrieving page HTML');
});

document.getElementById('btnReconnect').addEventListener('click', () => {
  browser.runtime.sendMessage({ type: 'popup_action', action: 'reconnect' });
  addLog('info', 'Reconnecting WebSocket...');
});

// Listen for action results
browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'action_result') {
    if (msg.success) {
      addLog('success', msg.action + ': OK');
    } else {
      addLog('error', msg.action + ': ' + (msg.error || 'failed'));
    }
  }
});
