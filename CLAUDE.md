# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Deployment

- **Production:** https://food-inventory-4ygl.onrender.com (Render free tier — **not** Railway, despite `railway.toml` being present)
- **GitHub:** https://github.com/srwang721tw/food-inventory
- Production MUST use `DATABASE_URL` env var pointing to Render PostgreSQL — Render's filesystem is ephemeral and SQLite data is wiped on every redeploy.

## Commands

```bash
# Activate virtualenv (required before running anything)
source .venv/bin/activate

# Run dev server (use port 5001 to avoid conflicts)
PORT=5001 python app.py

# Install dependencies
pip install -r requirements.txt

# Production server (used on Railway)
gunicorn app:app --bind 0.0.0.0:$PORT
```

There are no tests in this project.

**Zero-cost constraint:** The entire system must run at zero ongoing cost. Never suggest paid APIs (Claude API, OpenAI, Google STT, etc.). If NLP needs improvement, extend `nlp.py` with more regex rules.

## Architecture

This is a mobile-first family food inventory web app (家庭共享食物庫存系統). The stack is Flask + SQLAlchemy + vanilla JS with no build step.

### Backend (`app.py`)

Two SQLAlchemy models:
- **`Location`** — a storage place (e.g. 冰箱, 冷凍庫, 乾貨櫃). Has many `Item`s with cascade delete.
- **`Item`** — a food item with name, emoji, quantity, unit, purchase_date, expiry_date, notes, and a FK to Location.

Routes:
- `GET /` — renders `index.html` with all locations+items serialized as `data_json` (a JSON blob injected into the template)
- `GET /location/<id>` — renders `location.html` with items and all locations serialized as separate JSON blobs
- `GET /health` — health check for Railway
- REST API: `GET|POST /api/locations`, `PUT|DELETE /api/locations/<id>`, `GET|PUT|DELETE /api/items/<id>`, `POST /api/items`, `POST /api/items/batch`, `POST /api/parse`

Database: SQLite locally (`instance/food_inventory.db`); PostgreSQL on Railway via `DATABASE_URL` env var. Schema migrations are done inline at startup (currently adds the `emoji` column if missing).

### NLP module (`nlp.py`)

Rule-based Chinese food text parser — no external API, no cost. Uses `jieba` for segmentation and `regex` for date/quantity extraction. Entry points:
- `parse_food_text(text)` → single item dict
- `parse_multiple_foods(text)` → list of item dicts (handles sentences with multiple items via `_split_items`)

Extracted fields: `name`, `quantity`, `unit`, `purchase_date`, `expiry_date`, `location_hint`. Date parsing supports absolute dates (YYYY年M月D日, YYYY/M/D), relative days/weeks/months, and natural phrases (昨天, 下週, 三天後到期, etc.).

### Frontend (templates/)

**`base.html`** — shared CSS design system (CSS variables, sheet/overlay, form, button, toast, emoji grid, voice button components) and shared JS (`toast()`, `showSheet()`, `hideSheet()`). Extended by `location.html`.

**`index.html`** — standalone SPA (does **not** extend `base.html`, has its own inline styles). Renders an accordion list of locations; each accordion row contains item cards. All state lives in a `DATA` object populated from the server-rendered `data_json`. Mutations go through fetch calls to the REST API, then update `DATA` in place and call `render()`. Sheets (bottom drawers) handle add/edit/delete for items and locations.

**`location.html`** — legacy per-location detail view (extends `base.html`). Currently unused — the accordion SPA in `index.html` replaced it. Keep but don't maintain.

### NLP pitfalls

- **Pattern ordering in `nlp.py`:** Regex patterns are tried first-match-wins. Prefixed patterns (`保存N週`, `可以放N天`) MUST come before their bare equivalents (`N週`, `N天`). If a general pattern fires first, it only masks the number+unit and leaves the prefix (e.g., "保存") unmasked, which bleeds into the extracted food name.
- **`_split_items()` connector guard:** The `還有`/`另外`/`以及` connectors split a sentence into multiple items, but only when the right side is NOT a pure time expression (e.g., "還有五天到期" should NOT split — it's one item's expiry, not a second item).

### JS pitfalls

- **Dangling event listeners:** Removing an HTML element without removing its corresponding `document.querySelector(...).addEventListener(...)` throws `TypeError: Cannot read properties of null` at top-level script scope, silently killing all JS and leaving the page blank/non-interactive. Always search for all JS references before deleting HTML elements.

### UI patterns to preserve

- Mobile-first, max-width 430px, iOS-style aesthetic
- `color-scheme: light` is forced to prevent dark-mode inversion
- All mutations are optimistic: update `DATA` → call `render()` → show toast (no full page reloads)
- Items are always sorted: soonest expiry first, no-expiry items last, then by name
- Status colors: danger (red) = expired or ≤3 days; warn (orange) = ≤7 days; ok (green) = >7 days

### Environment variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL URL (Railway). Falls back to SQLite if absent. |
| `SECRET_KEY` | Flask secret key |
| `PORT` | Server port (default 5000) |
