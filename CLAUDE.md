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

這是一個以手機操作為主的家庭食物庫存 Web App。技術棧為 Flask + SQLAlchemy + Vanilla JS，無建置步驟。

### 後端（`app.py`）

三個 SQLAlchemy Model：
- **`User`**：使用者帳號。欄位有 username（unique）、password_hash（Argon2）、is_admin、created_at。
- **`Location`**：存放地點（如冰箱、冷凍庫）。有多個 `Item`，cascade delete。
- **`Item`**：食物項目，欄位有 name、emoji、quantity、unit、purchase_date、expiry_date、notes、FK 指向 Location。

Auth 機制：
- Argon2 密碼雜湊（`argon2-cffi`），`_hash_pw()` / `_verify_pw()` helper。
- `login_required` decorator：未登入頁面路由 → redirect `/login`。
- `api_login_required` decorator：未登入 API 路由 → 401 JSON。
- 初始 admin 帳號由 `ADMIN_USERNAME` + `ADMIN_PASSWORD` 環境變數在 `db.create_all()` 後自動建立（users 表為空時）。

路由：
- `GET|POST /login` — 登入頁（HTML form POST，非 AJAX）
- `GET /logout` — 清除 session，redirect 到 `/login`
- `GET /` — 渲染 `index.html`（含 `data_json`、`current_username`、`is_admin`）
- `GET /location/<id>` — 渲染 `location.html`（legacy，目前未使用）
- `GET /health` — Render healthcheck（不需登入）
- REST API（全部需登入）：
  - `GET|POST /api/users` — 列出/新增使用者（admin only）
  - `DELETE /api/users/<id>` — 刪除使用者（admin only，不能刪自己）
  - `GET|POST /api/locations`、`PUT|DELETE /api/locations/<id>`、`POST /api/locations/reorder`
  - `GET|PUT|DELETE /api/items/<id>`、`POST /api/items`、`POST /api/items/batch`
  - `POST /api/parse` — NLP 解析，根據 `NLP_BACKEND` env var 選擇 regex 或 Gemini

資料庫：本地用 SQLite（`instance/food_inventory.db`）；生產用 Neon PostgreSQL（`DATABASE_URL` 環境變數）。Schema migration 在啟動時 inline 執行。

### NLP 模組（`nlp.py`）

純本地的中文食物文字解析器，使用 jieba 分詞 + regex 抽取日期/數量。不呼叫任何外部 API。

Entry points：
- `parse_food_text(text)` → 單一 item dict
- `parse_multiple_foods(text)` → item dict 列表（透過 `_split_items` 處理多項）

解析欄位：`name`、`quantity`、`unit`、`purchase_date`、`expiry_date`、`location_hint`。日期支援絕對日期（YYYY年M月D日、YYYY/M/D）、相對天數/週/月、自然語言片語（昨天、下週、三天後到期等）。

### Gemini NLP 模組（`gemini_nlp.py`）

使用 Google `google-genai` SDK 呼叫 Gemini 2.0/2.5 Flash。只在 `NLP_BACKEND=gemini` 且 `GEMINI_API_KEY` 已設定時啟用。

Entry point：
- `parse_with_gemini(text)` → item dict 列表（格式與 `parse_multiple_foods()` 相同）

System prompt 每次動態注入今天日期，要求回傳純 JSON 陣列（`response_mime_type='application/json'`，`temperature=0`）。

### 前端（templates/）

**`login.html`** — 獨立登入頁（不繼承 base.html）。iOS 風格卡片式設計，同樣支援深/淺色模式。`<form method="POST">`（非 AJAX，確保 JS 失效時仍可登入）。

**`base.html`** — 共用 CSS 設計系統（CSS 變數、Sheet/Overlay、表單、按鈕、Toast、Emoji grid、語音按鈕）與共用 JS（`toast()`、`showSheet()`、`hideSheet()`）。由 `location.html` 繼承。

**`index.html`** — 獨立 SPA（**不**繼承 `base.html`，自帶 inline 樣式）。渲染地點 accordion 列表，每個 accordion 內含食物卡片。所有狀態存在 `DATA` 物件（由 server-rendered `data_json` 初始化）。Mutation 流程：call API → 更新 `DATA` → 呼叫 `render()` → 顯示 toast（無整頁重新載入）。

Header 右側按鈕（由左到右）：👥 使用者管理（admin 才顯示，Jinja2 `{% if is_admin %}`）、🚪 登出、🌓 主題切換。

**`location.html`** — legacy 地點詳細頁面（繼承 `base.html`）。目前未使用，被 `index.html` 的 accordion SPA 取代。保留但不維護。

### NLP 注意事項

- **Regex 順序：** pattern 採用 first-match-wins。有前綴的 pattern（`保存N週`、`可以放N天`）**必須放在** 無前綴版本（`N週`、`N天`）之前。
- **`_split_items()` 的 connector guard：** `還有`/`另外`/`以及` 連接詞用於分割多項食物，但當右側是純時間表達式（如「還有五天到期」）時**不應分割**。
- **`_split_items()` 的雙模式分割（rule 4）：** qty-first → 在 NUM+UNIT 之前分割；name-first → 在 NUM+UNIT 之後分割，尾部全局 context 丟棄。
- **全局到期日傳播：** `parse_multiple_foods` 在分割前先對完整文字呼叫 `parse_food_text` 取得全局 `expiry_date`，再傳播給沒有個別到期日的各項目。

### JS 注意事項

- **殘留的 event listener：** 移除 HTML 元素時，若對應的 JS ref 沒有一併移除，會靜默中斷整個 JS 執行。
- **401 處理：** session 過期時 API 回傳 401，前端應導向 `/login`（目前 fetch 未全域攔截 401，如需改進可加 interceptor）。

### UI 設計規範

- 以手機操作為主，max-width 430px（橫式放寬至 700px），iOS 風格設計
- 深色/淺色/系統三段切換；`html.dark` class 控制 CSS 變數
- 所有 mutation 為樂觀更新：先更新 `DATA` → `render()` → 顯示 toast（無整頁重新載入）
- 食物排序規則：到期日最近優先，無到期日的排最後，同到期日按名稱排序
- 到期色碼：紅（已過期或 ≤3 天）、橘（≤7 天）、綠（>7 天）
- 左滑刪除（手機）：刪除鍵以 `position: absolute; right: -76px` 放在 card 內部，跟著 card transform 移動；`overflow: hidden` 保證初始隱藏。電腦版改為 hover 時顯示垃圾桶圖示
- 拖拉排序：≡ handle 同時綁定 `touchstart`（手機）和 `mousedown`（電腦），共用 `_dragStart / _dragMove / _dragEnd` 邏輯，建立 ghost clone，排序結果 POST 到 `/api/locations/reorder`
- 點擊目標：只有 `.item-emoji` 和 `.item-info` 有 `onclick="openEditItem(...)"`，其餘區域（badge、空白）不觸發編輯。手機左滑後 touchend 會 `e.preventDefault()` 阻止 click 事件
- 語音輸入：`recog.continuous = true`，持續錄音直到使用者手動按停止

### 環境變數

| 變數 | 說明 |
|------|------|
| `DATABASE_URL` | Neon PostgreSQL 連線字串。不設定時退回 SQLite（僅限本地開發）。 |
| `SECRET_KEY` | Flask session 金鑰 |
| `PORT` | 伺服器 port（預設 5000；本地建議用 5001） |
| `ADMIN_USERNAME` | 初始 admin 帳號名稱（users 表為空時自動建立） |
| `ADMIN_PASSWORD` | 初始 admin 帳號密碼 |
| `NLP_BACKEND` | `regex`（預設）或 `gemini`（需同時設 `GEMINI_API_KEY`） |
| `GEMINI_API_KEY` | Google AI Studio API Key（從 aistudio.google.com 取得，`AIza` 開頭） |
| `GEMINI_MODEL` | `gemini-2.5-flash`（預設）或 `gemini-2.5-flash-lite`（最省配額） |
