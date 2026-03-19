import os
from PIL import Image

# Ordner mit deinen Bildern
IMAGE_DIR = "static/images"
# Max. Breite/Höhe der Bilder
MAX_SIZE = (800, 800)
# Qualität der WebP-Bilder
QUALITY = 70

def optimize_image(path):
    try:
        img = Image.open(path)
        img.thumbnail(MAX_SIZE)  # Größe anpassen
        new_path = os.path.splitext(path)[0] + ".webp"
        img.save(new_path, "WEBP", quality=QUALITY)
        print(f"[OK] {path} → {new_path}")
        # Optional: Original löschen
        # os.remove(path)
    except Exception as e:
        print(f"[ERROR] {path}: {e}")

def walk_and_optimize(folder):
    for root, _, files in os.walk(folder):
        for file in files:
            if file.lower().endswith((".png", ".jpg", ".jpeg")):
                optimize_image(os.path.join(root, file))

if __name__ == "__main__":
    walk_and_optimize(IMAGE_DIR)
    print("✅ Alle Bilder optimiert!")
