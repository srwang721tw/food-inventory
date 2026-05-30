# Food Inventory

A mobile-first web app for tracking household food inventory. Describe newly purchased items in natural Chinese (typed or spoken), and the app automatically parses names, quantities, and expiry dates.

**Production:** https://food-inventory-4ygl.onrender.com

---

## Features

| Feature | Description |
|---------|-------------|
| **Voice / text input** | Speak or type e.g. "三包泡麵一個月後到期" — name, quantity, and expiry are parsed automatically |
| **Batch NLP parsing** | One sentence can describe multiple items; review and edit each before saving |
| **Expiry color coding** | Red (expired / ≤3 days), orange (≤7 days), green (safe), grey (no expiry set) |
| **Swipe to delete** | Swipe an item row left to reveal a delete button; tap once to remove |
| **Drag to reorder** | Long-press the ≡ handle on a location to drag it to a new position |
| **Stats quick-filter** | Tap "已過期" or "快過期" to expand all matching locations; tap again to collapse |
| **Dark / light mode** | Toggle in the top-right corner: system default 🌓 → light ☀️ → dark 🌙 |
| **Responsive layout** | Optimised for portrait and landscape on mobile |

### Supported NLP input patterns

```
一瓶豆漿三天後到期、三包泡麵一個月後到期
雞胸肉500克明天到期還有花椰菜一顆五天後到期
一包水蓮大約兩個禮拜內到期一罐可樂沒有期限
有效期限到2026/7/1
今天買了牛奶放冰箱
```

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12 + Flask 3.1 |
| ORM | Flask-SQLAlchemy 3.1 |
| Database | SQLite (local dev) / PostgreSQL (production) |
| NLP | jieba + regex — local, zero cost, no API calls |
| Voice | Web Speech API (browser-native; Chrome / Edge only) |
| Frontend | Vanilla JS + CSS — no framework, no build step |
| Hosting | Render (web service) + Neon (PostgreSQL) |

---

## Local development

```bash
# Activate the virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the dev server (port 5001)
PORT=5001 python app.py
```

Open http://localhost:5001

---

## Deployment (Render + Neon)

### Neon database

1. Create a project at [neon.tech](https://neon.tech) (region: Singapore)
2. Copy the connection string: `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`

### Render environment variables

Go to your Render service → **Environment** and set:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Neon connection string |
| `SECRET_KEY` | Any random string |

Render redeploys automatically on save. Flask's `db.create_all()` creates all tables on first boot.

---

## API reference

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main page (SSR — full data JSON embedded) |
| `GET / POST /api/locations` | List / create locations |
| `PUT / DELETE /api/locations/<id>` | Update / delete a location |
| `POST /api/locations/reorder` | Persist drag-to-reorder result |
| `POST /api/parse` | NLP parse text → `List[item_dict]` |
| `POST /api/items/batch` | Batch create items |
| `GET / PUT / DELETE /api/items/<id>` | Single item operations |
| `GET /health` | Render health check |
