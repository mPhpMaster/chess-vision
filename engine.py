"""A small pure-Python chess engine (no Stockfish).

Negamax alpha-beta with iterative deepening, principal variation search,
transposition table, null-move pruning, late move reductions, quiescence
search, killer/history move ordering and a tapered piece-square evaluation.
"""
import time

import chess

INF = 10 ** 6
MATE = 100000
MATE_BOUND = MATE - 1000
EXACT, LOWER, UPPER = 0, 1, 2

VALUE = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
         chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
PHASE = {chess.PAWN: 0, chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4, chess.KING: 0}

# Piece-square tables from White's point of view, rank 8 first (as you'd look at the board).
_PST = {
    chess.PAWN: [
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0],
    chess.KNIGHT: [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50],
    chess.BISHOP: [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20],
    chess.ROOK: [
        0, 0, 0, 0, 0, 0, 0, 0,
        5, 10, 10, 10, 10, 10, 10, 5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        0, 0, 0, 5, 5, 0, 0, 0],
    chess.QUEEN: [
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20],
}
_KING_MG = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20]
_KING_EG = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50]
PASSED_BONUS = [0, 10, 15, 25, 45, 75, 120, 0]  # by rank from the pawn's own side


def _build_tables():
    mg = {c: {} for c in chess.COLORS}
    eg = {c: {} for c in chess.COLORS}
    for pt in chess.PIECE_TYPES:
        for color in chess.COLORS:
            mg_t, eg_t = [0] * 64, [0] * 64
            for sq in chess.SQUARES:
                idx = sq ^ 56 if color == chess.WHITE else sq  # map to the visual table
                if pt == chess.KING:
                    mg_t[sq], eg_t[sq] = _KING_MG[idx], _KING_EG[idx]
                else:
                    mg_t[sq] = eg_t[sq] = VALUE[pt] + _PST[pt][idx]
            mg[color][pt], eg[color][pt] = mg_t, eg_t
    return mg, eg


MG, EG = _build_tables()


def _passed_masks():
    """Squares in front of a pawn (own + adjacent files) that enemy pawns must not occupy."""
    masks = {chess.WHITE: [0] * 64, chess.BLACK: [0] * 64}
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        for ff in range(max(0, f - 1), min(7, f + 1) + 1):
            for rr in range(r + 1, 8):
                masks[chess.WHITE][sq] |= chess.BB_SQUARES[chess.square(ff, rr)]
            for rr in range(0, r):
                masks[chess.BLACK][sq] |= chess.BB_SQUARES[chess.square(ff, rr)]
    return masks


PASSED_MASK = _passed_masks()


class Timeout(Exception):
    pass


def evaluate(b):
    """Static evaluation in centipawns from the side to move's point of view."""
    mg = eg = phase = 0
    material = {chess.WHITE: 0, chess.BLACK: 0}
    for color in chess.COLORS:
        sign = 1 if color == chess.WHITE else -1
        own = b.occupied_co[color]
        mg_c, eg_c = MG[color], EG[color]
        for pt in chess.PIECE_TYPES:
            bb = b.pieces_mask(pt, color)
            if not bb:
                continue
            mt, et = mg_c[pt], eg_c[pt]
            for sq in chess.scan_forward(bb):
                mg += sign * mt[sq]
                eg += sign * et[sq]
            n = chess.popcount(bb)
            phase += PHASE[pt] * n
            material[color] += VALUE[pt] * n
        if chess.popcount(b.bishops & own) >= 2:
            mg += sign * 30
            eg += sign * 50
        enemy_pawns = b.pawns & b.occupied_co[not color]
        for sq in chess.scan_forward(b.pawns & own):
            if not PASSED_MASK[color][sq] & enemy_pawns:
                rank = chess.square_rank(sq) if color == chess.WHITE else 7 - chess.square_rank(sq)
                mg += sign * PASSED_BONUS[rank] // 2
                eg += sign * PASSED_BONUS[rank]
    phase = min(phase, 24)
    score = (mg * phase + eg * (24 - phase)) // 24

    # Mop-up: in won endgames, drive the losing king to the edge and bring ours closer.
    diff = material[chess.WHITE] - material[chess.BLACK]
    if phase <= 6 and abs(diff) >= 400:
        winner = chess.WHITE if diff > 0 else chess.BLACK
        wk, lk = b.king(winner), b.king(not winner)
        if wk is not None and lk is not None:
            lf, lr = chess.square_file(lk), chess.square_rank(lk)
            center = max(3 - lf, lf - 4) + max(3 - lr, lr - 4)
            bonus = 10 * center + 4 * (14 - chess.square_manhattan_distance(wk, lk))
            score += bonus if winner == chess.WHITE else -bonus
    return score if b.turn == chess.WHITE else -score


class Engine:
    def __init__(self):
        self.tt = {}

    # ---- public --------------------------------------------------------- #
    def analyse(self, board, think_time, multipv=3, should_stop=None, on_depth=None, max_depth=64):
        """Search `board` and return up to `multipv` lines, best first.

        Each line: {"move", "pv", "score" (cp, side to move POV), "mate" (moves or None), "depth"}.
        `on_depth(lines)` is called after each completed depth for live updates.
        """
        self.root = board.copy(stack=False)
        self.board = self.root.copy(stack=False)
        self.deadline = time.time() + think_time
        self.should_stop = should_stop or (lambda: False)
        self.nodes = 0
        self.killers = [[None, None] for _ in range(256)]
        self.history = {}
        self.path = {self.board._transposition_key()}
        if len(self.tt) > 2_000_000:
            self.tt.clear()

        moves = list(self.board.legal_moves)
        if not moves:
            return []
        start = time.time()
        lines = []
        for depth in range(1, max_depth + 1):
            self.check_time = depth > 1  # depth 1 always completes
            try:
                scored = self._root(depth, moves, multipv)
            except Timeout:
                break
            finally:
                self.board = self.root.copy(stack=False)
                self.path = {self.board._transposition_key()}
            top = [m for _, m in scored]
            moves = top + [m for m in moves if m not in top]
            lines = [self._line(s, m, depth) for s, m in scored]
            if on_depth:
                on_depth(lines)
            elapsed = time.time() - start
            if abs(scored[0][0]) >= MATE_BOUND or len(moves) == 1 or elapsed > think_time * 0.45:
                break
        return lines

    # ---- search --------------------------------------------------------- #
    def _root(self, depth, moves, n):
        b = self.board
        scored = []  # (score, move), kept sorted best first
        for m in moves:
            alpha = scored[n - 1][0] if len(scored) >= n else -INF
            b.push(m)
            if alpha == -INF:
                s = -self._negamax(depth - 1, -INF, INF, 1)
            else:
                s = -self._negamax(depth - 1, -alpha - 1, -alpha, 1)
                if s > alpha:
                    s = -self._negamax(depth - 1, -INF, -alpha, 1)
            b.pop()
            if s > alpha or len(scored) < n:
                scored.append((s, m))
                scored.sort(key=lambda x: -x[0])
                del scored[n:]
        best_s, best_m = scored[0]
        self.tt[b._transposition_key()] = (depth, EXACT, best_s, best_m)
        return scored

    def _tick(self):
        self.nodes += 1
        if self.check_time and not self.nodes & 1023:
            if time.time() > self.deadline or self.should_stop():
                raise Timeout

    def _negamax(self, depth, alpha, beta, ply):
        self._tick()
        b = self.board
        key = b._transposition_key()
        if key in self.path or b.halfmove_clock >= 100:
            return 0
        if not (b.pawns or b.rooks or b.queens) and chess.popcount(b.occupied) <= 3:
            return 0  # K vs K, K+minor vs K
        in_check = b.is_check()
        if in_check:
            depth += 1
        if depth <= 0:
            return self._quiesce(alpha, beta, ply)

        alpha_orig = alpha
        tt_move = None
        entry = self.tt.get(key)
        if entry:
            t_depth, flag, t_score, tt_move = entry
            if t_depth >= depth:
                t_score = _from_tt(t_score, ply)
                if flag == EXACT or (flag == LOWER and t_score >= beta) or (flag == UPPER and t_score <= alpha):
                    return t_score

        # Null move pruning: if passing still beats beta, this node is too good to search fully.
        if (depth >= 3 and not in_check and abs(beta) < MATE_BOUND
                and b.occupied_co[b.turn] & ~(b.pawns | b.kings) and evaluate(b) >= beta):
            b.push(chess.Move.null())
            self.path.add(key)
            try:
                s = -self._negamax(depth - 3, -beta, -beta + 1, ply + 1)
            finally:
                self.path.discard(key)
                b.pop()
            if s >= beta:
                return beta

        moves = self._order(b, tt_move, ply)
        if not moves:
            return -MATE + ply if in_check else 0

        best, best_move = -INF, None
        self.path.add(key)
        try:
            for i, m in enumerate(moves):
                quiet = not b.is_capture(m) and not m.promotion
                b.push(m)
                if i == 0:
                    s = -self._negamax(depth - 1, -beta, -alpha, ply + 1)
                else:
                    r = 1 if depth >= 3 and i >= 3 and quiet and not in_check and not b.is_check() else 0
                    if r and i >= 8 and depth >= 5:
                        r = 2
                    s = -self._negamax(depth - 1 - r, -alpha - 1, -alpha, ply + 1)
                    if s > alpha and (r or s < beta):
                        s = -self._negamax(depth - 1, -beta, -alpha, ply + 1)
                b.pop()
                if s > best:
                    best, best_move = s, m
                if s > alpha:
                    alpha = s
                if alpha >= beta:
                    if quiet:
                        k = self.killers[ply]
                        if k[0] != m:
                            k[0], k[1] = m, k[0]
                        hk = (m.from_square, m.to_square)
                        self.history[hk] = self.history.get(hk, 0) + depth * depth
                    break
        finally:
            self.path.discard(key)

        flag = UPPER if best <= alpha_orig else LOWER if best >= beta else EXACT
        self.tt[key] = (depth, flag, _to_tt(best, ply), best_move)
        return best

    def _quiesce(self, alpha, beta, ply):
        self._tick()
        b = self.board
        stand = evaluate(b)
        if stand >= beta:
            return stand
        if stand > alpha:
            alpha = stand
        caps = []
        for m in b.generate_legal_captures():
            victim = b.piece_type_at(m.to_square) or chess.PAWN
            if stand + VALUE[victim] + 200 < alpha and not m.promotion:
                continue  # delta pruning: even winning this piece can't raise alpha
            caps.append((VALUE[victim] * 10 - VALUE[b.piece_type_at(m.from_square)], m))
        caps.sort(key=lambda x: -x[0])
        for _, m in caps:
            b.push(m)
            s = -self._quiesce(-beta, -alpha, ply + 1)
            b.pop()
            if s >= beta:
                return s
            if s > alpha:
                alpha = s
        return alpha

    def _order(self, b, tt_move, ply):
        k0, k1 = self.killers[ply]
        scored = []
        for m in b.legal_moves:
            if m == tt_move:
                s = 10 ** 8
            elif b.is_capture(m):
                victim = b.piece_type_at(m.to_square) or chess.PAWN
                s = 10 ** 7 + VALUE[victim] * 10 - VALUE[b.piece_type_at(m.from_square)]
            elif m.promotion:
                s = 9 * 10 ** 6
            elif m == k0 or m == k1:
                s = 8 * 10 ** 6
            else:
                s = self.history.get((m.from_square, m.to_square), 0)
            scored.append((s, m))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored]

    # ---- results -------------------------------------------------------- #
    def _line(self, score, move, depth):
        b = self.root.copy(stack=False)
        pv = [move]
        b.push(move)
        seen = {b._transposition_key()}
        while len(pv) < 12:
            entry = self.tt.get(b._transposition_key())
            if not entry or entry[3] is None or not b.is_legal(entry[3]):
                break
            b.push(entry[3])
            key = b._transposition_key()
            if key in seen:
                break
            seen.add(key)
            pv.append(entry[3])
        mate = None
        if score >= MATE_BOUND:
            mate = (MATE - score + 1) // 2
        elif score <= -MATE_BOUND:
            mate = -((MATE + score + 1) // 2)
        return {"move": move, "pv": pv, "score": score, "mate": mate, "depth": depth}


def _to_tt(s, ply):
    return s + ply if s >= MATE_BOUND else s - ply if s <= -MATE_BOUND else s


def _from_tt(s, ply):
    return s - ply if s >= MATE_BOUND else s + ply if s <= -MATE_BOUND else s
