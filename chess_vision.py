"""Chess Vision - reads a chessboard from your screen and suggests the best move.

Workflow:
  1. "Select board"  - drag a square around the board on a frozen screenshot.
  2. "Calibrate"     - with the board in the STARTING position, learn the piece set.
  3. Turn on "Auto" (or press "Analyze now") - the board is read from screen and
     the built-in engine (engine.py) suggests the best move for the side to move.
"""
import ctypes
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk

import chess
import mss
import numpy as np
from PIL import Image, ImageTk

from appdata import APP_NAME, SOURCE_DIR, data_path
from engine import Engine
from practice import PracticeBoard
from queens import QueensPuzzle

CALIB_FILE = data_path("calibration.npz")
ICON_FILE = os.path.join(getattr(sys, "_MEIPASS", SOURCE_DIR), "chess_vision.ico")
FEAT = 32          # each square is resized to FEAT x FEAT for recognition
INSET = 0.06       # trim this fraction off each square edge (grid lines, borders)
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


# --------------------------------------------------------------------------- #
# Screen capture
# --------------------------------------------------------------------------- #
def set_dpi_aware():
    """Make Tk and mss agree on physical pixel coordinates on scaled displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def grab(region):
    left, top, size = region
    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": size, "height": size})
    return np.ascontiguousarray(np.asarray(shot)[:, :, 2::-1])  # BGRA -> RGB


# --------------------------------------------------------------------------- #
# Recognition
# --------------------------------------------------------------------------- #
def split_cells(img):
    """Return 64 square crops in screen order (row 0 = top, col 0 = left)."""
    h, w = img.shape[:2]
    cw, ch = w / 8, h / 8
    cells = []
    for r in range(8):
        for c in range(8):
            x0, x1 = int(c * cw + cw * INSET), int((c + 1) * cw - cw * INSET)
            y0, y1 = int(r * ch + ch * INSET), int((r + 1) * ch - ch * INSET)
            cells.append(img[y0:y1, x0:x1])
    return cells


def cell_arrays(cell):
    """Distance of each pixel from the square's background colour, plus luminance.

    The background is estimated from the square's border ring, so highlighted
    squares (last move, selection) and textured boards still work.
    """
    a = np.asarray(Image.fromarray(cell).resize((FEAT, FEAT), Image.BOX), dtype=np.float32)
    ring = np.concatenate([a[:2].reshape(-1, 3), a[-2:].reshape(-1, 3),
                           a[2:-2, :2].reshape(-1, 3), a[2:-2, -2:].reshape(-1, 3)])
    bg = np.median(ring, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    return dist, a @ LUMA


def features(dist, lum, thr):
    """Background-independent feature: piece silhouette + piece luminance."""
    mask = dist > thr
    feat = np.concatenate([mask.ravel() * 255.0, np.where(mask, lum, 0.0).ravel()])
    return feat.astype(np.float32), float(mask.mean()), mask


def cell_to_square(i, flipped):
    r, c = divmod(i, 8)
    return chess.square(7 - c, r) if flipped else chess.square(c, 7 - r)


class Recognizer:
    def __init__(self):
        self.templates = None   # (N, D) feature vectors
        self.labels = None      # (N,) piece symbols
        self.thr = None         # pixel "is piece" distance threshold
        self.occ = None         # fraction of piece pixels above which a square is occupied

    @property
    def ready(self):
        return self.templates is not None

    def calibrate(self, img):
        """Learn the piece set from a board showing the starting position.

        Returns True if Black is at the bottom of the screen.
        """
        arrs = [cell_arrays(c) for c in split_cells(img)]
        empty_dist = np.concatenate([arrs[i][0].ravel() for i in range(16, 48)])
        thr = float(np.clip(np.percentile(empty_dist, 99) + 12, 20, 60))
        feats = [features(d, l, thr) for d, l in arrs]
        piece_idx = list(range(16)) + list(range(48, 64))

        empty_occ = max(f[1] for f in feats[16:48])
        piece_occ = min(feats[i][1] for i in piece_idx)
        if piece_occ < 0.04 or piece_occ <= empty_occ * 1.5:
            raise ValueError("This doesn't look like the starting position - "
                             "check the board selection and set up a new game.")

        def mean_piece_lum(rows):
            vals = [arrs[i][1][feats[i][2]] for r in rows for i in range(r * 8, r * 8 + 8)]
            return float(np.concatenate(vals).mean())

        flipped = mean_piece_lum([0, 1]) > mean_piece_lum([6, 7])  # bright pieces on top

        start = chess.Board()
        self.templates = np.stack([feats[i][0] for i in piece_idx])
        self.labels = np.array([start.piece_at(cell_to_square(i, flipped)).symbol() for i in piece_idx])
        self.thr = thr
        self.occ = (empty_occ + piece_occ) / 2
        return flipped

    def read(self, img):
        """Return 64 piece symbols ('' for empty) in screen order."""
        out = []
        for cell in split_cells(img):
            feat, occ, _ = features(*cell_arrays(cell), self.thr)
            if occ < self.occ:
                out.append("")
                continue
            d = ((self.templates - feat) ** 2).sum(axis=1)
            out.append(str(self.labels[int(d.argmin())]))
        return out

    def save(self, path, region, flipped):
        np.savez(path, templates=self.templates, labels=self.labels, thr=self.thr,
                 occ=self.occ, region=np.array(region), flipped=flipped)

    def load(self, path):
        z = np.load(path)
        self.templates, self.labels = z["templates"], z["labels"]
        self.thr, self.occ = float(z["thr"]), float(z["occ"])
        return tuple(int(v) for v in z["region"]), bool(z["flipped"])


def guess_flipped(syms, current):
    """White pawns sit lower on screen than Black pawns when White is at the bottom."""
    wp = [i // 8 for i, s in enumerate(syms) if s == "P"]
    bp = [i // 8 for i, s in enumerate(syms) if s == "p"]
    if wp and bp and np.mean(wp) != np.mean(bp):
        return np.mean(wp) < np.mean(bp)
    return current


def placement_fen(syms, flipped):
    b = chess.BaseBoard(None)
    for i, s in enumerate(syms):
        if s:
            b.set_piece_at(cell_to_square(i, flipped), chess.Piece.from_symbol(s))
    return b.board_fen()


# --------------------------------------------------------------------------- #
# Position logic
# --------------------------------------------------------------------------- #
def build_board(fen, white_to_move):
    b = chess.Board(None)
    b.set_board_fen(fen)
    b.turn = white_to_move
    rights = ""
    for king_sq, rook_sq, color, flag in ((chess.E1, chess.H1, chess.WHITE, "K"),
                                          (chess.E1, chess.A1, chess.WHITE, "Q"),
                                          (chess.E8, chess.H8, chess.BLACK, "k"),
                                          (chess.E8, chess.A8, chess.BLACK, "q")):
        if (b.piece_at(king_sq) == chess.Piece(chess.KING, color)
                and b.piece_at(rook_sq) == chess.Piece(chess.ROOK, color)):
            rights += flag
    b.set_castling_fen(rights or "-")
    return b


def infer_move(prev, fen):
    """If `fen` is one legal move away from `prev`, return the board after it."""
    for turn in (prev.turn, not prev.turn):
        b = prev.copy(stack=False)
        if b.turn != turn:
            b.turn, b.ep_square = turn, None
        for m in list(b.legal_moves):
            b.push(m)
            if b.board_fen() == fen:
                return b
            b.pop()
    return None


def fmt_score(line, white_to_move):
    """Format an engine line's score from White's point of view."""
    sign = 1 if white_to_move else -1
    if line["mate"] is not None:
        return f"#{sign * line['mate']}"
    return f"{sign * line['score'] / 100:+.2f}"


# --------------------------------------------------------------------------- #
# Board region selector (frozen full-screen screenshot)
# --------------------------------------------------------------------------- #
class RegionSelector:
    HELP = ("Drag a square around the chessboard (edge to edge).   "
            "Arrows: move 1px   Shift+Arrows: resize   Enter: confirm   Esc: cancel")

    def __init__(self, root, on_done, init=None):
        with mss.mss() as sct:
            mon = sct.monitors[0]
            shot = sct.grab(mon)
        self.ox, self.oy = mon["left"], mon["top"]
        self.on_done = on_done
        self.top = top = tk.Toplevel(root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
        self.photo = ImageTk.PhotoImage(Image.frombytes("RGB", shot.size, shot.rgb))
        self.cv = cv = tk.Canvas(top, width=mon["width"], height=mon["height"],
                                 highlightthickness=0, cursor="crosshair")
        cv.pack()
        cv.create_image(0, 0, anchor="nw", image=self.photo)
        t = cv.create_text(20, 20, anchor="nw", text=self.HELP, fill="white", font=("Segoe UI", 12, "bold"))
        cv.create_rectangle(cv.bbox(t), fill="black", outline="")
        cv.tag_raise(t)

        self.rect = (init[0] - self.ox, init[1] - self.oy, init[2]) if init else None
        self.start = None
        cv.bind("<ButtonPress-1>", self.press)
        cv.bind("<B1-Motion>", self.drag)
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            top.bind(f"<{key}>", lambda e, dx=dx, dy=dy: self.nudge(dx, dy, 0))
            top.bind(f"<Shift-{key}>", lambda e, d=dx + dy: self.nudge(0, 0, d))
        top.bind("<Return>", lambda e: self.finish(True))
        top.bind("<Escape>", lambda e: self.finish(False))
        top.focus_force()
        self.redraw()

    def press(self, e):
        self.start = (e.x, e.y)

    def drag(self, e):
        sx, sy = self.start
        dx, dy = e.x - sx, e.y - sy
        s = max(abs(dx), abs(dy))
        self.rect = (sx if dx >= 0 else sx - s, sy if dy >= 0 else sy - s, s)
        self.redraw()

    def nudge(self, dx, dy, ds):
        if self.rect:
            x, y, s = self.rect
            self.rect = (x + dx, y + dy, max(16, s + ds))
            self.redraw()

    def redraw(self):
        self.cv.delete("sel")
        if not self.rect:
            return
        x, y, s = self.rect
        for k in range(1, 8):
            o = s * k / 8
            self.cv.create_line(x + o, y, x + o, y + s, fill="#00ff66", tags="sel")
            self.cv.create_line(x, y + o, x + s, y + o, fill="#00ff66", tags="sel")
        self.cv.create_rectangle(x, y, x + s, y + s, outline="red", width=2, tags="sel")

    def finish(self, ok):
        self.top.destroy()
        if ok and self.rect and self.rect[2] >= 64:
            x, y, s = self.rect
            self.on_done((int(x + self.ox), int(y + self.oy), int(s)))
        else:
            self.on_done(None)


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #
class App:
    SQ = 48
    GLYPH = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}

    def __init__(self, root):
        self.root = root
        root.title("Chess Vision")
        root.attributes("-topmost", True)
        self.rec = Recognizer()
        self.region = None
        self.flipped = False
        self.board = None          # current chess.Board
        self.shown_fen = None
        self.pending_fen = None
        self.best_move = None
        self.engine = Engine()
        self.engine_lock = threading.Lock()
        self.gen = 0

        self.auto = tk.BooleanVar(value=False)
        self.auto_orient = tk.BooleanVar(value=True)
        self.on_top = tk.BooleanVar(value=True)
        self.turn = tk.StringVar(value="w")
        self.think = tk.DoubleVar(value=3.0)

        left = ttk.Frame(root, padding=8)
        left.grid(row=0, column=0, sticky="n")
        self.cv = tk.Canvas(left, width=self.SQ * 8, height=self.SQ * 8, highlightthickness=0)
        self.cv.pack()
        self.best_lbl = ttk.Label(left, text="Best move: -", font=("Segoe UI", 16, "bold"))
        self.best_lbl.pack(anchor="w", pady=(8, 0))
        self.lines_lbl = ttk.Label(left, text="", font=("Consolas", 10), justify="left")
        self.lines_lbl.pack(anchor="w")

        right = ttk.Frame(root, padding=8)
        right.grid(row=0, column=1, sticky="n")
        ttk.Button(right, text="1. Select board", command=self.select_region).pack(fill="x")
        ttk.Button(right, text="2. Calibrate (start position)", command=self.calibrate).pack(fill="x", pady=4)
        ttk.Button(right, text="Analyze now", command=lambda: self.scan(force=True)).pack(fill="x")
        ttk.Checkbutton(right, text="Auto (watch the board)", variable=self.auto).pack(anchor="w", pady=(8, 0))

        side = ttk.LabelFrame(right, text="Side to move", padding=4)
        side.pack(fill="x", pady=8)
        ttk.Radiobutton(side, text="White", value="w", variable=self.turn, command=self.turn_changed).pack(anchor="w")
        ttk.Radiobutton(side, text="Black", value="b", variable=self.turn, command=self.turn_changed).pack(anchor="w")

        ttk.Button(right, text="Flip board", command=self.flip).pack(fill="x")
        ttk.Checkbutton(right, text="Auto-detect orientation", variable=self.auto_orient).pack(anchor="w")
        ttk.Checkbutton(right, text="Always on top", variable=self.on_top,
                        command=lambda: root.attributes("-topmost", self.on_top.get())).pack(anchor="w")
        tf = ttk.Frame(right)
        tf.pack(fill="x", pady=8)
        ttk.Label(tf, text="Think time (s)").pack(side="left")
        ttk.Spinbox(tf, from_=0.1, to=30, increment=0.5, textvariable=self.think, width=5).pack(side="right")
        ttk.Button(right, text="Practice board", command=lambda: PracticeBoard(root)).pack(fill="x")
        ttk.Button(right, text="8 Queens puzzle", command=lambda: QueensPuzzle(root)).pack(fill="x", pady=4)

        self.status = ttk.Label(root, text="", padding=(8, 0, 8, 8), wraplength=600, foreground="#555")
        self.status.grid(row=1, column=0, columnspan=2, sticky="w")

        if os.path.exists(CALIB_FILE):
            try:
                self.region, self.flipped = self.rec.load(CALIB_FILE)
                self.set_status("Loaded saved calibration. Turn on Auto or press Analyze now.")
            except Exception as e:
                self.set_status(f"Could not load calibration ({e}). Select the board and calibrate.")
        else:
            self.set_status("Step 1: Select board.  Step 2: show the starting position and Calibrate.")

        self.draw()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.after(400, self.tick)

    # ---- UI helpers ------------------------------------------------------ #
    def set_status(self, text):
        self.status.config(text=text)

    def draw(self):
        cv, S = self.cv, self.SQ
        cv.delete("all")
        for i in range(64):
            r, c = divmod(i, 8)
            sq = cell_to_square(i, self.flipped)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            cv.create_rectangle(c * S, r * S, c * S + S, r * S + S, outline="",
                                fill="#f0d9b5" if light else "#b58863")
            p = self.board.piece_at(sq) if self.board else None
            if p:
                g = self.GLYPH[p.symbol().lower()]
                x, y = c * S + S / 2, r * S + S / 2
                font = ("Segoe UI Symbol", int(S * 0.62))
                if p.color == chess.WHITE:
                    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        cv.create_text(x + ox, y + oy, text=g, font=font, fill="black")
                    cv.create_text(x, y, text=g, font=font, fill="white")
                else:
                    cv.create_text(x, y, text=g, font=font, fill="black")
        if self.best_move:
            def center(sq):
                i = next(i for i in range(64) if cell_to_square(i, self.flipped) == sq)
                r, c = divmod(i, 8)
                return c * S + S / 2, r * S + S / 2
            (x0, y0), (x1, y1) = center(self.best_move.from_square), center(self.best_move.to_square)
            cv.create_line(x0, y0, x1, y1, fill="#15781b", width=S // 6, arrow=tk.LAST,
                           arrowshape=(S / 2.2, S / 2, S / 5), stipple="gray75")

    # ---- Actions --------------------------------------------------------- #
    def select_region(self):
        self.root.withdraw()

        def done(region):
            self.root.deiconify()
            if region:
                self.region = region
                self.set_status(f"Board at {region}. Now show the starting position and press Calibrate.")
        self.root.after(250, lambda: RegionSelector(self.root, done, self.region))

    def calibrate(self):
        if not self.region:
            self.set_status("Select the board first.")
            return
        try:
            self.flipped = self.rec.calibrate(grab(self.region))
        except ValueError as e:
            self.set_status(str(e))
            return
        self.rec.save(CALIB_FILE, self.region, self.flipped)
        self.board, self.shown_fen = None, None
        self.set_status(f"Calibrated ({'Black' if self.flipped else 'White'} at bottom). "
                        "Turn on Auto or press Analyze now.")
        self.scan(force=True)

    def flip(self):
        self.auto_orient.set(False)
        self.flipped = not self.flipped
        self.board, self.shown_fen = None, None
        self.scan(force=True)

    def turn_changed(self):
        if self.board:
            b = self.board.copy(stack=False)
            b.turn, b.ep_square = self.turn.get() == "w", None
            self.set_board(b)

    def tick(self):
        if self.auto.get() and self.rec.ready and self.region:
            try:
                self.scan()
            except Exception as e:
                self.set_status(f"Scan error: {e}")
        self.root.after(400, self.tick)

    def scan(self, force=False):
        if not (self.rec.ready and self.region):
            self.set_status("Select the board and calibrate first.")
            return
        syms = self.rec.read(grab(self.region))
        if self.auto_orient.get():
            self.flipped = guess_flipped(syms, self.flipped)
        fen = placement_fen(syms, self.flipped)
        if not force:
            stable = fen == self.pending_fen  # wait for animations to finish
            self.pending_fen = fen
            if not stable or fen == self.shown_fen:
                return
        self.pending_fen = fen

        white = self.turn.get() == "w"
        b = None
        if self.board is not None:
            if self.board.board_fen() == fen:
                b = self.board.copy(stack=False)
                if force and b.turn != white:
                    b.turn, b.ep_square = white, None
            else:
                b = infer_move(self.board, fen)
        if b is None:
            b = build_board(fen, white)
        self.set_board(b)

    def set_board(self, b):
        if not b.is_valid() and b.status() & chess.STATUS_OPPOSITE_CHECK:
            b.turn, b.ep_square = not b.turn, None
        self.board, self.shown_fen = b, b.board_fen()
        self.turn.set("w" if b.turn else "b")
        self.best_move = None
        self.draw()
        if not b.is_valid():
            self.best_lbl.config(text="Best move: -")
            self.lines_lbl.config(text="")
            self.set_status(f"Position looks invalid ({b.status()!r}). Check the board selection, "
                            "re-calibrate, or use Flip board.")
            return
        if b.is_game_over():
            self.best_lbl.config(text=f"Game over: {b.result()}")
            self.lines_lbl.config(text="")
            return
        self.analyze(b)

    # ---- Engine ---------------------------------------------------------- #
    def analyze(self, board):
        self.gen += 1
        self.best_lbl.config(text="Thinking...")
        try:
            t = max(0.2, float(self.think.get()))
        except (tk.TclError, ValueError):
            t = 3.0
        threading.Thread(target=self._worker, args=(board.copy(stack=False), self.gen, t), daemon=True).start()

    def _worker(self, board, gen, think):
        with self.engine_lock:
            if gen != self.gen:
                return
            try:
                self.engine.analyse(board, think, multipv=3,
                                    should_stop=lambda: gen != self.gen,
                                    on_depth=lambda lines: self.root.after(0, self.show_result, board, lines, gen))
            except Exception as e:
                self.root.after(0, self.set_status, f"Engine error: {e}")

    def show_result(self, board, lines, gen):
        if gen != self.gen or not lines:
            return
        best = lines[0]["move"]
        self.best_move = best
        side = "White" if board.turn else "Black"
        self.best_lbl.config(text=f"{side}: {board.san(best)}  ({chess.square_name(best.from_square)}"
                                  f"→{chess.square_name(best.to_square)})  {fmt_score(lines[0], board.turn)}")
        text = [f"{fmt_score(l, board.turn):>7}  {board.variation_san(l['pv'][:8])}" for l in lines]
        self.lines_lbl.config(text="\n".join(text))
        self.set_status(f"Depth {lines[0]['depth']}   FEN: {board.fen()}")
        self.draw()

    def quit(self):
        self.gen += 1  # stops any running search
        self.root.destroy()


def set_icon(root):
    if os.path.exists(ICON_FILE):
        try:
            root.iconbitmap(default=ICON_FILE)  # also applies to Practice / Queens windows
        except tk.TclError:
            pass


def main(argv):
    """Entry point. --practice or --queens opens that window on its own."""
    set_dpi_aware()
    root = tk.Tk()
    set_icon(root)
    if "--queens" in argv or "--practice" in argv:
        root.withdraw()
        win = QueensPuzzle(root) if "--queens" in argv else PracticeBoard(root)
        win.top.bind("<Destroy>", lambda e: root.destroy() if e.widget is win.top else None)
    else:
        App(root)
        root.title(APP_NAME)
    root.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
