"""
Einmalig ausführen: python migrate_workshop_passwort.py
Fügt die Spalte verwalter_passwort_hash zur Workshop-Tabelle hinzu.
Sicher mehrfach ausführbar.
"""

from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text(
            "ALTER TABLE workshops ADD COLUMN verwalter_passwort_hash VARCHAR(255)"
        ))
        db.session.commit()
        print("Spalte 'verwalter_passwort_hash' hinzugefügt.")
    except Exception as e:
        db.session.rollback()
        print(f"Spalte evtl. schon vorhanden, übersprungen: {e}")
