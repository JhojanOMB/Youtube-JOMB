# create_sample_icon.py
from pathlib import Path
from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "iconos"
ICON_DIR.mkdir(parents=True, exist_ok=True)

path = ICON_DIR / "configuracion.png"
size = 64
img = Image.new("RGBA", (size, size), (60,65,80,255))
d = ImageDraw.Draw(img)
d.ellipse((6,6,size-6,size-6), fill=(91,121,255,255))
tri = [(size*0.35, size*0.28), (size*0.35, size*0.72), (size*0.72, size*0.5)]
d.polygon(tri, fill=(255,255,255,230))
img.save(path)
print("Creado icono de prueba en:", path)
