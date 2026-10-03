"""Renders synthetic boards and checks that Recognizer reads them back correctly."""
import random

import chess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from chess_vision import Recognizer, guess_flipped, placement_fen

GLYPH = {"k": "\u265a", "q": "\u265b", "r": "\u265c", "b": "\u265d", "n": "\u265e", "p": "\u265f"}
THEMES = {"brown": ((240, 217, 181), (181, 136, 99)), "green": ((238, 238, 210), (118, 150, 86))}
FONT = ImageFont.truetype(r"C:\Windows\Fonts\seguisym.ttf", 60)


def render(board, flipped, theme, size=640, highlights=()):
    light, dark = THEMES[theme]
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    s = size // 8
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        col, row = (7 - f, r) if flipped else (f, 7 - r)
        fill = light if (f + r) % 2 else dark
        if sq in highlights:
            fill = (246, 246, 105)
        d.rectangle([col * s, row * s, col * s + s, row * s + s], fill=fill)
        p = board.piece_at(sq)
        if p:
            white = p.color == chess.WHITE
            d.text((col * s + s / 2, row * s + s / 2), GLYPH[p.symbol().lower()], font=FONT, anchor="mm",
                   fill=(250, 250, 250) if white else (30, 30, 30), stroke_width=2,
                   stroke_fill=(20, 20, 20) if white else (200, 200, 200))
    return np.asarray(img)


def random_position(rng):
    b = chess.Board()
    for _ in range(rng.randint(10, 80)):
        moves = list(b.legal_moves)
        if not moves:
            break
        b.push(rng.choice(moves))
    return b


def main():
    rng = random.Random(1)
    total = errors = 0
    for theme in THEMES:
        for calib_flipped in (False, True):
            rec = Recognizer()
            got = rec.calibrate(render(chess.Board(), calib_flipped, theme))
            assert got == calib_flipped, f"orientation detection failed ({theme}, {calib_flipped})"
            for _ in range(25):
                b = random_position(rng)
                flipped = rng.random() < 0.5
                hl = [b.peek().from_square, b.peek().to_square] if b.move_stack else []
                syms = rec.read(render(b, flipped, theme, highlights=hl))
                fen = placement_fen(syms, guess_flipped(syms, flipped))
                total += 1
                if fen != b.board_fen():
                    errors += 1
                    print(f"MISMATCH {theme}: expected {b.board_fen()} got {fen}")
    print(f"{total - errors}/{total} positions read correctly")


if __name__ == "__main__":
    main()
