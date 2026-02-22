import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

from flask import (
    Flask, render_template, request,
    redirect, flash, abort,
    session, url_for, jsonify
)

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Modelle importieren
from models import db, Bestellung, BestellPosition

# =====================================================
# CONFIG
# =====================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_PERMANENT"] = False


app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY fehlt!")

database_url = os.getenv("DATABASE_URL", "sqlite:///ibk-shop-db.db")
database_url = database_url.replace("postgres://", "postgresql://")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
with app.app_context():
    db.create_all()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

csrf = CSRFProtect(app)

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
# EMAIL
# =====================================================

def send_email(subject, body, recipient):
    if not SENDGRID_API_KEY or not EMAIL_SENDER:
        logger.warning("SendGrid nicht konfiguriert")
        return

    message = Mail(
        from_email=EMAIL_SENDER,
        to_emails=recipient,
        subject=subject,
        plain_text_content=body
    )

    sg = SendGridAPIClient(SENDGRID_API_KEY)
    sg.send(message)

# =====================================================
# HILFSFUNKTIONEN
# =====================================================

def get_cart():
    return session.get("cart", [])

def save_cart(cart):
    session["cart"] = cart
    session.modified = True

def calculate_total(cart):
    return sum(item["price"] * item["quantity"] for item in cart)

# =====================================================
# ROUTES
# =====================================================

# Admin Test
@app.route("/admin-test")
def admin_test():
    alle = Bestellung.query.all()
    return {"anzahl_bestellungen": len(alle)}

# Homepage
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

# Produkt Detail
@app.route("/produkt/<int:produkt_id>")
def produkt_detail(produkt_id):
    produkt = next((p for p in produkte if p["id"] == produkt_id), None)
    if not produkt:
        abort(404)
    return render_template("produkt.html", produkt=produkt, user_email=session.get("user_email"))

# Admin Bestellungen anzeigen
@app.route("/admin/bestellungen")
def admin_bestellungen():
    alle = Bestellung.query.order_by(Bestellung.bestelldatum.desc()).all()
    return render_template("admin_bestellungen.html", bestellungen=alle)



# ============================
# CART ROUTES
# ============================

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    produkt_id = int(request.form.get("produkt_id"))
    produkt = next((p for p in produkte if p["id"] == produkt_id), None)
    if not produkt:
        abort(404)

    cart = get_cart()
    for item in cart:
        if item["id"] == produkt_id:
            item["quantity"] += 1
            save_cart(cart)
            return redirect(url_for("cart"))

    cart.append({
        "id": produkt["id"],
        "title": produkt["name"],
        "price": float(produkt.get("preis", 0)),
        "quantity": 1
    })
    save_cart(cart)
    return redirect(url_for("cart"))

@app.route("/cart")
def cart():
    cart_items = get_cart()
    total = calculate_total(cart_items)
    return render_template("cart.html", cart_items=cart_items, total=total)

@app.route("/remove-from-cart/<int:produkt_id>")
def remove_from_cart(produkt_id):
    cart = get_cart()
    cart = [item for item in cart if item["id"] != produkt_id]
    save_cart(cart)
    return redirect(url_for("cart"))

# ============================
# CHECKOUT
# ============================

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart_items = get_cart()
    total = calculate_total(cart_items)

    # DEBUG
    print("METHOD:", request.method)
    print("FORM:", request.form)
    print("CART:", cart_items)

    if request.method == "POST":
        email = request.form.get("email")
        print("EMAIL:", email)

        if not email or not cart_items:
            flash("Bitte gültige Daten eingeben.", "error")
            return redirect(url_for("checkout"))

        try:
            bestellung = Bestellung(email=email)
            db.session.add(bestellung)
            db.session.flush()

            for item in cart_items:
                db.session.add(
                    BestellPosition(
                        bestellung_id=bestellung.id,
                        bezeichnung=item["title"],
                        menge=item["quantity"],
                        preis=item["price"]
                    )
                )

            db.session.commit()
            session["cart"] = []
            flash("Bestellung erfolgreich!", "success")
            return redirect(url_for("bestelldanke"))

        except Exception as e:
            db.session.rollback()
            print("DATABASE ERROR:", e)
            flash(f"Fehler: {e}", "error")

    return render_template("checkout.html", cart_items=cart_items, total=total)

# ============================
# KONTAKT
# ============================

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
        send_email(
            subject=f"Neue Nachricht von {name}",
            body=f"Von: {name} <{email}>\n\nNachricht:\n{message}",
            recipient=EMAIL_SENDER
        )
        flash("Danke! Deine Nachricht wurde gesendet.", "success")
    except Exception as e:
        flash(f"Fehler beim Senden: {e}", "error")
    return redirect("/kontaktdanke")

# ============================
# NEWSLETTER
# ============================

@app.route("/newsletter", methods=["POST"])
def newsletter():
    email = request.form.get("email")
    if not email:
        flash("Bitte gib eine gültige E-Mail-Adresse ein.", "error")
        return redirect("/")
    try:
        send_email(
            subject="Neue Newsletter-Anmeldung",
            body=f"Neue Anmeldung: {email}",
            recipient=EMAIL_SENDER
        )
        flash("Danke! Newsletter-Anmeldung erfolgreich.", "success")
    except Exception as e:
        flash(f"Fehler beim Newsletter-Versand: {e}", "error")
    return redirect("/danke")

# ============================
# RECHTLICHES
# ============================

@app.route("/rechtliches")
def rechtliches():
    return render_template("rechtliches.html", user_email=session.get("user_email"))

@app.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html", user_email=session.get("user_email"))

@app.route("/impressum")
def impressum():
    return render_template("impressum.html", user_email=session.get("user_email"))

# ============================
# DANKE SEITEN
# ============================

@app.route("/danke")
def danke():
    return render_template("danke.html", user_email=session.get("user_email"))

@app.route("/kontaktdanke")
def kontaktdanke():
    return render_template("kontaktdanke.html", user_email=session.get("user_email"))

@app.route("/bestelldanke")
def bestelldanke():
    return render_template("bestelldanke.html", user_email=session.get("user_email"))

# =====================================================
# START (RENDER READY)
# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
