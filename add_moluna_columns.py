from app import app, db
from sqlalchemy import text

columns = [
    ("moluna_status", "VARCHAR(50)"),
    ("moluna_order_id", "VARCHAR(100)"),
    ("trackingnummer", "VARCHAR(100)"),
    ("logistiker", "VARCHAR(100)"),
    ("paketart", "VARCHAR(100)"),
    ("eans", "VARCHAR(500)")
]

with app.app_context():
    for name, col_type in columns:
        try:
            db.session.execute(text(f"""
                ALTER TABLE bestellungen
                ADD COLUMN IF NOT EXISTS {name} {col_type};
            """))
            db.session.commit()
            print(f"✅ Spalte '{name}' wurde hinzugefügt (oder existiert bereits).")
        except Exception as e:
            print(f"⚠️ Fehler bei Spalte '{name}':", e)
