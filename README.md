# PantryAI — 智慧食材庫存管家

> 用語音或自然語言輸入，AI 自動解析食物名稱、數量、到期日，零摩擦管理家庭食材庫存。

**Production：** https://food-inventory-4ygl.onrender.com
**GitHub：** https://github.com/srwang721tw/pantry-ai

---

## 設計理念

- **手機優先**：max-width 430px，iOS 風格設計，支援 PWA 安裝到主畫面
- **零費用**：全部使用免費方案（Render + Neon + Gemini 免費配額），無任何持續費用
- **離線可用**：Service Worker 快取靜態資源，網路中斷時顯示離線頁面
- **AI 輔助**：Gemini 解析自然語言，服務不可用時自動 fallback 到本地 regex，從不中斷操作

---

## Tech Stack

| 層級 | 技術 |
|------|------|
| Backend | Python 3.12 · Flask 3.1 |
| ORM | Flask-SQLAlchemy 3.1 |
| Database | Neon PostgreSQL（production）· SQLite（local dev）|
| AI NLP | Google Gemini 3.1 Flash Lite（免費配額）|
| 本地 NLP | jieba + regex（fallback，零成本）|
| Auth | Argon2 密碼雜湊（argon2-cffi）· Flask session |
| Voice | Web Speech API（瀏覽器原生）|
| Frontend | Vanilla JS + CSS（無框架、無建置步驟）|
| PWA | Web App Manifest + Service Worker |
| Hosting | Render free tier + Neon free tier |

---

## 專案亮點

| 功能 | 說明 |
|------|------|
| **AI 食譜建議** | 根據現有庫存 + 自訂食材，Gemini 推薦簡單台灣家常菜（150 字內）|
| **AI 語意解析** | Gemini 解析自然語言（名稱、數量、日期、地點），失敗自動 fallback 到本地 regex |
| **語音輸入** | 持續語音錄音，說完自動解析，支援 iOS Safari 和 Chrome |
| **批次新增** | 一句話描述多項食物，自動拆分、預覽、可手動修改再加入庫存 |
| **PWA 離線支援** | 可安裝到手機主畫面，Service Worker 快取靜態資源，離線顯示品牌頁面 |
| **多使用者隔離** | 每個帳號有獨立存放地點與食物庫存，資料完全隔離 |
| **到期色碼** | 紅（過期或 ≤3 天）· 橘（≤7 天）· 綠（安全）|
| **左滑刪除** | 手機左滑顯示刪除鍵；電腦 hover 顯示垃圾桶圖示 |
| **拖拉排序** | 長按 ≡ 拖拉存放地點與食物，touch + mouse 雙模式 |
| **下滑收回** | 所有 bottom sheet 可從任意位置向下滑動收回 |
| **暗色模式** | 系統🌓 / 亮☀️ / 暗🌙 三段切換，偏好存於 localStorage |
| **Zero-cost** | 全部使用免費方案，不產生任何持續費用 |

---

## 快速上手（本地開發）

```bash
# 啟用虛擬環境
source .venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 啟動開發伺服器（port 5001 避免與系統衝突）
PORT=5001 python app.py
```

瀏覽器開啟 http://localhost:5001，用環境變數 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登入。

---

## 環境變數

| 變數 | 說明 | 必填 |
|------|------|------|
| `DATABASE_URL` | Neon PostgreSQL 連線字串 | 是（production）|
| `SECRET_KEY` | Flask session 簽署金鑰 | 是 |
| `ADMIN_USERNAME` | 初始 admin 帳號名稱 | 是（首次啟動）|
| `ADMIN_PASSWORD` | 初始 admin 帳號密碼 | 是（首次啟動）|
| `NLP_BACKEND` | `gemini`（建議）或 `regex`（預設）| 否 |
| `GEMINI_API_KEY` | Google AI Studio API Key | `NLP_BACKEND=gemini` 時必填 |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite`（預設）或其他 Gemini 模型 | 否 |
| `FLASK_DEBUG` | `1` 啟用 debug mode（僅本地開發）| 否 |
| `PORT` | 伺服器 port（預設 5000）| 否 |

---

## 部署（Render + Neon）

1. 在 [neon.tech](https://neon.tech) 建立 PostgreSQL 專案（地區：Singapore）
2. 複製連線字串 `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`
3. 在 Render Dashboard → Environment 設定上表環境變數
4. Push 到 GitHub，Render 自動部署

---

## 操作說明

### 新增食物
1. 點右下角 ➕ 按鈕
2. 說出或打入食物描述（例：「三包泡麵一個月後到期」）
3. 點「解析文字」→ 確認預覽 → 「加入庫存」

### 管理帳號（Admin）
- Header 右上角 👥 → 使用者管理
- 可新增 / 刪除帳號（刪除帳號會一併清除該帳號所有資料）

### 修改暱稱 / 密碼（所有使用者）
- Header 右上角 👥 → 使用者管理 → 我的暱稱 / 修改密碼

---

## API 概覽

| 端點 | 方法 | 說明 |
|------|------|------|
| `/login` | GET · POST | 登入頁 |
| `/logout` | GET | 登出 |
| `/api/me/nickname` | PUT | 更新自己的暱稱 |
| `/api/me/password` | PUT | 更新自己的密碼（需驗證舊密碼）|
| `/api/users` | GET · POST | 列出 / 新增使用者（admin）|
| `/api/users/<id>` | DELETE | 刪除使用者（admin）|
| `/api/locations` | GET · POST | 列出 / 新增存放地點 |
| `/api/locations/<id>` | PUT · DELETE | 更新 / 刪除存放地點 |
| `/api/locations/reorder` | POST | 更新排序 |
| `/api/items` | POST | 新增食物 |
| `/api/items/<id>` | GET · PUT · DELETE | 取得 / 更新 / 刪除食物 |
| `/api/items/batch` | POST | 批次新增食物 |
| `/api/items/reorder` | POST | 更新食物排序 |
| `/api/parse` | POST | NLP 解析文字 → item dict 列表 |
| `/api/recipe` | POST | AI 食譜建議（需 `NLP_BACKEND=gemini`）|
| `/health` | GET | Render healthcheck |
