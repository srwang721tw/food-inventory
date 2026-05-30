# 🏠 王李夫妻共享食物庫存系統

家庭食物庫存管理 App，用口語描述剛買的食物，自動解析並追蹤到期日。

**Production：** https://food-inventory-4ygl.onrender.com

---

## 功能

| 功能 | 說明 |
|------|------|
| **語音 / 文字輸入** | 說出或打入「三包泡麵一個月後到期」，自動解析名稱、數量、到期日 |
| **批次 NLP 解析** | 一句話可同時描述多項食物，解析後可手動調整再確認 |
| **到期色碼** | 紅（已過期 / ≤3天）、橘（≤7天）、綠（安全）、灰（無到期日） |
| **左滑刪除** | 對食物列左滑，右側出現刪除鍵，直接點擊刪除 |
| **拖拉排序** | 長按地點左側 ≡ 拖拉調整存放地點順序 |
| **統計快篩** | 點上方「已過期」或「快過期」自動展開相關地點；再點一次收折 |
| **深色模式** | 右上角按鈕循環切換：跟隨系統 🌓 → 淺色 ☀️ → 深色 🌙 |
| **RWD** | 直式 / 橫式自適應，以手機操作為主 |

### NLP 支援的輸入格式

```
一瓶豆漿三天後到期、三包泡麵一個月後到期
雞胸肉500克明天到期還有花椰菜一顆五天後到期
一包水蓮大約兩個禮拜內到期一罐可樂沒有期限
有效期限到2026/7/1
今天買了牛奶放冰箱
```

---

## 技術棧

| 層次 | 選擇 |
|------|------|
| 後端 | Python 3.12 + Flask 3.1 |
| ORM | Flask-SQLAlchemy 3.1 |
| 資料庫 | SQLite（本地）/ PostgreSQL（生產） |
| NLP | jieba + regex（本地，零費用，無 API 呼叫） |
| 語音辨識 | Web Speech API（瀏覽器原生，Chrome / Edge） |
| 前端 | Vanilla JS + CSS（無框架，無建置步驟） |
| 部署 | Render（Web Service + Neon PostgreSQL） |

---

## 本地開發

```bash
# 1. 啟動虛擬環境
source .venv/bin/activate

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 啟動伺服器（port 5001 避免與系統服務衝突）
PORT=5001 python app.py
```

開啟 http://localhost:5001

---

## 部署（Render + Neon）

### Neon 資料庫

1. 前往 [neon.tech](https://neon.tech) 建立 Project（Region: Singapore）
2. 複製 Connection String：`postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`

### Render

1. 進入 Service → **Environment**
2. 設定以下環境變數：

| 變數 | 值 |
|------|----|
| `DATABASE_URL` | Neon Connection String |
| `SECRET_KEY` | 任意隨機字串 |

3. 儲存後 Render 自動重新部署；Flask 啟動時自動建立所有 table。

---

## API

| Endpoint | 說明 |
|----------|------|
| `GET /` | 主頁面（SSR，含完整資料 JSON） |
| `GET/POST /api/locations` | 取得 / 新增地點 |
| `PUT/DELETE /api/locations/<id>` | 編輯 / 刪除地點 |
| `POST /api/locations/reorder` | 儲存地點排序 |
| `POST /api/parse` | NLP 解析文字 → `List[item_dict]` |
| `POST /api/items/batch` | 批次新增食物 |
| `GET/PUT/DELETE /api/items/<id>` | 單筆食物操作 |
| `GET /health` | Render healthcheck |
