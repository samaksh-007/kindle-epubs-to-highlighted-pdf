from pathlib import Path

from PIL import Image, ImageDraw


out = Path(__file__).parent / "assets"
out.mkdir(exist_ok=True)

sizes = [16, 24, 32, 48, 64, 128, 256]
images = []
for size in sizes:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    def box(values):
        return tuple(round(v * scale) for v in values)

    draw.ellipse(box((8, 8, 248, 248)), fill="#4658d9")
    draw.polygon([tuple(round(v * scale) for v in p) for p in [(60, 62), (124, 78), (124, 212), (60, 192)]], fill="#ffffff")
    draw.polygon([tuple(round(v * scale) for v in p) for p in [(132, 78), (196, 62), (196, 192), (132, 212)]], fill="#eef2ff")
    draw.line([tuple(round(v * scale) for v in p) for p in [(128, 78), (128, 212)]], fill="#3344b5", width=max(1, round(8 * scale)))
    draw.rectangle(box((72, 126, 116, 144)), fill="#ffd166")
    draw.rectangle(box((140, 112, 184, 130)), fill="#ffd166")
    draw.polygon([tuple(round(v * scale) for v in p) for p in [(172, 42), (208, 42), (208, 102), (190, 84), (172, 102)]], fill="#21b7a8")
    images.append(image)

images[-1].save(out / "kindle_highlights_logo.png")
images[-1].save(out / "kindle_highlights_logo.ico", format="ICO", sizes=[(s, s) for s in sizes])
print(out / "kindle_highlights_logo.ico")
