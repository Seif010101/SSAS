"""Write packaging/icon.ico (teal square with a white check mark), using Pillow only."""

from pathlib import Path

from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=(15, 118, 110, 255))
w = int(S * 0.09)
d.ellipse([S * 0.2, S * 0.2, S * 0.8, S * 0.8], outline="white", width=w)
d.line([(S * 0.36, S * 0.52), (S * 0.46, S * 0.62), (S * 0.65, S * 0.41)], fill="white", width=w, joint="curve")
out = Path(__file__).with_name("icon.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"wrote {out}")
