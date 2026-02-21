import os
import json
import logging
import secrets
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv

from flask import (
    Flask, render_template, request,
    redirect, flash, abort,
    session, url_for, jsonify
)

from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition


# =====================================================
# CONFIG
# =====================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY fehlt!")

database_url = os.getenv("DATABASE_URL", "sqlite:///ibk-shop-db.db")
database_url = database_url.replace("postgres://", "postgresql://")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")

BUCHBUTLER_USER = os.getenv("BUCHBUTLER_USER")
BUCHBUTLER_PASSWORD = os.getenv("BUCHBUTLER_PASSWORD")
BASE_URL = "https://api.buchbutler.de"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================================================
# EXTENSIONS (nur EINMAL!)
# =====================================================

db = SQLAlchemy(app)
csrf = CSRFProtect(app)


# =====================================================
# MODELLE
# =====================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Bestellung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bestelldatum = db.Column(db.DateTime, default=datetime.utcnow)
    email = db.Column(db.String(120))
    status = db.Column(db.String(50), default="offen")

    positionen = db.relationship(
        "BestellPosition",
        backref="bestellung",
        cascade="all, delete-orphan"
    )


class BestellPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bestell_id = db.Column(db.Integer, db.ForeignKey("bestellung.id"))
    ean = db.Column(db.String(20))
    bezeichnung = db.Column(db.String(255))
    menge = db.Column(db.Integer)
    preis = db.Column(db.Float)


class StornoToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bestell_id = db.Column(db.Integer, db.ForeignKey("bestellung.id"))
    token = db.Column(db.String(200))
    created = db.Column(db.DateTime, default=datetime.utcnow)


# =====================================================
# TABELLEN EINMALIG ERSTELLEN
# =====================================================

with app.app_context():
    db.create_all()


# =====================================================
# PRODUKTE LADEN
# =====================================================

basedir = os.path.abspath(os.path.dirname(__file__))
json_path = os.path.join(basedir, "produkte.json")

if os.path.exists(json_path):
    with open(json_path, encoding="utf-8") as f:
        produkte = json.load(f)
else:
    produkte = []


# =====================================================
# EMAIL SERVICE
# =====================================================

def send_email(subject, body, recipient, pdf_bytes=None):
    if not SENDGRID_API_KEY or not EMAIL_SENDER:
        logger.warning("SendGrid nicht konfiguriert")
        return

    message = Mail(
        from_email=EMAIL_SENDER,
        to_emails=recipient,
        subject=subject,
        plain_text_content=body
    )

    if pdf_bytes:
        encoded_file = base64.b64encode(pdf_bytes).decode()
        attachment = Attachment(
            FileContent(encoded_file),
            FileName("Rechnung.pdf"),
            FileType("application/pdf"),
            Disposition("attachment")
        )
        message.attachment = attachment

    sg = SendGridAPIClient(SENDGRID_API_KEY)
    sg.send(message)


# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def index():
    return render_template("index.html", produkte=produkte)


@app.route("/produkt/<int:produkt_id>")
def produkt_detail(produkt_id):
    produkt = next((p for p in produkte if p["id"] == produkt_id), None)
    if not produkt:
        abort(404)
    return render_template("produkt.html", produkt=produkt)


@app.route("/bestellung", methods=["POST"])
def neue_bestellung():
    try:
        data = request.get_json() or {}
        email = data.get("email")

        if not email:
            return jsonify({"success": False, "error": "E-Mail fehlt"}), 400

        bestellung = Bestellung(email=email)
        db.session.add(bestellung)
        db.session.flush()

        for pos in data.get("auftrag_position", []):
            db.session.add(
                BestellPosition(
                    bestell_id=bestellung.id,
                    ean=pos.get("ean"),
                    bezeichnung=pos.get("pos_bezeichnung"),
                    menge=int(pos.get("menge", 1)),
                    preis=float(pos.get("vk_brutto", 0))
                )
            )

        db.session.commit()

        return jsonify({"success": True, "bestellId": bestellung.id})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Bestellfehler: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/bestellungen")
def alle_bestellungen():
    alle = Bestellung.query.all()
    return jsonify([
        {
            "id": b.id,
            "email": b.email,
            "bestelldatum": b.bestelldatum.isoformat()
        }
        for b in alle
    ])


@app.route("/bestellung/<int:bestell_id>")
def bestellung_detail(bestell_id):
    b = Bestellung.query.get_or_404(bestell_id)
    return jsonify({
        "id": b.id,
        "email": b.email,
        "positionen": [
            {
                "ean": p.ean,
                "bezeichnung": p.bezeichnung,
                "menge": p.menge,
                "preis": p.preis
            }
            for p in b.positionen
        ]
    })


@app.route("/bestellung/<int:bestell_id>", methods=["DELETE"])
def bestellung_loeschen(bestell_id):
    b = Bestellung.query.get(bestell_id)
    if not b:
        return jsonify({"success": False}), 404

    db.session.delete(b)
    db.session.commit()
    return jsonify({"success": True})


# =====================================================
# START (wichtig für Render)
# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
