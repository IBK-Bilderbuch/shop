from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ----------------------
# User Modell
# ----------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f"<User {self.email}>"

# ----------------------
# Bestell-Modelle
# ----------------------

class Bestellung(db.Model):
    __tablename__ = "bestellungen"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)

    # ⭐ PERSONENDATEN
    vorname = db.Column(db.String(120))
    nachname = db.Column(db.String(120))
    strasse = db.Column(db.String(200))
    hausnummer = db.Column(db.String(20))
    plz = db.Column(db.String(20))
    stadt = db.Column(db.String(120))
    land = db.Column(db.String(120))
    telefon = db.Column(db.String(50))

    bestelldatum = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    positionen = db.relationship(
        "BestellPosition",
        backref="bestellung",
        cascade="all, delete-orphan"
    )

class BestellPosition(db.Model):
    __tablename__ = "bestellpositionen"

    id = db.Column(db.Integer, primary_key=True)
    bestellung_id = db.Column(db.Integer, db.ForeignKey("bestellungen.id"))
    ean = db.Column(db.String(50))
    bezeichnung = db.Column(db.String(200))
    menge = db.Column(db.Integer)
    preis = db.Column(db.Float)
