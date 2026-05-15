# sitemap_generator.py
import json
from datetime import date
import xml.etree.ElementTree as ET

BASE_URL = "https://www.ibk-bilderbuch.de"

# ----------------------------
# 1. Statische Seiten
# ----------------------------
STATIC_URLS = [
    ("/", "weekly", "1.0"),
    ("/suche", "weekly", "0.9"),
    ("/kontakt", "monthly", "0.7"),
    ("/produkt", "weekly", "0.9"),
    ("/impressum", "yearly", "0.3"),
    ("/datenschutz", "yearly", "0.3"),
    ("/agb", "yearly", "0.3"),
    ("/widerruf", "yearly", "0.3"),
]

# ----------------------------
# 2. Produkte laden
# ----------------------------
def load_products():
    """Lädt Produkte aus produkte.json"""
    try:
        with open("produkte.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Fehler beim Laden von produkte.json:", e)
        return []

# ----------------------------
# 3. Sitemap XML bauen
# ----------------------------
def build_sitemap_xml():
    """Erstellt das XML-Element der Sitemap"""
    urlset = ET.Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    today = date.today().isoformat()

    # ---- statische Seiten
    for path, freq, priority in STATIC_URLS:
        url = ET.SubElement(urlset, "url")
        ET.SubElement(url, "loc").text = BASE_URL + path
        ET.SubElement(url, "changefreq").text = freq
        ET.SubElement(url, "priority").text = priority

    # ---- Produkte


    products = load_products()
    for p in products:

        prod_id = p.get("id")

        slug = p.get("slug")
        if not slug:
            continue

        url = ET.SubElement(urlset, "url")
        ET.SubElement(url, "loc").text = f"{BASE_URL}/produkt/{prod_id}/{slug}"
        ET.SubElement(url, "changefreq").text = "monthly"
        ET.SubElement(url, "priority").text = "0.8"
        ET.SubElement(url, "lastmod").text = today

    return urlset

# ----------------------------
# 4. Datei speichern
# ----------------------------
def save_sitemap_file(filename="sitemap.xml"):
    tree = ET.ElementTree(build_sitemap_xml())
    tree.write(filename, encoding="utf-8", xml_declaration=True)
    print(f"✔ {filename} erfolgreich erstellt")

# ----------------------------
# 5. Flask Route (optional)
# ----------------------------
def flask_route_example(app):
    """Einbindung für Flask: @app.route('/sitemap.xml')"""
    from flask import Response

    @app.route("/sitemap.xml")
    def sitemap():
        xml = ET.tostring(build_sitemap_xml(), encoding="utf-8", method="xml")
        return Response(xml, mimetype="application/xml")

# ----------------------------
# 6. Direkt ausführen
# ----------------------------
if __name__ == "__main__":
    save_sitemap_file()
