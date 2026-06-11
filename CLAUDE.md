# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 部署資訊

- **Production：** https://food-inventory-4ygl.onrender.com（Render 免費方案；儘管 `railway.toml` 存在，實際部署在 **Render**，不在 Railway）
- **GitHub：** https://github.com/srwang721tw/food-inventory
- 生產環境**必須**設定 `DATABASE_URL` 指向 Neon PostgreSQL。Render 的 filesystem 是 ephemeral，SQLite 資料每次重新部署都會清空。

## 指令

```bash
# 啟動虛擬環境（必要）
source .venv/bin/activate

# 啟動開發伺服器（用 5001 避免與系統衝突）
PORT=5001 python app.py

# 安裝依賴
pip install -r requirements.txt

# 生產伺服器（Render 使用）
gunicorn app:app --bind 0.0.0.0:$PORT
```

此專案**無測試**。

**零費用原則：** 整個系統不得產生任何持續費用。Gemini API 僅使用免費方案（Google AI Studio 免費配額）。禁止建議使用付費 API（OpenAI、Claude API 等）。

## 架構說明

這是一個以手機操作為主的家庭食物庫存 Web App，品牌名稱為 **PantryAI**。技術棧為 Flask + SQLAlchemy + Vanilla JS，無建置步驟。

---

## 後端（`app.py`）

### 資料模型

**`User`**
| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer PK | |
| `username` | String(50) unique | 帳號名稱 |
| `password_hash` | String(200) | Argon2 hash（含 salt，~95–130 chars）|
| `is_admin` | Boolean | 管理員旗標，預設 False |
| `nickname` | String(50) nullable | 使用者暱稱，顯示於 header |
| `created_at` | DateTime | |
| `locations` | relationship | cascade delete-orphan → Location |

**`Location`**
| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer PK | |
| `user_id` | Integer FK(users.id) | 所屬使用者（per-user 隔離）|
| `name` | String(100) | 地點名稱 |
| `icon` | String(10) | Emoji 圖示 |
| `sort_order` | Integer | 拖拉排序位置 |
| `created_at` | DateTime | |
| `items` | relationship | cascade delete-orphan → Item |

**`Item`**
| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer PK | |
| `location_id` | Integer FK(locations.id) | |
| `name` | String(200) | |
| `emoji` | String(10) | 預設 🍱 |
| `quantity` | Float | 預設 1 |
| `unit` | String(50) | 預設「個」|
| `purchase_date` | Date nullable | |
| `expiry_date` | Date nullable | |
| `notes` | Text | |
| `sort_order` | Integer | 拖拉排序位置，預設 0 |
| `created_at` / `updated_at` | DateTime | |

### Auth 機制

- Argon2 密碼雜湊（`argon2-cffi`），`_hash_pw()` / `_verify_pw()` helper
- `_verify_pw` 捕捉所有 Exception（防止 Argon2 邊緣情況觸發 500）
- `login_required` decorator：未登入頁面路由 → redirect `/login`
- `api_login_required` decorator：未登入 API 路由 → 401 JSON
- `admin_required` decorator：非 admin 使用者 → 403 JSON（疊加在 `api_login_required` 之後）
- 初始 admin 帳號由 `ADMIN_USERNAME` + `ADMIN_PASSWORD` 環境變數在 `db.create_all()` 後自動建立（users 表為空時）
- 新建帳號時自動 seed 3 個預設存放地點（冰箱、冷凍庫、乾貨櫃）

### 所有路由

| 路由 | 方法 | 登入 | 說明 |
|------|------|------|------|
| `/login` | GET · POST | 否 | 登入頁（fetch-based POST，iOS standalone 友善）|
| `/logout` | GET | 否 | 清除 session，redirect `/login` |
| `/` | GET | 是 | 渲染 `index.html`（含 `data`、`current_username`、`current_nickname`、`is_admin`、`is_gemini`）|
| `/sw.js` | GET | 否 | Service Worker（scope `/`，no-cache）|
| `/health` | GET | 否 | Render healthcheck |
| `/api/me/nickname` | PUT | 是 | 更新自己的暱稱（空字串 → NULL）|
| `/api/me/password` | PUT | 是 | 更新自己的密碼（需驗證舊密碼，min 4 字元）|
| `/api/users` | GET | 是 admin | 列出所有使用者 |
| `/api/users` | POST | 是 admin | 新增使用者（同時 seed 3 個預設地點）|
| `/api/users/<id>` | DELETE | 是 admin | 刪除使用者（不能刪自己；cascade 清除所有地點與食物）|
| `/api/locations` | GET · POST | 是 | 列出 / 新增存放地點 |
| `/api/locations/<id>` | PUT · DELETE | 是 | 更新 / 刪除存放地點 |
| `/api/locations/reorder` | POST | 是 | 更新排序（`[{id, sort_order}, ...]`）|
| `/api/items` | POST | 是 | 新增單一食物 |
| `/api/items/<id>` | GET · PUT · DELETE | 是 | 取得 / 更新 / 刪除食物 |
| `/api/items/batch` | POST | 是 | 批次新增食物（`[item_dict, ...]`，含 location_hint 自動比對）|
| `/api/items/reorder` | POST | 是 | 更新食物排序（`[{id, sort_order}, ...]`）|
| `/api/parse` | POST | 是 | NLP 解析文字 → item dict 列表 |
| `/api/recipe` | POST | 是 | AI 食譜建議（`{ingredients, combine}`，需 `NLP_BACKEND=gemini`）|

### 所有權驗證 / 共用 helpers

- `_own_location(loc_id)` — 查詢 Location，若 `user_id != session["user_id"]` 則 abort(403)
- `_own_item(item_id)` — 查詢 Item，透過 `item.location.user_id` 驗證所有權
- `_get_location_or_403(loc_id, uid)` — 回傳 `(loc, None)` 或 `(None, (jsonify(...), 403))`，供 item 端點使用
- `_next_item_sort_order(location_id)` — 查詢該地點的 max sort_order + 1
- `_parse_date(val)` — `date.fromisoformat(val) if val else None`
- `_item_from_dict(data, location_id, sort_order)` — 從 API JSON 建構 Item 物件

### 登入穩定性

login POST handler 用 try/except 包覆 DB 查詢，捕捉 Neon 冷啟動等暫時性連線錯誤，改回傳「伺服器暫時無法連線，請稍後再試」而非 500。

### Schema Migration（啟動時 inline 執行）

| Migration | 條件 | 動作 |
|-----------|------|------|
| `items.emoji` | 欄位不存在 | ALTER TABLE 加 VARCHAR(10) DEFAULT '🍱' |
| `locations.sort_order` | 欄位不存在 | ALTER TABLE 加 INTEGER DEFAULT 0，UPDATE SET sort_order=id |
| `locations.user_id` | 欄位不存在 | ALTER TABLE 加 INTEGER，UPDATE 指派給第一個 user |
| `users.nickname` | 欄位不存在 | ALTER TABLE 加 VARCHAR(50) |
| `items.sort_order` | 欄位不存在 | ALTER TABLE 加 INTEGER DEFAULT 0，UPDATE SET sort_order=id |

全部包在 `try/except Exception: pass` 中，對 SQLite 和 PostgreSQL 均相容。

---

## NLP 模組（`nlp.py`）

純本地中文食物文字解析器，使用 jieba 分詞 + regex。不呼叫外部 API。

Entry points：
- `parse_food_text(text)` → 單一 item dict
- `parse_multiple_foods(text)` → item dict 列表（透過 `_split_items` 處理多項）

解析欄位：`name`、`quantity`、`unit`、`purchase_date`、`expiry_date`、`location_hint`。
日期支援絕對（YYYY年M月D日、YYYY/M/D）、相對天數/週/月、自然語言（昨天、下週、三天後到期）。

**關鍵注意事項：**
- **Regex 順序：** first-match-wins。有前綴 pattern（`保存N週`）**必須放在**無前綴版本（`N週`）之前
- **`_split_items()` connector guard：** `還有`/`另外`/`以及` 當右側為純時間表達式時**不分割**
- **全局到期日傳播：** 先對完整文字取全局 `expiry_date`，再套用至各無個別到期日的項目

---

## Gemini NLP 模組（`gemini_nlp.py`）

使用 `google-genai` SDK 呼叫 Gemini（預設 `gemini-3.1-flash-lite`）。只在 `NLP_BACKEND=gemini` 且 `GEMINI_API_KEY` 已設定時啟用。

Entry points：
- `parse_with_gemini(text)` → item dict 列表（格式與 `parse_multiple_foods()` 相同）
- `suggest_recipe(inventory_items, user_ingredients='', combine=True)` → 食譜文字字串

System prompt 每次動態注入今天日期，要求回傳純 JSON 陣列（`response_mime_type='application/json'`，`temperature=0`）。

**`suggest_recipe` 三分支選材邏輯：**

| 條件 | 使用食材 |
|------|---------|
| `user_ingredients` + `combine=True` + 有庫存 | 使用者輸入 ＋ 庫存隨機 2–3 種 |
| `user_ingredients` + `combine=False` | 僅使用者輸入 |
| 無 `user_ingredients` | 庫存隨機 3–5 種 |

Retry 邏輯：最多 3 次，2s/4s backoff，僅 503/UNAVAILABLE 重試。

**Fallback 邏輯（`/api/parse`）：**
- `NLP_BACKEND=gemini`：先嘗試 Gemini，任何 Exception → 靜默 fallback 到 regex
- `NLP_BACKEND=regex`：直接使用 regex

**GC 注意事項：** google-genai v2.7.0 client GC 會關閉 HTTP transport。`parse_with_gemini` 和 `suggest_recipe` 皆在呼叫前以 `client = _client()` 儲存 reference。

---

## 前端（`templates/`）

**`login.html`** — 獨立登入頁（不繼承任何 template）。iOS 風格卡片，App 名稱 PantryAI，副標「您的冰箱守門員」。fetch-based login（`e.preventDefault()` + `fetch('/login', ...)`），避免 iOS standalone WebView 跳出 Safari。

**`index.html`** — 獨立 SPA，不繼承任何 template，自帶 inline 樣式。

所有狀態存在 `DATA` 物件（由 `{{ data|tojson }}` 初始化，Flask tojson filter 跳脫 HTML 特殊字元防止 script injection）。

Mutation 流程：call API → 更新 `DATA` → `render()` → toast（無整頁重載）

**Header 右側按鈕（由左到右）：**
- 👥 使用者管理（所有使用者可見）
- 🚪 登出
- 🌓 主題切換

**Header 標題：** `{current_nickname or '我的'} PantryAI`（`current_nickname` 由 Jinja2 server-render）

**使用者管理 Sheet 內容：**
- **我的暱稱**（所有使用者）：input + 儲存 → `PUT /api/me/nickname` → 即時更新 header
- **修改密碼**（所有使用者）：目前密碼 + 新密碼 → `PUT /api/me/password`
- **現有帳號**（admin only，Jinja2 `{% if is_admin %}`）：列表 + 🗑 刪除
- **新增帳號**（admin only）：帳號 + 密碼 → `POST /api/users`

**JS 全域變數（server-rendered）：**
- `DATA` — 所有 locations 和 items（`{{ data|tojson }}`）
- `IS_ADMIN` — Boolean（`{{ is_admin|tojson }}`）
- `IS_GEMINI` — Boolean，控制 AI 食譜建議區塊是否顯示
- `CURRENT_NICKNAME` — 字串（可為空，`{{ (current_nickname or '')|tojson }}`）

**AI 食譜建議區塊（`IS_GEMINI` 為 true 時顯示）：**
- 自訂食材 text input（可留空）
- 「結合現有庫存食材」checkbox（預設勾選）
- 按鈕 POST `{ingredients, combine}` → `/api/recipe` → 顯示食譜文字

---

## UI 設計規範

- 以手機操作為主，max-width 430px（橫式放寬至 700px），iOS 風格設計
- 深色/淺色/系統三段切換；`html.dark` class 控制 CSS 變數；偏好存於 localStorage
- 所有 mutation 為樂觀更新：先更新 `DATA` → `render()` → toast
- 食物排序：到期日最近優先，無到期日排最後，同到期日按名稱
- 到期色碼：紅（過期或 ≤3 天）、橘（≤7 天）、綠（>7 天）
- 左滑刪除（手機）：刪除鍵 `position: absolute; right: -76px`，`overflow: hidden` 初始隱藏；電腦版 hover 顯示垃圾桶
- 拖拉排序：≡ handle 綁定 `touchstart`（手機）+ `mousedown`（電腦），共用 `_dragStart / _dragMove / _dragEnd`，ghost clone，POST 到 `/api/locations/reorder`（地點）及 `/api/items/reorder`（食物）
- 下滑收回 sheet：監聽整個 `.sheet`（`scrollTop === 0` 保護），`dy > 10px` 開始追蹤，`dy > 100px` dismiss，touchmove 用 `{ passive: false }` 以 `preventDefault()`
- 點擊目標：只有 `.item-emoji` 和 `.item-info` 觸發 `openEditItem()`；手機左滑後 touchend `e.preventDefault()` 阻止 click
- 語音輸入：`recog.continuous = true`，持續錄音直到使用者手動停止
- iOS date input：須加 `-webkit-appearance: none; display: block; width: 100%; box-sizing: border-box` 才能在真機 Safari 對齊寬度

---

## JS 注意事項

- **殘留 event listener：** 移除 HTML 元素時，若對應的 JS ref 沒有一併移除，會靜默中斷整個 JS 執行
- **401 處理：** session 過期時 API 回傳 401，前端應導向 `/login`（目前 fetch 未全域攔截 401）
- **swipe-delete touch 處理：** `initSwipe()` 在 touchstart 儲存 `startTarget`，touchend 判斷 `startTarget.closest('.swipe-del')` 決定是否 preventDefault

---

## 環境變數

| 變數 | 說明 |
|------|------|
| `DATABASE_URL` | Neon PostgreSQL 連線字串。不設定時退回 SQLite（僅限本地開發）|
| `SECRET_KEY` | Flask session 金鑰 |
| `PORT` | 伺服器 port（預設 5000；本地建議用 5001）|
| `ADMIN_USERNAME` | 初始 admin 帳號名稱（users 表為空時自動建立）|
| `ADMIN_PASSWORD` | 初始 admin 帳號密碼 |
| `NLP_BACKEND` | `regex`（預設）或 `gemini`（需同時設 `GEMINI_API_KEY`）|
| `GEMINI_API_KEY` | Google AI Studio API Key（aistudio.google.com 取得）|
| `GEMINI_MODEL` | `gemini-3.1-flash-lite`（預設）或其他支援的 Gemini 模型 |
| `FLASK_DEBUG` | `1` 啟用 Flask debug mode（本地開發用）|
