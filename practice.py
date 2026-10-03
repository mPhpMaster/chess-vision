"""Practice board - move the pieces yourself for both sides and get hints.

The hint follows an adjustable error rate: at 0% it always shows the engine's
best move; higher rates shorten the thinking time and sometimes suggest a
weaker candidate move instead, so you can practise against human-like play.
"""
import random
import threading
import tkinter as tk
from tkinter import ttk

import chess

from engine import Engine

LIGHT, DARK = "#f0d9b5", "#b58863"
SELECT, TARGET = "#f6f669", "#9bc06a"
GLYPH = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}


def pick_hint(lines, error_pct, rng):
    """Best line, or with probability error_pct a weaker candidate (closer ones more likely)."""
    if len(lines) > 1 and rng.random() * 100 < error_pct:
        cands = lines[1:]
        return rng.choices(cands, weights=[1 / (i + 1) for i in range(len(cands))])[0], True
    return lines[0], False


class PracticeBoard:
    SQ = 64

    def __init__(self, master):
        self.top = top = tk.Toplevel(master) if master else tk.Tk()
        top.title("Practice board")
        self.board = chess.Board()
        self.flipped = False
        self.selected = None
        self.hint = None
        self.engine = Engine()
        self.engine_lock = threading.Lock()
        self.gen = 0
        self.rng = random.Random()

        self.error = tk.IntVar(value=20)
        self.think = tk.DoubleVar(value=3.0)
        self.auto_hint = tk.BooleanVar(value=True)
        self.reveal = tk.BooleanVar(value=False)

        left = ttk.Frame(top, padding=8)
        left.grid(row=0, column=0, sticky="n")
        self.cv = tk.Canvas(left, width=self.SQ * 8, height=self.SQ * 8, highlightthickness=0)
        self.cv.pack()
        self.cv.bind("<Button-1>", self.click)
        self.hint_lbl = ttk.Label(left, text="", font=("Segoe UI", 15, "bold"))
        self.hint_lbl.pack(anchor="w", pady=(8, 0))
        self.status = ttk.Label(left, text="", foreground="#555")
        self.status.pack(anchor="w")

        right = ttk.Frame(top, padding=8)
        right.grid(row=0, column=1, sticky="n")
        ttk.Button(right, text="New game", command=self.new_game).pack(fill="x")
        ttk.Button(right, text="Undo", command=self.undo).pack(fill="x", pady=4)
        ttk.Button(right, text="Flip board", command=self.flip).pack(fill="x")
        ttk.Button(right, text="Hint now", command=self.request_hint).pack(fill="x", pady=4)
        ttk.Checkbutton(right, text="Hint every move", variable=self.auto_hint).pack(anchor="w")
        ttk.Checkbutton(right, text="Tell me when the hint is a mistake", variable=self.reveal,
                        command=self.show_hint_text).pack(anchor="w")

        ef = ttk.LabelFrame(right, text="Error rate", padding=4)
        ef.pack(fill="x", pady=8)
        self.err_lbl = ttk.Label(ef, text="20%")
        self.err_lbl.pack(anchor="e")
        ttk.Scale(ef, from_=0, to=100, variable=self.error, orient="horizontal",
                  command=lambda v: self.err_lbl.config(text=f"{int(float(v))}%")).pack(fill="x")
        tf = ttk.Frame(right)
        tf.pack(fill="x")
        ttk.Label(tf, text="Think time (s)").pack(side="left")
        ttk.Spinbox(tf, from_=0.2, to=30, increment=0.5, textvariable=self.think, width=5).pack(side="right")

        self.moves_txt = tk.Text(right, width=24, height=14, font=("Consolas", 10), state="disabled")
        self.moves_txt.pack(pady=8)

        top.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    # ---- board interaction ---------------------------------------------- #
    def square_at(self, x, y):
        c, r = int(x // self.SQ), int(y // self.SQ)
        if not (0 <= c < 8 and 0 <= r < 8):
            return None
        return chess.square(7 - c, r) if self.flipped else chess.square(c, 7 - r)

    def xy(self, sq):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        c, row = (7 - f, r) if self.flipped else (f, 7 - r)
        return c * self.SQ, row * self.SQ

    def click(self, e):
        sq = self.square_at(e.x, e.y)
        if sq is None or self.board.is_game_over():
            return
        if self.selected is not None:
            move = chess.Move(self.selected, sq)
            p = self.board.piece_at(self.selected)
            if p and p.piece_type == chess.PAWN and chess.square_rank(sq) in (0, 7):
                move.promotion = chess.QUEEN
            if move in self.board.legal_moves:
                self.selected = None
                self.board.push(move)
                self.refresh()
                return
        p = self.board.piece_at(sq)
        self.selected = sq if p and p.color == self.board.turn else None
        self.draw()

    def new_game(self):
        self.board = chess.Board()
        self.selected = None
        self.refresh()

    def undo(self):
        if self.board.move_stack:
            self.board.pop()
            self.selected = None
            self.refresh()

    def flip(self):
        self.flipped = not self.flipped
        self.draw()

    def refresh(self):
        self.gen += 1  # cancels any running hint search
        self.hint = None
        self.hint_lbl.config(text="")
        self.update_moves()
        self.draw()
        b = self.board
        if b.is_game_over():
            self.status.config(text=f"Game over: {b.result()} ({b.outcome().termination.name.lower()})")
            return
        self.status.config(text=f"{'White' if b.turn else 'Black'} to move" + ("  - check!" if b.is_check() else ""))
        if self.auto_hint.get():
            self.request_hint()

    def update_moves(self):
        tmp = chess.Board()
        parts = []
        for i, m in enumerate(self.board.move_stack):
            san = tmp.san(m)
            parts.append(f"{i // 2 + 1:>3}. {san:<8}" if i % 2 == 0 else f"{san}\n")
            tmp.push(m)
        self.moves_txt.config(state="normal")
        self.moves_txt.delete("1.0", "end")
        self.moves_txt.insert("end", "".join(parts))
        self.moves_txt.see("end")
        self.moves_txt.config(state="disabled")

    # ---- drawing -------------------------------------------------------- #
    def draw(self):
        cv, S = self.cv, self.SQ
        cv.delete("all")
        last = self.board.peek() if self.board.move_stack else None
        targets = {m.to_square for m in self.board.legal_moves if m.from_square == self.selected}
        for sq in chess.SQUARES:
            x, y = self.xy(sq)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            fill = LIGHT if light else DARK
            if sq == self.selected or (last and sq in (last.from_square, last.to_square)):
                fill = SELECT
            cv.create_rectangle(x, y, x + S, y + S, fill=fill, outline="")
            if sq in targets:
                cv.create_oval(x + S * .38, y + S * .38, x + S * .62, y + S * .62, fill=TARGET, outline="")
            p = self.board.piece_at(sq)
            if p:
                g, cx, cy = GLYPH[p.symbol().lower()], x + S / 2, y + S / 2
                font = ("Segoe UI Symbol", int(S * 0.62))
                if p.color == chess.WHITE:
                    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        cv.create_text(cx + ox, cy + oy, text=g, font=font, fill="black")
                    cv.create_text(cx, cy, text=g, font=font, fill="white")
                else:
                    cv.create_text(cx, cy, text=g, font=font, fill="black")
        if self.hint:
            m = self.hint[0]["move"]
            (x0, y0), (x1, y1) = self.xy(m.from_square), self.xy(m.to_square)
            cv.create_line(x0 + S / 2, y0 + S / 2, x1 + S / 2, y1 + S / 2, fill="#15781b", width=S // 6,
                           arrow=tk.LAST, arrowshape=(S / 2.2, S / 2, S / 5), stipple="gray75")

    # ---- hints ---------------------------------------------------------- #
    def request_hint(self):
        if self.board.is_game_over():
            return
        self.gen += 1
        gen, err = self.gen, int(self.error.get())
        try:
            think = max(0.2, float(self.think.get()))
        except (tk.TclError, ValueError):
            think = 3.0
        think = max(0.2, think * (1 - err / 100))  # the error rate also cuts thinking time
        self.hint_lbl.config(text="Thinking...")
        threading.Thread(target=self._worker, args=(self.board.copy(), gen, think, err), daemon=True).start()

    def _worker(self, board, gen, think, err):
        with self.engine_lock:
            if gen != self.gen:
                return
            try:
                lines = self.engine.analyse(board, think, multipv=4, should_stop=lambda: gen != self.gen)
            except Exception as e:
                self.top.after(0, lambda: self.status.config(text=f"Engine error: {e}"))
                return
        if lines and gen == self.gen:
            line, mistake = pick_hint(lines, err, self.rng)
            self.top.after(0, self.set_hint, board, line, mistake, lines[0], gen)

    def set_hint(self, board, line, mistake, best, gen):
        if gen != self.gen:
            return
        self.hint = (line, mistake, best, board)
        self.show_hint_text()
        self.draw()

    def show_hint_text(self):
        if not self.hint:
            return
        line, mistake, best, board = self.hint
        m = line["move"]
        text = f"Hint: {board.san(m)}  ({chess.square_name(m.from_square)}→{chess.square_name(m.to_square)})"
        if self.reveal.get() and mistake:
            text += f"   [mistake - best was {board.san(best['move'])}]"
        self.hint_lbl.config(text=text)

    def close(self):
        self.gen += 1
        self.top.destroy()


if __name__ == "__main__":
    app = PracticeBoard(None)
    app.top.mainloop()
