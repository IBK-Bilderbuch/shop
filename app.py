import os
import json
import logging
import secrets
import base64
import requests
from datetime import datetime

from flask import (
    Flask, render_template, request,
    redirect, flash, abort,
    session, url_for, jsonify
)

from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition

# =====================================================
# CONFIG
# =====================================================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY fehlt!")


database_url = os.getenv("DATABASE_URL")
if database_url:
    database_url = database_url.replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///ibk-shop-db.db"


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
csrf = CSRFProtect

@app.before_request
def create_tables():
    db.create_all()



SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")

BUCHBUTLER_USER = os.getenv("BUCHBUTLER_USER")
BUCHBUTLER_PASSWORD = os.getenv("BUCHBUTLER_PASSWORD")
BASE_URL = "https://api.buchbutler.de"

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
        cascade="all, delete"
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
# BUCHBUTLER HELPER
# =====================================================

def to_float(value):
    if not value:
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except:
        return 0.0

def buchbutler_request(endpoint, ean):
    if not BUCHBUTLER_USER or not BUCHBUTLER_PASSWORD:
        return None
    url = f"{BASE_URL}/{endpoint}/"
    params = {
        "username": BUCHBUTLER_USER,
        "passwort": BUCHBUTLER_PASSWORD,
        "ean": ean
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("response")
    except Exception:
        logger.exception("Buchbutler Fehler")
        return None

def lade_bestand_von_api(ean):
    res = buchbutler_request("MOVEMENT", ean)
    if not res:
        return None
    if isinstance(res, list) and len(res) > 0:
        res = res[0]
    return {
        "preis": to_float(res.get("Preis")),
        "bestand": res.get("Bestand"),
        "erfuellungsrate": res.get("Erfuellungsrate"),
        "handling_zeit": res.get("Handling_Zeit_in_Werktagen")
    }

def lade_produkt_von_api(ean):
    res = buchbutler_request("CONTENT", ean)
    if not res:
        return None
    attrs = res.get("Artikelattribute") or {}
    return {
        "id": res.get("pim_artikel_id"),
        "name": res.get("bezeichnung"),
        "autor": (attrs.get("Autor") or {}).get("Wert", ""),
        "preis": to_float(res.get("vk_brutto")),
        "isbn": (attrs.get("ISBN_13") or {}).get("Wert", ""),
        "seiten": (attrs.get("Seiten") or {}).get("Wert", ""),
        "format": (attrs.get("Buchtyp") or {}).get("Wert", ""),
        "sprache": (attrs.get("Sprache") or {}).get("Wert", ""),
        "verlag": (attrs.get("Verlag") or {}).get("Wert", ""),
        "erscheinungsjahr": (attrs.get("Erscheinungsjahr") or {}).get("Wert", ""),
        "erscheinungsdatum": (attrs.get("Erscheinungsdatum") or {}).get("Wert", ""),
        "alter_von": (attrs.get("Altersempfehlung_von") or {}).get("Wert", ""),
        "alter_bis": (attrs.get("Altersempfehlung_bis") or {}).get("Wert", ""),
        "lesealter": (attrs.get("Lesealter") or {}).get("Wert", ""),
        "gewicht": (attrs.get("Gewicht") or {}).get("Wert", ""),
        "laenge": (attrs.get("Laenge") or {}).get("Wert", ""),
        "breite": (attrs.get("Breite") or {}).get("Wert", ""),
        "hoehe": (attrs.get("Hoehe") or {}).get("Wert", ""),
        "extra": attrs
    }

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
# STORNO TOKEN
# =====================================================

def generate_cancel_token(bestell_id):
    token = secrets.token_urlsafe(32)
    db.session.add(StornoToken(bestell_id=bestell_id, token=token))
    db.session.commit()
    return token

# =====================================================
# ROUTES
# =====================================================

# ---------- Homepage ----------
@app.route("/")
def index():
    kategorienamen = [
        "Jacominus Gainsborough", "Mut oder Angst?!",
        "Klassiker", "Monstergeschichten",
        "Wichtige Fragen", "Weihnachten",
        "Kinder und Gefühle", "Dazugehören"
    ]
    kategorien = [(k, [p for p in produkte if p.get("kategorie") == k]) for k in kategorienamen]
    return render_template("index.html", kategorien=kategorien, user_email=session.get("user_email"))

# ---------- Produkt ----------
@app.route("/produkt/<int:produkt_id>")
def produkt_detail(produkt_id):
    produkt = next((p for p in produkte if p["id"] == produkt_id), None)
    if not produkt:
        abort(404)
    if produkt.get("ean"):
        api_produkt = lade_produkt_von_api(produkt["ean"])
        if api_produkt:
            produkt.update(api_produkt)
        movement = lade_bestand_von_api(produkt["ean"])
        if movement:
            produkt.update(movement)
    produkt.setdefault("bestand", "n/a")
    produkt.setdefault("preis", 0)
    produkt.setdefault("handling_zeit", "n/a")
    produkt.setdefault("erfuellungsrate", "n/a")
    return render_template("produkt.html", produkt=produkt, user_email=session.get("user_email"))

# ---------- Bestellung ----------
@csrf.exempt
@app.route("/bestellung", methods=["POST"])
def neue_bestellung():


    data = request.get_json() or {}
    data = request.get_json() or {}
    liefer = data.get("lieferadresse", {})
    email = data.get("email")
    if not email:
        return jsonify({"success": False, "error": "E-Mail fehlt"}), 400
    bestellung = Bestellung(email=email)
    db.session.add(bestellung)
    db.session.flush()
    for pos in data.get("auftrag_position", []):
        ean = pos.get("ean")
        menge = int(pos.get("menge", 1))
        movement = lade_bestand_von_api(ean)
        if not movement:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Produkt {ean} nicht verfügbar"}), 400
        preis = movement["preis"]
        db.session.add(BestellPosition(
            bestell_id=bestellung.id,
            ean=ean,
            bezeichnung=pos.get("pos_bezeichnung"),
            menge=menge,
            preis=preis
        ))
    db.session.commit()
    token = generate_cancel_token(bestellung.id)
    try:
        send_email(
            subject="Ihre Bestellung",
            body=f"Vielen Dank für Ihre Bestellung!\nBestellnummer: {bestellung.id}\nStornieren: https://deinedomain.de/storno/{token}",
            recipient=email
        )
    except Exception as e:
        logger.error(f"Bestellmail Fehler: {e}")
    return jsonify({"success": True, "bestellId": bestellung.id})

# ---------- Alle Bestellungen ----------
@app.route("/bestellungen")
def alle_bestellungen():
    alle = Bestellung.query.all()
    result = [ {"id": b.id, "email": b.email, "bestelldatum": b.bestelldatum.isoformat()} for b in alle ]
    return jsonify(result)

# ---------- Bestellung Detail ----------
@app.route("/bestellung/<int:bestell_id>")
def bestellung_detail(bestell_id):
    b = Bestellung.query.get_or_404(bestell_id)
    pos = BestellPosition.query.filter_by(bestell_id=bestell_id).all()
    return jsonify({
        "bestellung": {"id": b.id, "email": b.email, "bestelldatum": b.bestelldatum.isoformat()},
        "positionen": [{"ean": p.ean, "bezeichnung": p.bezeichnung, "menge": p.menge, "preis": p.preis} for p in pos]
    })

# ---------- Bestellung löschen ----------
@app.route("/bestellung/<int:bestell_id>", methods=["DELETE"])
def bestellung_loeschen(bestell_id):
    b = Bestellung.query.get(bestell_id)
    if not b:
        return jsonify({"success": False, "error": "Nicht gefunden"}), 404
    db.session.delete(b)
    db.session.commit()
    return jsonify({"success": True})

# ---------- Kontakt ----------
@app.route("/kontakt")
def kontakt():
    return render_template("kontakt.html", user_email=session.get("user_email"))

@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name")
    email = request.form.get("email")
    message = request.form.get("message")
    if not name or not email or not message:
        flash("Bitte fülle alle Felder aus!", "error")
        return redirect("/kontakt")
    try:
        send_email(subject=f"Neue Nachricht von {name}", body=f"Von: {name} <{email}>\n\nNachricht:\n{message}", recipient=EMAIL_SENDER)
        flash("Danke! Deine Nachricht wurde gesendet.", "success")
    except Exception as e:
        flash(f"Fehler beim Senden: {e}", "error")
    return redirect("/kontaktdanke")

# ---------- Newsletter ----------
@app.route("/newsletter", methods=["POST"])
def newsletter():
    email = request.form.get("email")
    if not email:
        flash("Bitte gib eine gültige E-Mail-Adresse ein.", "error")
        return redirect("/")
    try:
        send_email(subject="Neue Newsletter-Anmeldung", body=f"Neue Anmeldung: {email}", recipient=EMAIL_SENDER)
        flash("Danke! Newsletter-Anmeldung erfolgreich.", "success")
    except Exception as e:
        flash(f"Fehler beim Newsletter-Versand: {e}", "error")
    return redirect("/danke")

# ---------- Checkout ----------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        payment_method = request.form.get("payment-method")

        if not name or not email:
            flash("Bitte Pflichtfelder ausfüllen.", "error")
            return redirect(url_for("checkout"))

        # ✅ Bestellung speichern
        bestellung = Bestellung(email=email)
        db.session.add(bestellung)
        db.session.commit()

        flash(f"Bestellung gespeichert! Nr: {bestellung.id}", "success")
        return redirect(url_for("bestelldanke"))

    return render_template(
        "checkout.html",
        user_email=session.get("user_email")
    )

# ---------- Dankeseiten ----------
@app.route("/danke")
def danke():
    return render_template("danke.html", user_email=session.get("user_email"))

@app.route("/kontaktdanke")
def kontaktdanke():
    return render_template("kontaktdanke.html", user_email=session.get("user_email"))

@app.route("/bestelldanke")
def bestelldanke():
    return render_template("bestelldanke.html", user_email=session.get("user_email"))

# ---------- Warenkorb ----------
@app.route("/cart")
def cart():
    cart_items = [{'title': 'Reife Blessuren | Danilo Lučić', 'price': 23.90, 'quantity': 1}]
    total = sum(item["price"] * item["quantity"] for item in cart_items)
    return render_template("cart.html", cart_items=cart_items, total=total, user_email=session.get("user_email"))

# ---------- Rechtliches ----------
@app.route("/rechtliches")
def rechtliches():
    return render_template("rechtliches.html", user_email=session.get("user_email"))

@app.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html", user_email=session.get("user_email"))

@app.route("/impressum")
def impressum():
    return render_template("impressum.html", user_email=session.get("user_email"))

# ---------- Cronjob ----------
@app.route("/cron")
def cron():
    logger.info("Cronjob wurde ausgelöst")
    return "OK"

# =====================================================
# START
# =====================================================

if __name__ == "__main__":
    app.run()
