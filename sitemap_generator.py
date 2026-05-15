import json
from datetime import date
from xml.etree.ElementTree import Element, SubElement, ElementTree

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
    try:
        with open("produkte.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Fehler beim Laden von produkte.json:", e)
        return []

# ----------------------------
# 3. Sitemap bauen
# ----------------------------
def build_sitemap():
    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    today = date.today().isoformat()

    # ---- statische Seiten
    for path, freq, priority in STATIC_URLS:
        url = SubElement(urlset, "url")
        SubElement(url, "loc").text = BASE_URL + path
        SubElement(url, "changefreq").text = freq
        SubElement(url, "priority").text = priority

    # ---- Produkte
    products = load_products()

    for p in products:
        # erwartet: p["slug"] oder p["url"]
        slug = p.get("slug") or p.get("id") or None

        if not slug:
            continue

        url = SubElement(urlset, "url")
        SubElement(url, "loc").text = f"{BASE_URL}/produkt/{slug}"
        SubElement(url, "changefreq").text = "monthly"
        SubElement(url, "priority").text = "0.8"
        SubElement(url, "lastmod").text = today

    # ---- schreiben
    tree = ElementTree(urlset)
    tree.write("sitemap.xml", encoding="utf-8", xml_declaration=True)

    print("✔ sitemap.xml erfolgreich erstellt")

# ----------------------------
# 4. Start
# ----------------------------
if __name__ == "__main__":
    build_sitemap()
