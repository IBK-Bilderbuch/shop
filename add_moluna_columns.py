from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("""
            ALTER TABLE bestellungen
            ADD COLUMN moluna_status VARCHAR(50),
            ADD COLUMN moluna_order_id VARCHAR(100),
            ADD COLUMN trackingnummer VARCHAR(100);
        """))
        db.session.commit()
        print("✅ Moluna-Spalten wurden hinzugefügt!")
    except Exception as e:
        print("⚠️ Fehler:", e)
