
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
import requests

from flask import (
    Flask, render_template, request,
    redirect, flash, abort,
    session, url_for, jsonify
)

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Modelle importieren
from models import db, Bestellung, BestellPosition, Produkt


from datetime import timedelta

from functools import lru_cache


# =====================================================
# CONFIG
# =====================================================

load_dotenv()

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=1)
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_PERMANENT"] = False




app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError("FLASK_SECRET_KEY fehlt!")

database_url = os.getenv("DATABASE_URL", "sqlite:///ibk-shop-db.db")
database_url = database_url.replace("postgres://", "postgresql://")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False





ADMIN_PASSWORD = os.getenv("FLASK_ADMIN_PASSWORD")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

csrf = CSRFProtect(app)



# ---------- BUCHBUTLER API ZUGANG ----------



BUCHBUTLER_USER = os.getenv("BUCHBUTLER_USER")
BUCHBUTLER_PASSWORD = os.getenv("BUCHBUTLER_PASSWORD")

BASE_URL = "https://api.buchbutler.de"




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
    try:
            sg.send(message)
    except Exception:
            logger.exception("Email Versand fehlgeschlagen")
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


def check_auth():
    if not BUCHBUTLER_USER or not BUCHBUTLER_PASSWORD:
        logger.error("Buchbutler Zugangsdaten fehlen")
        return False
    return True


def to_float(value):
    """Konvertiert API Preis sicher"""
    if not value:
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def to_int(value):
    """Konvertiert Zahlen sicher"""
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def attr(attrs, key):
    """Greift sicher auf Artikelattribute zu"""
    return (attrs.get(key) or {}).get("Wert", "")

def buchbutler_request(endpoint, ean):
    """Allgemeine Request Funktion"""
    url = f"{BASE_URL}/{endpoint}/"

    params = {
        "username": BUCHBUTLER_USER,
        "passwort": BUCHBUTLER_PASSWORD,
        "ean": ean
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if not data or "response" not in data:
        return None

    return data["response"]
# -----------------------------
# CONTENT API
# -----------------------------

@lru_cache(maxsize=128)
def cached_lade_produkt_von_api(ean):
    return lade_produkt_von_api(ean)

def lade_produkt_von_api(ean):
    """Lädt Produktdaten von CONTENT API"""

    if not check_auth():
        return None

    try:
        res = buchbutler_request("CONTENT", ean)

        if not res:
            return None

        attrs = res.get("Artikelattribute") or {}

        produkt = {
            "id": to_int(res.get("pim_artikel_id")),
            "name": res.get("bezeichnung"),
            "autor": attr(attrs, "Autor"),
            "preis": to_float(res.get("vk_brutto")),
           
            "isbn": attr(attrs, "ISBN_13"),
            "seiten": attr(attrs, "Seiten"),
            "format": attr(attrs, "Buchtyp"),
            "sprache": attr(attrs, "Sprache"),
            "verlag": attr(attrs, "Verlag"),
            "erscheinungsjahr": attr(attrs, "Erscheinungsjahr"),
            "erscheinungsdatum": attr(attrs, "Erscheinungsdatum"),
            "alter_von": attr(attrs, "Altersempfehlung_von"),
            "alter_bis": attr(attrs, "Altersempfehlung_bis"),
            "lesealter": attr(attrs, "Lesealter"),
            "gewicht": attr(attrs, "Gewicht"),
            "laenge": attr(attrs, "Laenge"),
            "breite": attr(attrs, "Breite"),
            "hoehe": attr(attrs, "Hoehe"),
            "extra": attrs
        }

        return produkt

    except Exception:
        logger.exception("Fehler beim Laden von CONTENT API")
        return None

# -----------------------------
# MOVEMENT API
# -----------------------------

def lade_bestand_von_api(ean):
    """Lädt Bestand / Preis / Lieferdaten"""

    if not check_auth():
        return None

    try:
        res = buchbutler_request("MOVEMENT", ean)

        if not res:
            return None

        # 🔥 FIX — falls Liste zurückkommt
        if isinstance(res, list):
            if len(res) == 0:
                return None
            res = res[0]

        return {
            "bestand": to_int(res.get("Bestand")),
            "preis": to_float(res.get("Preis")),
            "erfuellungsrate": res.get("Erfuellungsrate"),
            "handling_zeit": res.get("Handling_Zeit_in_Werktagen")

        }


    except Exception:
        logger.exception("Fehler beim Laden von MOVEMENT API")
        return None



# =====================================================
# ROUTES
# =====================================================

# Admin Test
@app.route("/admin-test")
def admin_test():
    alle = Bestellung.query.all()
    return {"anzahl_bestellungen": len(alle)}



def admin_required():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return None



@limiter.limit("5 per minute")
@app.route("/ibk-control-8471", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password")
        if pw == ADMIN_PASSWORD:
            session.clear()
            session["admin"] = True
            session.permanent = True
            return redirect("/admin/bestellungen")
        else:
            flash("Falsches Passwort!", "error")
    return render_template("admin_login.html")



# Admin Bestellungen anzeigen
@app.route("/admin/bestellungen")
def admin_bestellungen():
    resp = admin_required()
    if resp:  # wenn redirect zurückkommt
        return resp
    alle = Bestellung.query.order_by(Bestellung.bestelldatum.desc()).all()
    return render_template("admin_bestellungen.html", bestellungen=alle)
    
# Homepage
@app.route("/")
def index():

    kategorienamen = [
        "Jacominus Gainsborough",
        "Mut oder Angst?!",
        "Klassiker",
        "Monstergeschichten",
        "Wichtige Fragen",
        "Weihnachten",
        "Kinder und Gefühle",
        "Dazugehören"
    ]

    kategorien = []

    for k in kategorienamen:
        liste = Produkt.query.filter_by(kategorie=k).all()
        kategorien.append((k, liste))

    return render_template(
        "index.html",
        kategorien=kategorien,
        user_email=session.get("user_email")
    )



@app.route("/admin/sync-buchbutler")
def sync_buchbutler():

    if not session.get("admin"):
        abort(403)

    produkte = Produkt.query.all()

    for produkt in produkte:

        api = lade_produkt_von_api(produkt.ean)
        movement = lade_bestand_von_api(produkt.ean)

        if api:
            produkt.name = api.get("name")
            produkt.autor = api.get("autor")

        if movement:
            produkt.preis = movement.get("preis")

    db.session.commit()

    return "✅ Sync komplett"

   
    
# suche icon 
@app.route("/suche", methods=["GET", "POST"])
def suche():

    query = ""
    ergebnisse = []

    if request.method == "POST":
        query = request.form.get("q", "").lower()

        ergebnisse = Produkt.query.filter(
            Produkt.name.ilike(f"%{query}%")
        ).all()

    return render_template(
        "suche.html",
        query=query,
        ergebnisse=ergebnisse
    )
# Produkt Detail

  

@app.route('/produkt/<int:produkt_id>')
def produkt_detail(produkt_id):

    produkt = Produkt.query.get_or_404(produkt_id)

    api = cached_lade_produkt_von_api(produkt.ean)
    movement = lade_bestand_von_api(produkt.ean)

    produkt_daten = {
        "id": produkt.id,
        "ean": produkt.ean,
        "name": produkt.name,
        "autor": produkt.autor,
        "preis": produkt.preis,
        "kategorie": produkt.kategorie
    }

    if api:
        produkt_daten.update(api)

    if movement:
        produkt_daten.update(movement)

    return render_template(
        "produkt.html",
        produkt=produkt_daten,
        user_email=session.get("user_email")
    )


def import_json_in_db():

    json_path = os.path.join(os.path.dirname(__file__), "produkte.json")

    if not os.path.exists(json_path):
        print("Keine JSON gefunden")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        produkte = json.load(f)

    for p in produkte:

        if not p.get("ean"):
            continue

        existiert = Produkt.query.filter_by(ean=p["ean"]).first()

        if existiert:
            # Update bestehendes Produkt
            existiert.name = p.get("name")
            existiert.autor = p.get("autor")
            existiert.preis = p.get("preis")
            existiert.kategorie = p.get("kategorie")

        else:
            neu = Produkt(
                ean=p["ean"],
                name=p.get("name"),
                autor=p.get("autor"),
                preis=p.get("preis"),
                kategorie=p.get("kategorie"),
            )
            db.session.add(neu)

    db.session.commit()
    print("JSON erfolgreich in DB synchronisiert")
# ============================
# CART ROUTES
# ============================

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():

    produkt_id = int(request.form.get("produkt_id"))

    produkt = Produkt.query.get_or_404(produkt_id)

    # Live Preis + Bestand holen
    preis = produkt.preis

    if produkt.ean:
        movement = lade_bestand_von_api(produkt.ean)
        if movement and movement.get("preis"):
            preis = movement["preis"]

    cart = get_cart()

    found = False
    for item in cart:
        if item["id"] == produkt.id:
            item["quantity"] += 1
            found = True
            break

    if not found:
        cart.append({
            "id": produkt.id,
            "title": produkt.name,
            "price": preis,
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


@app.route("/sync-cart", methods=["POST"])
@csrf.exempt  
def sync_cart():
    data = request.get_json()

    if not data:
        return {"status": "error"}, 400

    session["cart"] = data
    session.modified = True

    print("SYNCED CART:", session["cart"])

    return {"status": "ok"}
    
# ============================
# CHECKOUT
# ============================

    
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart_items = get_cart()
    total = calculate_total(cart_items)

    logger.info("Checkout gestartet")

    if request.method == "POST":

        email = request.form.get("email")

        if not email or not cart_items:
            flash("Bitte gültige Daten eingeben.", "error")
            return redirect(url_for("checkout"))

        try:
            # Bestellung anlegen
            bestellung = Bestellung(
                email=email,
                vorname=request.form.get("vorname"),
                nachname=request.form.get("nachname"),
                strasse=request.form.get("strasse"),
                hausnummer=request.form.get("hausnummer"),
                plz=request.form.get("plz"),
                stadt=request.form.get("stadt"),
                land=request.form.get("land"),
                adresszusatz=request.form.get("adresszusatz"),
                telefon=request.form.get("telefon"),
                paymentmethod=request.form.get("paymentmethod"),
            )
            db.session.add(bestellung)
            db.session.flush()  # ID verfügbar machen

            # Positionen speichern
            for item in cart_items:
                db.session.add(
                    BestellPosition(
                        bestellung_id=bestellung.id,
                        bezeichnung=item.get("title"),
                        menge=item.get("quantity", 1),
                        preis=item.get("price", 0)
                    )
                )

            # Commit der Bestellung
            db.session.commit()

            # ✅ Warenkorb zuverlässig leeren
            session.pop("cart", None)
            session.modified = True  # <- sehr wichtig!

            flash("Bestellung erfolgreich!", "success")
            return redirect(url_for("bestelldanke"))

        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            flash(f"Fehler: {e}", "error")
            return redirect(url_for("checkout"))

    return render_template(
        "checkout.html",
        cart_items=cart_items,
        total=total
    )
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

with app.app_context():
    db.create_all()
    import_json_in_db()

# =====================================================
# START (RENDER READY)
# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


