import json
import os
from datetime import date, datetime
from functools import wraps

from argon2 import PasswordHasher
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect as sqla_inspect, text

from nlp import parse_food_text, parse_multiple_foods

load_dotenv()

app = Flask(__name__)

db_url = os.environ.get("DATABASE_URL", "sqlite:///food_inventory.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config.update(
    SQLALCHEMY_DATABASE_URI=db_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-key-please-change"),
)
db = SQLAlchemy(app)

_ph = PasswordHasher()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _hash_pw(password: str) -> str:
    return _ph.hash(password)


def _verify_pw(password: str, stored_hash: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except Exception:
        return False


def login_required(f):
    @wraps(f)
    def deco(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return deco


def api_login_required(f):
    @wraps(f)
    def deco(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "請先登入"}), 401
        return f(*args, **kwargs)
    return deco


# ── Ownership helpers ─────────────────────────────────────────────────────────

def _own_location(loc_id: int):
    """Return Location if it belongs to current user, else abort 403."""
    from flask import abort
    loc = Location.query.get_or_404(loc_id)
    if loc.user_id != session["user_id"]:
        abort(403)
    return loc


def _own_item(item_id: int):
    """Return Item if its location belongs to current user, else abort 403."""
    from flask import abort
    item = Item.query.get_or_404(item_id)
    if item.location.user_id != session["user_id"]:
        abort(403)
    return item


# ── Models ────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    nickname      = db.Column(db.String(50), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    locations     = db.relationship("Location", backref="owner", lazy=True,
                                    cascade="all, delete-orphan")


class Location(db.Model):
    __tablename__ = "locations"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name       = db.Column(db.String(100), nullable=False)
    icon       = db.Column(db.String(10), default="📦")
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items      = db.relationship("Item", backref="location", lazy=True,
                                 cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "icon": self.icon, "sort_order": self.sort_order}


class Item(db.Model):
    __tablename__ = "items"
    id            = db.Column(db.Integer, primary_key=True)
    location_id   = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    name          = db.Column(db.String(200), nullable=False)
    emoji         = db.Column(db.String(10), default="🍱")
    quantity      = db.Column(db.Float, default=1)
    unit          = db.Column(db.String(50), default="個")
    purchase_date = db.Column(db.Date)
    expiry_date   = db.Column(db.Date)
    notes         = db.Column(db.Text, default="")
    sort_order    = db.Column(db.Integer, default=0)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id":            self.id,
            "location_id":   self.location_id,
            "name":          self.name,
            "emoji":         self.emoji or "🍱",
            "quantity":      self.quantity,
            "unit":          self.unit,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "expiry_date":   self.expiry_date.isoformat()   if self.expiry_date   else None,
            "notes":         self.notes or "",
            "sort_order":    self.sort_order,
        }


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if "user_id" in session:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = User.query.filter_by(username=username).first()
            if user and _verify_pw(password, user.password_hash):
                session.permanent = True
                session["user_id"] = user.id
                return redirect(url_for("index"))
            error = "帳號或密碼錯誤"
        except Exception:
            error = "伺服器暫時無法連線，請稍後再試"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    uid          = session["user_id"]
    current_user = User.query.get(uid)
    locations    = Location.query.filter_by(user_id=uid).order_by(
                       Location.sort_order, Location.created_at).all()
    data = {"locations": []}
    for loc in locations:
        items = sorted(loc.items, key=lambda i: (i.sort_order, i.id))
        entry = loc.to_dict()
        entry["items"] = [i.to_dict() for i in items]
        data["locations"].append(entry)
    is_gemini = (
        os.environ.get("NLP_BACKEND", "regex").lower() == "gemini"
        and bool(os.environ.get("GEMINI_API_KEY"))
    )
    return render_template(
        "index.html",
        data_json=json.dumps(data, ensure_ascii=False),
        current_username=current_user.username if current_user else "",
        current_nickname=current_user.nickname if current_user else None,
        is_admin=current_user.is_admin if current_user else False,
        is_gemini=is_gemini,
    )


@app.route("/location/<int:loc_id>")
@login_required
def location_view(loc_id):
    loc   = _own_location(loc_id)
    items = Item.query.filter_by(location_id=loc_id).order_by(Item.created_at.desc()).all()
    items = sorted(items, key=lambda i: (
        i.expiry_date is None,
        i.expiry_date or date.max,
        i.name,
    ))
    uid            = session["user_id"]
    all_locations  = Location.query.filter_by(user_id=uid).order_by(Location.name).all()
    items_json     = json.dumps([i.to_dict() for i in items],         ensure_ascii=False)
    locations_json = json.dumps([l.to_dict() for l in all_locations], ensure_ascii=False)
    return render_template(
        "location.html",
        location=loc,
        items_json=items_json,
        locations_json=locations_json,
    )


@app.route("/health")
def health():
    return "OK", 200


@app.route("/sw.js")
def service_worker():
    """Serve Service Worker from root path so its scope covers the whole app."""
    resp = send_from_directory(app.static_folder, "sw.js")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# ── Change own nickname (any user) ───────────────────────────────────────────

@app.route("/api/me/nickname", methods=["PUT"])
@api_login_required
def api_change_nickname():
    me   = User.query.get(session["user_id"])
    data = request.get_json() or {}
    nick = data.get("nickname", "").strip()
    me.nickname = nick or None   # 空字串存 NULL
    db.session.commit()
    return jsonify({"ok": True, "nickname": me.nickname})


# ── Change own password (any user) ───────────────────────────────────────────

@app.route("/api/me/password", methods=["PUT"])
@api_login_required
def api_change_password():
    me   = User.query.get(session["user_id"])
    data = request.get_json() or {}
    cur  = data.get("current_password", "")
    new  = data.get("new_password", "").strip()
    if not cur or not new:
        return jsonify({"error": "請填寫目前密碼和新密碼"}), 400
    if len(new) < 4:
        return jsonify({"error": "新密碼至少需要 4 個字元"}), 400
    if not _verify_pw(cur, me.password_hash):
        return jsonify({"error": "目前密碼不正確"}), 400
    me.password_hash = _hash_pw(new)
    db.session.commit()
    return jsonify({"ok": True})


# ── User management API (admin only) ─────────────────────────────────────────

@app.route("/api/users", methods=["GET", "POST"])
@api_login_required
def api_users():
    me = User.query.get(session["user_id"])
    if not me or not me.is_admin:
        return jsonify({"error": "權限不足"}), 403
    if request.method == "POST":
        data     = request.get_json() or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        if not username or not password:
            return jsonify({"error": "帳號與密碼不能為空"}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({"error": "帳號已存在"}), 409
        user = User(username=username, password_hash=_hash_pw(password))
        db.session.add(user)
        db.session.flush()  # get user.id before commit
        db.session.add_all([
            Location(name="冰箱",  icon="🧊", sort_order=0, user_id=user.id),
            Location(name="冷凍庫", icon="❄️", sort_order=1, user_id=user.id),
            Location(name="乾貨櫃", icon="🗄️", sort_order=2, user_id=user.id),
        ])
        db.session.commit()
        return jsonify({"id": user.id, "username": user.username, "is_admin": user.is_admin}), 201
    users = User.query.order_by(User.created_at).all()
    return jsonify([{"id": u.id, "username": u.username, "is_admin": u.is_admin} for u in users])


@app.route("/api/users/<int:uid>", methods=["DELETE"])
@api_login_required
def api_delete_user(uid):
    me = User.query.get(session["user_id"])
    if not me or not me.is_admin:
        return jsonify({"error": "權限不足"}), 403
    if uid == me.id:
        return jsonify({"error": "不能刪除自己"}), 400
    user = User.query.get_or_404(uid)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"ok": True})


# ── Location API ──────────────────────────────────────────────────────────────

@app.route("/api/locations", methods=["GET", "POST"])
@api_login_required
def api_locations():
    uid = session["user_id"]
    if request.method == "POST":
        data = request.get_json()
        loc  = Location(name=data["name"], icon=data.get("icon", "📦"), user_id=uid)
        db.session.add(loc)
        db.session.commit()
        return jsonify(loc.to_dict()), 201
    return jsonify([l.to_dict() for l in
                    Location.query.filter_by(user_id=uid).order_by(
                        Location.sort_order, Location.created_at).all()])


@app.route("/api/locations/reorder", methods=["POST"])
@api_login_required
def api_locations_reorder():
    uid   = session["user_id"]
    items = request.get_json()
    for item in (items or []):
        loc = Location.query.get(item["id"])
        if loc and loc.user_id == uid:       # only reorder own locations
            loc.sort_order = item["sort_order"]
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/locations/<int:loc_id>", methods=["PUT", "DELETE"])
@api_login_required
def api_location(loc_id):
    loc = _own_location(loc_id)
    if request.method == "DELETE":
        db.session.delete(loc)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json()
    if "name" in data: loc.name = data["name"]
    if "icon" in data: loc.icon = data["icon"]
    db.session.commit()
    return jsonify(loc.to_dict())


# ── Items reorder API ─────────────────────────────────────────────────────────

@app.route("/api/items/reorder", methods=["POST"])
@api_login_required
def api_items_reorder():
    uid     = session["user_id"]
    payload = request.get_json()
    for entry in (payload or []):
        item = Item.query.get(entry["id"])
        if item and item.location.user_id == uid:
            item.sort_order = entry["sort_order"]
    db.session.commit()
    return jsonify({"ok": True})


# ── Recipe API (Gemini) ────────────────────────────────────────────────────────

@app.route("/api/recipe", methods=["POST"])
@api_login_required
def api_recipe():
    uid              = session["user_id"]
    body             = request.get_json() or {}
    user_ingredients = (body.get("ingredients") or "").strip()
    combine          = bool(body.get("combine", True))

    locations = Location.query.filter_by(user_id=uid).all()
    all_items = [i for loc in locations for i in loc.items]

    if not user_ingredients and not all_items:
        return jsonify({"error": "請先新增食物或輸入食材再產生食譜建議"}), 400
    try:
        from gemini_nlp import suggest_recipe, _is_transient
        recipe = suggest_recipe(all_items, user_ingredients, combine)
        return jsonify({"recipe": recipe})
    except Exception as e:
        err_str = str(e)
        if _is_transient(e):
            msg = "Gemini 目前流量過高，請稍後再試 🙏"
        elif '429' in err_str or 'quota' in err_str.lower():
            msg = "Gemini 免費配額已用完，請明天再試"
        else:
            msg = "食譜產生失敗，請稍後再試"
        return jsonify({"error": msg}), 500


# ── Parse API ─────────────────────────────────────────────────────────────────

@app.route("/api/parse", methods=["POST"])
@api_login_required
def api_parse():
    text = (request.get_json() or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "請提供文字"}), 400
    backend = os.environ.get("NLP_BACKEND", "regex").lower()
    try:
        if backend == "gemini" and os.environ.get("GEMINI_API_KEY"):
            try:
                from gemini_nlp import parse_with_gemini
                return jsonify(parse_with_gemini(text))
            except Exception:
                # Gemini failed (429, network error, etc.) — fall back to regex silently
                return jsonify(parse_multiple_foods(text))
        else:
            return jsonify(parse_multiple_foods(text))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Item API ──────────────────────────────────────────────────────────────────

@app.route("/api/items/batch", methods=["POST"])
@api_login_required
def api_items_batch():
    uid        = session["user_id"]
    items_data = request.get_json()
    if not isinstance(items_data, list):
        return jsonify({"error": "Expected a list"}), 400
    # Verify all target locations belong to current user
    for data in items_data:
        loc = Location.query.get(data.get("location_id"))
        if not loc or loc.user_id != uid:
            return jsonify({"error": "無效地點"}), 403
    created = []
    for data in items_data:
        loc_id = data["location_id"]
        max_order = db.session.query(db.func.max(Item.sort_order)).filter_by(location_id=loc_id).scalar() or 0
        item = Item(
            location_id   = loc_id,
            name          = data["name"],
            emoji         = data.get("emoji", "🍱"),
            quantity      = float(data.get("quantity", 1)),
            unit          = data.get("unit", "個"),
            purchase_date = date.fromisoformat(data["purchase_date"]) if data.get("purchase_date") else None,
            expiry_date   = date.fromisoformat(data["expiry_date"])   if data.get("expiry_date")   else None,
            notes         = data.get("notes", ""),
            sort_order    = max_order + len(created) + 1,
        )
        db.session.add(item)
        created.append(item)
    db.session.commit()
    return jsonify([i.to_dict() for i in created]), 201


@app.route("/api/items", methods=["POST"])
@api_login_required
def api_add_item():
    uid  = session["user_id"]
    data = request.get_json()
    loc  = Location.query.get(data.get("location_id"))
    if not loc or loc.user_id != uid:
        return jsonify({"error": "無效地點"}), 403
    max_order = db.session.query(db.func.max(Item.sort_order)).filter_by(location_id=loc.id).scalar() or 0
    item = Item(
        location_id   = data["location_id"],
        name          = data["name"],
        emoji         = data.get("emoji", "🍱"),
        quantity      = float(data.get("quantity", 1)),
        unit          = data.get("unit", "個"),
        purchase_date = date.fromisoformat(data["purchase_date"]) if data.get("purchase_date") else None,
        expiry_date   = date.fromisoformat(data["expiry_date"])   if data.get("expiry_date")   else None,
        notes         = data.get("notes", ""),
        sort_order    = max_order + 1,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@app.route("/api/items/<int:item_id>", methods=["GET", "PUT", "DELETE"])
@api_login_required
def api_item(item_id):
    item = _own_item(item_id)
    if request.method == "GET":
        return jsonify(item.to_dict())
    if request.method == "DELETE":
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json()
    # If moving to a different location, verify it belongs to current user
    if "location_id" in data:
        uid = session["user_id"]
        loc = Location.query.get(data["location_id"])
        if not loc or loc.user_id != uid:
            return jsonify({"error": "無效地點"}), 403
        item.location_id = int(data["location_id"])
    for field in ("name", "emoji", "unit", "notes"):
        if field in data:
            setattr(item, field, data[field])
    if "quantity" in data:
        item.quantity = float(data["quantity"])
    if "purchase_date" in data:
        item.purchase_date = date.fromisoformat(data["purchase_date"]) if data["purchase_date"] else None
    if "expiry_date" in data:
        item.expiry_date = date.fromisoformat(data["expiry_date"]) if data["expiry_date"] else None
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(item.to_dict())


# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

    # ── Legacy migrations ──────────────────────────────────────────────────────

    # items.emoji
    try:
        cols = [c["name"] for c in sqla_inspect(db.engine).get_columns("items")]
        if "emoji" not in cols:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN emoji VARCHAR(10) DEFAULT '🍱'"))
                conn.commit()
    except Exception:
        pass

    # locations.sort_order
    try:
        loc_cols = [c["name"] for c in sqla_inspect(db.engine).get_columns("locations")]
        if "sort_order" not in loc_cols:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE locations ADD COLUMN sort_order INTEGER DEFAULT 0"))
                conn.execute(text("UPDATE locations SET sort_order = id"))
                conn.commit()
    except Exception:
        pass

    # ── locations.user_id (per-user data isolation) ────────────────────────────
    try:
        loc_cols = [c["name"] for c in sqla_inspect(db.engine).get_columns("locations")]
        if "user_id" not in loc_cols:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE locations ADD COLUMN user_id INTEGER"))
                # Assign existing locations to the first admin user
                conn.execute(text(
                    "UPDATE locations SET user_id = "
                    "(SELECT id FROM users ORDER BY id LIMIT 1) "
                    "WHERE user_id IS NULL"
                ))
                conn.commit()
    except Exception:
        pass

    # users.nickname
    try:
        user_cols = [c["name"] for c in sqla_inspect(db.engine).get_columns("users")]
        if "nickname" not in user_cols:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN nickname VARCHAR(50)"))
                conn.commit()
    except Exception:
        pass

    # items.sort_order
    try:
        item_cols2 = [c["name"] for c in sqla_inspect(db.engine).get_columns("items")]
        if "sort_order" not in item_cols2:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN sort_order INTEGER DEFAULT 0"))
                conn.execute(text("UPDATE items SET sort_order = id"))
                conn.commit()
    except Exception:
        pass

    # ── Seed ──────────────────────────────────────────────────────────────────

    # Create initial admin user from env vars (only if users table is empty)
    if User.query.count() == 0:
        admin_user = os.environ.get("ADMIN_USERNAME", "").strip()
        admin_pass = os.environ.get("ADMIN_PASSWORD", "").strip()
        if admin_user and admin_pass:
            db.session.add(User(
                username=admin_user,
                password_hash=_hash_pw(admin_pass),
                is_admin=True,
            ))
            db.session.commit()

    # Seed 3 default locations for any user that has none yet
    for user in User.query.all():
        if Location.query.filter_by(user_id=user.id).count() == 0:
            db.session.add_all([
                Location(name="冰箱",  icon="🧊", sort_order=0, user_id=user.id),
                Location(name="冷凍庫", icon="❄️", sort_order=1, user_id=user.id),
                Location(name="乾貨櫃", icon="🗄️", sort_order=2, user_id=user.id),
            ])
    db.session.commit()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port, host="0.0.0.0")
