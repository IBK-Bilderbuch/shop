"""
Einmalig ausführen: python migrate_workshop_slug.py
Fügt die Slug-Spalte hinzu und befüllt sie für bereits vorhandene Workshops.
Sicher mehrfach ausführbar.
"""

from app import app, slugify
from models import db, Workshop
from sqlalchemy import text

with app.app_context():

    # 1. Spalte hinzufügen
    try:
        db.session.execute(text(
            "ALTER TABLE workshops ADD COLUMN slug VARCHAR(255)"
        ))
        db.session.commit()
        print("Spalte 'slug' hinzugefügt.")
    except Exception as e:
        db.session.rollback()
        print(f"Spalte evtl. schon vorhanden, übersprungen: {e}")

    # 2. Bestehende Workshops ohne Slug befüllen
    workshops_ohne_slug = Workshop.query.filter(
        (Workshop.slug == None) | (Workshop.slug == "")
    ).all()

    for w in workshops_ohne_slug:
        basis_slug = slugify(w.titel)
        slug = basis_slug
        zaehler = 2

        while Workshop.query.filter_by(slug=slug).first():
            slug = f"{basis_slug}-{zaehler}"
            zaehler += 1

        w.slug = slug
        print(f"Slug vergeben: {w.titel} -> {slug}")

    db.session.commit()
    print("Fertig.")
