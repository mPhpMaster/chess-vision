"""Draws chess_vision.ico (a white queen on a green rounded square)."""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=48, fill=(21, 120, 27))
font = ImageFont.truetype(r"C:\Windows\Fonts\seguisym.ttf", 200)
d.text((S / 2, S / 2 + 6), "\u265b", font=font, anchor="mm", fill="white", stroke_width=6, stroke_fill=(10, 60, 14))
img.save(os.path.join(ROOT, "chess_vision.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(os.path.join(ROOT, "installer", "icon_preview.png"))
print("icon written")
