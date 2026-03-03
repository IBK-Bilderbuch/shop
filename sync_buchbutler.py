from app import app, db, lade_produkt_von_api, lade_bestand_von_api, Produkt

def sync_all():
    with app.app_context():
        alle_produkte = Produkt.query.all()

        for produkt in alle_produkte:
            ean = produkt.ean
            api = lade_produkt_von_api(ean)
            movement = lade_bestand_von_api(ean)

            if api:
                produkt.name = api.get("name")
                produkt.autor = api.get("autor")
            if movement:
                produkt.preis = movement.get("preis")

            produkt.json_data = api  # optional: alle Attribute speichern

            db.session.add(produkt)

        db.session.commit()
        print("✅ Buchbutler Sync abgeschlossen")

if __name__ == "__main__":
    sync_all()
