1|1|# Browseye
2|2|
3|3|Full browser control for Firefox via WebSocket — tab management, DOM manipulation,
4|4|data extraction, network monitoring, and more. All from your terminal.
5|5|
6|6|## Architecture
7|7|
8|8|```
9|9|┌─────────────┐     ws://:8765     ┌──────────────────┐
10|10|│  Firefox     │◄──────────────────│  Browseye        │
11|11|│  Extension   │   commands/       │  Server (Python) │
12|12|│  (agent)     │   responses       │  :8765 + :8766   │
13|13|└─────────────┘                    └────────┬─────────┘
14|14|                                            │ ws://:8766
15|15|                                    ┌───────▼─────────┐
16|16|                                    │  CLI Client     │
17|17|                                    │  ff_control     │
18|18|                                    └─────────────────┘
19|19|```
20|20|
21|21|## Quick Start
22|22|
23|23|```bash
24|24|# 1. Install deps
25|25|pip install websockets
26|26|
27|27|# 2. Run the setup
28|28|cd ~/firefox-controller
29|29|chmod +x setup.sh
30|30|./setup.sh
31|31|
32|32|# 3. Load the extension in Firefox
33|33|#    Open about:debugging → This Firefox → Load Temporary Add-on
34|34|#    Select ~/firefox-controller/extension/manifest.json
35|35|
36|36|# 4. Control from terminal
37|37|ff_control ping
38|38|ff_control tab_list
39|39|ff_control --interactive
40|40|```
41|41|
42|42|## CLI Usage
43|43|
44|44|```bash
45|45|# List all open tabs
46|46|ff_control tab_list
47|47|
48|48|# Navigate active tab
49|49|ff_control navigate '{"url": "https://google.com"}'
50|50|
51|51|# Execute JavaScript on the page
52|52|ff_control page_eval '{"code": "document.title"}'
53|53|
54|54|# Take screenshot (returns data URL)
55|55|ff_control page_screenshot
56|56|
57|57|# Get cookies for current site
58|58|ff_control cookies_get
59|59|
60|60|# Click an element
61|61|ff_control page_click '{"selector": "#login-button"}'
62|62|
63|63|# Fill a form field
64|64|ff_control page_fill '{"selector": "#username", "value": "admin"}'
65|65|
66|66|# List window info
67|67|ff_control window_list
68|68|
69|69|# Network monitoring
70|70|ff_control network_start
71|71|ff_control network_get
72|72|
73|73|# Interactive mode
74|74|ff_control -i
75|75|
76|76|# JSON output for scripts
77|77|ff_control --json tab_list
78|78|```
79|79|
80|80|## All Commands
81|81|
82|82|### Tab Management
83|83|| Command | Params | Description |
84|84||---------|--------|-------------|
85|85|| `tab_list` | — | List all open tabs |
86|86|| `tab_get` | `tabId` | Get tab info |
87|87|| `tab_create` | `url`, `active` | Open new tab |
88|88|| `tab_close` | `tabId` / `tabIds[]` | Close tab |
89|89|| `tab_activate` | `tabId` | Switch to tab |
90|90|| `tab_update` | `tabId`, `url`, `active` | Modify tab |
91|91|| `tab_reload` | `tabId`, `bypassCache` | Reload tab |
92|92|| `tab_duplicate` | `tabId` | Duplicate tab |
93|93|| `tab_move` | `tabId`, `index`, `windowId` | Move tab |
94|94|| `tab_discard` | `tabId` | Discard tab (unload) |
95|95|| `tab_mute` / `tab_unmute` | `tabId` | Mute/unmute tab |
96|96|
97|97|### Window Management
98|98|| Command | Params | Description |
99|99||---------|--------|-------------|
100|100|| `window_list` | — | List all windows |
101|101|| `window_create` | `url`, `type`, `state`, `incognito` | Create window |
102|102|| `window_close` | `windowId` | Close window |
103|103|
104|104|### Page / DOM
105|105|| Command | Params | Description |
106|106||---------|--------|-------------|
107|107|| `page_eval` | `code` | Execute JS in page |
108|108|| `page_get_html` | `tabId` | Get page HTML |
109|109|| `page_get_text` | `tabId` | Get page text |
110|110|| `page_get_title` | `tabId` | Get page title |
111|111|| `page_get_url` | `tabId` | Get page URL |
112|112|| `page_screenshot` | `format`, `quality` | Screenshot tab |
113|113|| `page_click` | `selector` | Click element |
114|114|| `page_fill` | `selector`, `value` | Fill form field |
115|115|| `page_select` | `selector`, `value` | Select dropdown |
116|116|| `page_scroll` | `x`, `y`, `smooth` | Scroll page |
117|117|| `page_scroll_to` | `x`, `y`, `smooth` | Scroll to position |
118|118|| `page_wait` | `timeout` / `selector` | Wait for time or element |
119|119|| `page_get_links` | `tabId` | Extract all links |
120|120|| `page_get_forms` | `tabId` | Extract form structure |
121|121|| `page_get_attributes` | `selector` | Get element attributes |
122|122|
123|123|### Cookies
124|124|| Command | Params | Description |
125|125||---------|--------|-------------|
126|126|| `cookies_get` | `url`, `domain`, `name` | Get cookies |
127|127|| `cookies_set` | `name`, `value`, `domain`, `path`, `secure`, `httpOnly` | Set cookie |
128|128|| `cookies_remove` | `name`, `url` | Remove cookie |
129|129|| `cookies_clear` | — | Clear all cookies |
130|130|
131|131|### History
132|132|| Command | Params | Description |
133|133||---------|--------|-------------|
134|134|| `history_search` | `text`, `maxResults`, `startTime`, `endTime` | Search history |
135|135|| `history_delete_url` | `url` | Delete from history |
136|136|| `history_delete_range` | `startTime`, `endTime` | Delete time range |
137|137|| `history_clear` | — | Clear all history |
138|138|
139|139|### Downloads
140|140|| Command | Params | Description |
141|141||---------|--------|-------------|
142|142|| `downloads_download` | `url`, `filename`, `conflictAction` | Download file |
143|143|| `downloads_list` | — | List recent downloads |
144|144|| `downloads_open` | `downloadId` | Open downloaded file |
145|145|| `downloads_remove_file` | `downloadId` | Delete downloaded file |
146|146|
147|147|### Storage
148|148|| Command | Params | Description |
149|149||---------|--------|-------------|
150|150|| `storage_get_local` | `key` | Get extension storage |
151|151|| `storage_set_local` | `data` | Set extension storage |
152|152|| `storage_clear_local` | — | Clear extension storage |
153|153|| `storage_get_page` | `tabId` | Get page localStorage/sessionStorage |
154|154|
155|155|### Network
156|156|| Command | Params | Description |
157|157||---------|--------|-------------|
158|158|| `network_start` | — | Start capturing requests |
159|159|| `network_stop` | — | Stop capturing |
160|160|| `network_get` | `keep` | Get captured requests |
161|161|| `network_clear` | — | Clear captured buffer |
162|162|| `network_block` | `pattern` | Block URLs matching pattern |
163|163|
164|164|### Bookmarks
165|165|| Command | Params | Description |
166|166||---------|--------|-------------|
167|167|| `bookmarks_list` | — | List all bookmarks |
168|168|| `bookmarks_create` | `title`, `url`, `parentId` | Add bookmark |
169|169|| `bookmarks_remove` | `id` | Remove bookmark |
170|170|
171|171|### Other
172|172|| Command | Params | Description |
173|173||---------|--------|-------------|
174|174|| `sessions_list` | `maxResults` | Recently closed tabs |
175|175|| `sessions_restore` | `sessionId` | Restore closed tab |
176|176|| `clipboard_read` | `tabId` | Read clipboard |
177|177|| `clipboard_write` | `text` | Write clipboard |
178|178|| `notify` | `title`, `message` | Show notification |
179|179|| `browser_info` | — | Get Firefox version info |
180|180|| `tab_execute_script` | `code`, `file`, `allFrames` | Execute script in tab |
181|181|| `tab_insert_css` | `code`, `file`, `allFrames` | Inject CSS |
182|182|| `get_info` | — | Get extension info |
183|183|| `ping` | — | Health check |
184|184|
185|185|## Permanent Extension Installation
186|186|
187|187|1. Open `about:config` → set `xpinstall.signatures.required` to `false`
188|188|2. Zip the extension:
189|189|   ```bash
190|190|   cd ~/firefox-controller/extension
191|191|   zip -r ../browseye.zip *
192|192|   ```
193|193|3. Open `about:addons` → Gear icon → Install Add-on From File
194|194|4. Select `browseye.zip`
195|195|
196|196|## Server Management
197|197|
198|198|```bash
199|199|# Start server
200|200|systemctl --user start browseye
201|201|
202|202|# Enable autostart
203|203|systemctl --user enable browseye
204|204|
205|205|# Check status
206|206|systemctl --user status browseye
207|207|
208|208|# View logs
209|209|journalctl --user -u browseye -f
210|210|```
211|211|