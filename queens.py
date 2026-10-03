"""Eight Queens puzzle - place 8 queens so that no queen attacks another.

Click a square to place or remove a queen. Queens that attack each other turn
red. "Hint" adds one queen that still leads to a full solution, and
"Show solution" cycles through all 92 solutions.

Every attempt (from opening the puzzle or pressing "Start over" until it is
solved) is timed and its moves, hints and solution views are counted. All of
it is saved to queens_stats.json in %APPDATA%\ChessVision, under the device name
(the computer name identifies the player).
"""
import json
import os
import socket
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from appdata import data_path

STATS_FILE = data_path("queens_stats.json")
PLAYER = os.environ.get("COMPUTERNAME") or socket.gethostname()

LIGHT, DARK = "#f0d9b5", "#b58863"
ATTACKED, CONFLICT, SOLVED = "#e8a090", "#d9302c", "#5aa04a"
QUEEN = "♛"
RESULT_TEXT = {"solved": "Solved", "shown": "Solution shown", "abandoned": "Abandoned", "playing": "In progress"}


def attacks(a, b):
    (r1, c1), (r2, c2) = a, b
    return a != b and (r1 == r2 or c1 == c2 or abs(r1 - r2) == abs(c1 - c2))


def all_solutions():
    """All 92 solutions, each a tuple of the queen's column for rows 0..7."""
    out = []

    def place(cols):
        r = len(cols)
        if r == 8:
            out.append(tuple(cols))
            return
        for c in range(8):
            if all(c != cc and abs(c - cc) != r - rr for rr, cc in enumerate(cols)):
                place(cols + [c])
    place([])
    return out


SOLUTIONS = all_solutions()


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


class Stats:
    """Persistent record of hint/solution presses and every attempt, per player (device name)."""

    def __init__(self, path=STATS_FILE, player=None):
        player = player or PLAYER
        self.path = path
        self.player = player
        self.data = {"players": {}, "attempts": []}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (OSError, ValueError):
                pass  # unreadable file: start fresh, it gets overwritten on next save
        # Older files kept global totals and attempts without a player: give them to this device.
        old_hints, old_sols = self.data.pop("total_hints", 0), self.data.pop("total_solutions", 0)
        self.totals = self.data["players"].setdefault(player, {"hints": 0, "solutions": 0})
        self.totals["hints"] += old_hints
        self.totals["solutions"] += old_sols
        for a in self.data["attempts"]:
            a.setdefault("player", player)
        if old_hints or old_sols:
            self.save()

    @property
    def all_attempts(self):
        return self.data["attempts"]

    @property
    def attempts(self):
        """This player's attempts."""
        return [a for a in self.data["attempts"] if a["player"] == self.player]

    def add_attempt(self, a):
        self.data["attempts"].append(a)
        self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def best_time(self):
        times = [a["seconds"] for a in self.attempts if a["result"] == "solved"]
        return min(times) if times else None


class QueensPuzzle:
    SQ = 64

    def __init__(self, master, stats_path=STATS_FILE):
        self.top = top = tk.Toplevel(master) if master else tk.Tk()
        self.stats = Stats(stats_path)
        top.title(f"Eight Queens - {self.stats.player}")
        self.queens = set()  # {(row, col)}
        self.sol_index = -1
        self.show_attacks = tk.BooleanVar(value=False)
        self.attempt = None  # dict, also stored in self.stats.attempts
        self.t0 = 0.0

        left = ttk.Frame(top, padding=8)
        left.grid(row=0, column=0, sticky="n")
        self.cv = tk.Canvas(left, width=self.SQ * 8, height=self.SQ * 8, highlightthickness=0)
        self.cv.pack()
        self.cv.bind("<Button-1>", self.click)
        self.msg = ttk.Label(left, text="", font=("Segoe UI", 14, "bold"))
        self.msg.pack(anchor="w", pady=(8, 0))

        right = ttk.Frame(top, padding=8)
        right.grid(row=0, column=1, sticky="n")
        ttk.Label(right, text=f"Player: {self.stats.player}", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(right, text="Place 8 queens so that\nno queen attacks another.",
                  justify="left").pack(anchor="w", pady=(0, 8))
        ttk.Button(right, text="Start over", command=self.start_over).pack(fill="x")
        ttk.Button(right, text="Hint", command=self.hint).pack(fill="x", pady=4)
        ttk.Button(right, text="Show solution", command=self.next_solution).pack(fill="x")
        ttk.Checkbutton(right, text="Show attacked squares", variable=self.show_attacks,
                        command=self.draw).pack(anchor="w", pady=8)

        cur = ttk.LabelFrame(right, text="This attempt", padding=6)
        cur.pack(fill="x")
        self.cur_lbl = ttk.Label(cur, text="", font=("Consolas", 11), justify="left")
        self.cur_lbl.pack(anchor="w")
        tot = ttk.LabelFrame(right, text=f"All time - {self.stats.player}", padding=6)
        tot.pack(fill="x", pady=8)
        self.tot_lbl = ttk.Label(tot, text="", font=("Consolas", 10), justify="left")
        self.tot_lbl.pack(anchor="w")

        hist = ttk.LabelFrame(top, text="History", padding=6)
        hist.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        cols = ("n", "player", "date", "result", "time", "moves", "hints", "solutions")
        heads = ("#", "Player", "Started", "Result", "Time", "Moves", "Hints", "Solutions")
        widths = (40, 90, 140, 120, 60, 60, 60, 80)
        self.tree = ttk.Treeview(hist, columns=cols, show="headings", height=6)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="x")

        top.protocol("WM_DELETE_WINDOW", self.close)
        self.new_attempt()
        self.tick()

    # ---- attempts ------------------------------------------------------- #
    def new_attempt(self):
        self.queens.clear()
        self.sol_index = -1
        self.t0 = time.time()
        self.attempt = {"player": self.stats.player,
                        "started": datetime.now().isoformat(timespec="seconds"), "result": "playing",
                        "seconds": 0, "moves": 0, "hints": 0, "solutions": 0}
        self.draw()
        self.refresh_stats()

    def finished(self):
        return self.attempt["result"] != "playing"

    def end_attempt(self, result):
        """Close the current attempt and save it."""
        a = self.attempt
        a["seconds"] = round(time.time() - self.t0, 1)
        a["result"] = result
        self.stats.add_attempt(a)
        self.refresh_stats()

    def start_over(self):
        a = self.attempt
        if not self.finished() and (a["moves"] or a["hints"]):
            self.end_attempt("abandoned")
        self.new_attempt()

    def close(self):
        a = self.attempt
        if not self.finished() and (a["moves"] or a["hints"]):
            self.end_attempt("abandoned")
        self.top.destroy()

    # ---- actions -------------------------------------------------------- #
    def click(self, e):
        if self.finished():
            self.msg.config(text="Press Start over to play again", foreground="black")
            return
        r, c = int(e.y // self.SQ), int(e.x // self.SQ)
        if not (0 <= r < 8 and 0 <= c < 8):
            return
        if (r, c) in self.queens:
            self.queens.remove((r, c))
        elif len(self.queens) < 8:
            self.queens.add((r, c))
        else:
            return
        self.attempt["moves"] += 1
        self.after_change()

    def hint(self):
        """Add a queen from a solution that contains every queen already placed."""
        if self.finished():
            self.msg.config(text="Press Start over to play again", foreground="black")
            return
        self.attempt["hints"] += 1
        self.stats.totals["hints"] += 1
        self.stats.save()
        for sol in SOLUTIONS:
            cells = {(r, c) for r, c in enumerate(sol)}
            if self.queens <= cells:
                missing = sorted(cells - self.queens)
                if missing:
                    self.queens.add(missing[0])
                self.after_change()
                return
        self.refresh_stats()
        self.msg.config(text="No solution from here - remove a queen", foreground=CONFLICT)

    def next_solution(self):
        self.sol_index = (self.sol_index + 1) % len(SOLUTIONS)
        self.queens = {(r, c) for r, c in enumerate(SOLUTIONS[self.sol_index])}
        self.attempt["solutions"] += 1
        self.stats.totals["solutions"] += 1
        if self.finished():
            self.stats.save()  # attempt dict is already in the saved list; persist the new count
            self.refresh_stats()
        else:
            self.end_attempt("shown")
        self.draw(f"Solution {self.sol_index + 1} of {len(SOLUTIONS)}")

    def after_change(self):
        if self.is_solved():
            self.end_attempt("solved")
        self.draw()
        self.refresh_stats()

    def is_solved(self):
        return len(self.queens) == 8 and not any(attacks(a, b) for a in self.queens for b in self.queens)

    # ---- display -------------------------------------------------------- #
    def tick(self):
        if not self.finished():
            self.refresh_current()
        self.top.after(250, self.tick)

    def refresh_current(self):
        a = self.attempt
        secs = a["seconds"] if self.finished() else time.time() - self.t0
        n = len(self.stats.attempts) + (0 if self.finished() else 1)
        self.cur_lbl.config(text=f"Attempt #{n}   {RESULT_TEXT[a['result']]}\n"
                                 f"Time       {fmt_time(secs)}\n"
                                 f"Moves      {a['moves']}\n"
                                 f"Hints      {a['hints']}\n"
                                 f"Solutions  {a['solutions']}")

    def refresh_stats(self):
        self.refresh_current()
        atts = self.stats.attempts
        solved = sum(a["result"] == "solved" for a in atts)
        best = self.stats.best_time()
        self.tot_lbl.config(text=f"Attempts        {len(atts)}\n"
                                 f"Solved alone    {solved}\n"
                                 f"Best time       {fmt_time(best) if best is not None else '-'}\n"
                                 f"Hint presses    {self.stats.totals['hints']}\n"
                                 f"Solution views  {self.stats.totals['solutions']}")
        self.tree.delete(*self.tree.get_children())
        for i, a in reversed(list(enumerate(self.stats.all_attempts, 1))):
            self.tree.insert("", "end", values=(i, a["player"], a["started"].replace("T", " "), RESULT_TEXT[a["result"]],
                                                fmt_time(a["seconds"]), a["moves"], a["hints"], a["solutions"]))

    def draw(self, note=None):
        cv, S = self.cv, self.SQ
        cv.delete("all")
        conflicts = {q for q in self.queens if any(attacks(q, o) for o in self.queens)}
        covered = {(r, c) for r in range(8) for c in range(8)
                   if any(attacks(q, (r, c)) for q in self.queens)} if self.show_attacks.get() else set()
        solved = len(self.queens) == 8 and not conflicts
        for r in range(8):
            for c in range(8):
                fill = LIGHT if (r + c) % 2 == 0 else DARK
                if (r, c) in covered and (r, c) not in self.queens:
                    fill = ATTACKED
                cv.create_rectangle(c * S, r * S, c * S + S, r * S + S, fill=fill, outline="")
        for r, c in self.queens:
            color = SOLVED if solved else CONFLICT if (r, c) in conflicts else "black"
            cv.create_text(c * S + S / 2, r * S + S / 2, text=QUEEN, fill=color,
                           font=("Segoe UI Symbol", int(S * 0.62)))
        for i in range(8):  # coordinates
            cv.create_text(i * S + S - 6, 8 * S - 8, text="abcdefgh"[i], font=("Segoe UI", 8), fill="#333")
            cv.create_text(6, i * S + 9, text=str(8 - i), font=("Segoe UI", 8), fill="#333")

        if solved and self.attempt and self.attempt["result"] == "solved":
            text, fg = note or f"Solved in {fmt_time(self.attempt['seconds'])} " \
                               f"with {self.attempt['moves']} moves!", SOLVED
        elif solved:
            text, fg = note or "Solved!", SOLVED
        elif conflicts:
            text, fg = f"{len(self.queens)}/8 queens - {len(conflicts)} under attack", CONFLICT
        else:
            text, fg = f"{len(self.queens)}/8 queens placed", "black"
        self.msg.config(text=text, foreground=fg)


if __name__ == "__main__":
    QueensPuzzle(None).top.mainloop()
