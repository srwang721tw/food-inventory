import json
import os
from datetime import date, datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect as sqla_inspect, text

from nlp import parse_food_text

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


# ── Models ────────────────────────────────────────────────────────────────────

class Location(db.Model):
    __tablename__ = "locations"
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    icon       = db.Column(db.String(10), default="📦")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items      = db.relationship("Item", backref="location", lazy=True,
                                 cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "icon": self.icon}


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
        }


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    locations = Location.query.order_by(Location.created_at).all()
    today = date.today()
    cards = []
    for loc in locations:
        its = loc.items
        expired  = sum(1 for i in its if i.expiry_date and i.expiry_date < today)
        expiring = sum(1 for i in its if i.expiry_date and
                       0 <= (i.expiry_date - today).days <= 7)
        cards.append({
            "id":       loc.id,
            "name":     loc.name,
            "icon":     loc.icon,
            "count":    len(its),
            "expired":  expired,
            "expiring": expiring,
        })
    total_items    = sum(c["count"]    for c in cards)
    total_expired  = sum(c["expired"]  for c in cards)
    total_expiring = sum(c["expiring"] for c in cards)
    return render_template("index.html",
                           cards=cards,
                           total_items=total_items,
                           total_expired=total_expired,
                           total_expiring=total_expiring)


@app.route("/location/<int:loc_id>")
def location_view(loc_id):
    loc   = Location.query.get_or_404(loc_id)
    today = date.today()
    items = Item.query.filter_by(location_id=loc_id).order_by(Item.created_at.desc()).all()
    items = sorted(items, key=lambda i: (
        i.expiry_date is None,
        i.expiry_date or date.max,
        i.name,
    ))
    all_locations  = Location.query.order_by(Location.name).all()
    items_json     = json.dumps([i.to_dict() for i in items],      ensure_ascii=False)
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


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/locations", methods=["GET", "POST"])
def api_locations():
    if request.method == "POST":
        data = request.get_json()
        loc  = Location(name=data["name"], icon=data.get("icon", "📦"))
        db.session.add(loc)
        db.session.commit()
        return jsonify(loc.to_dict()), 201
    return jsonify([l.to_dict() for l in Location.query.order_by(Location.created_at).all()])


@app.route("/api/locations/<int:loc_id>", methods=["PUT", "DELETE"])
def api_location(loc_id):
    loc = Location.query.get_or_404(loc_id)
    if request.method == "DELETE":
        db.session.delete(loc)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json()
    if "name" in data: loc.name = data["name"]
    if "icon" in data: loc.icon = data["icon"]
    db.session.commit()
    return jsonify(loc.to_dict())


@app.route("/api/parse", methods=["POST"])
def api_parse():
    text = (request.get_json() or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "請提供文字"}), 400
    try:
        return jsonify(parse_food_text(text))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/items", methods=["POST"])
def api_add_item():
    data = request.get_json()
    item = Item(
        location_id   = data["location_id"],
        name          = data["name"],
        emoji         = data.get("emoji", "🍱"),
        quantity      = float(data.get("quantity", 1)),
        unit          = data.get("unit", "個"),
        purchase_date = date.fromisoformat(data["purchase_date"]) if data.get("purchase_date") else None,
        expiry_date   = date.fromisoformat(data["expiry_date"])   if data.get("expiry_date")   else None,
        notes         = data.get("notes", ""),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@app.route("/api/items/<int:item_id>", methods=["GET", "PUT", "DELETE"])
def api_item(item_id):
    item = Item.query.get_or_404(item_id)
    if request.method == "GET":
        return jsonify(item.to_dict())
    if request.method == "DELETE":
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json()
    for field in ("name", "emoji", "unit", "notes"):
        if field in data:
            setattr(item, field, data[field])
    if "quantity"      in data: item.quantity    = float(data["quantity"])
    if "location_id"   in data: item.location_id = int(data["location_id"])
    if "purchase_date" in data:
        item.purchase_date = date.fromisoformat(data["purchase_date"]) if data["purchase_date"] else None
    if "expiry_date" in data:
        item.expiry_date   = date.fromisoformat(data["expiry_date"])   if data["expiry_date"]   else None
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(item.to_dict())


# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

    # Migrate: add emoji column to existing databases
    try:
        cols = [c["name"] for c in sqla_inspect(db.engine).get_columns("items")]
        if "emoji" not in cols:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN emoji VARCHAR(10) DEFAULT '🍱'"))
                conn.commit()
    except Exception:
        pass

    if Location.query.count() == 0:
        db.session.add_all([
            Location(name="冰箱",  icon="🧊"),
            Location(name="冷凍庫", icon="❄️"),
            Location(name="乾貨櫃", icon="🗄️"),
        ])
        db.session.commit()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port, host="0.0.0.0")
