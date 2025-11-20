#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
8x8 Block Puzzle Solver
- Removed constant board highlights (no preferred rows/cols outline)
- All UI translated to English
- Keeps improved scoring logic (green/red same priority)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import copy
import itertools
import math

# ---------------- CONFIG ----------------
BOARD_SIZE = 8
TARGET = {'yellow': 10, 'green': 5, 'red': 5}

COLOR_HEX = {
    'brown': '#8B4513',
    'yellow': '#FFD700',
    'green': '#32CD32',
    'red': '#FF4500',
    None: '#FFFFFF'
}

HIGHLIGHT_COLOR = '#00BFFF'

# Search parameters
TOP_K_CANDIDATES = 30
MAX_DFS_NODES = 45000

# Penalties / bonuses
OVERKILL_PENALTY = 12000.0
COLUMN_CLEAR_PENALTY = 10000.0

# Weight constants for scoring
WEIGHT_COLOR_PRIMARY = 1000.0
WEIGHT_COLOR_YELLOW = 100.0
NEAR_COMPLETE_BONUS_DIV = 3000.0
ACHIEVEMENT_BONUS = 100000.0

# No preferred rows/columns — user asked to remove highlight permanently
# Therefore disable preferred bonuses
POTENTIAL_WEIGHT = 0.1


# ---------------- Utilities ----------------
def create_empty_board():
    return [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

def apply_initial_setup(board):
    board[4][2] = 'red'
    board[3][3] = 'yellow'
    board[3][4] = 'green'
    board[4][5] = 'brown'
    return board

def clear_lines(board):
    cleared = {'yellow':0, 'green':0, 'red':0}
    rows = [r for r in range(BOARD_SIZE)
            if all(board[r][c] is not None for c in range(BOARD_SIZE))]
    cols = [c for c in range(BOARD_SIZE)
            if all(board[r][c] is not None for r in range(BOARD_SIZE))]
    to_clear = set()
    cleared_lines = []

    for r in rows:
        cleared_lines.append(('r', r))
        for c in range(BOARD_SIZE):
            to_clear.add((r, c))
    for c in cols:
        cleared_lines.append(('c', c))
        for r in range(BOARD_SIZE):
            to_clear.add((r, c))

    for (r, c) in to_clear:
        col = board[r][c]
        if col in cleared:
            cleared[col] += 1
        board[r][c] = None

    return cleared, cleared_lines

def remaining_needed(counts):
    return {col: max(0, TARGET[col] - counts.get(col,0)) for col in TARGET}

def is_goal(counts):
    return all(counts.get(col,0) >= TARGET[col] for col in TARGET)

def convert_completed_colors_to_brown(board, counts):
    for col in ('yellow','green','red'):
        if counts.get(col,0) >= TARGET[col]:
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if board[r][c] == col:
                        board[r][c] = 'brown'


# ---------------- Candidate generation ----------------
def get_candidate_positions(board, piece):
    results = []

    # Keep your special example logic
    if piece == [(0,0,'red'), (1,0,'green'), (2,0,'brown')]:
        r, c = 3, 0
        tb = copy.deepcopy(board)
        for dy, dx, col in piece:
            tb[r + dy][c + dx] = col
        cleared, cleared_lines = clear_lines(tb)
        results.append((r, c, cleared, cleared_lines, tb))
        return results

    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            ok = True
            for dy, dx, _ in piece:
                rr = r + dy
                cc = c + dx
                if rr < 0 or rr >= BOARD_SIZE or cc < 0 or cc >= BOARD_SIZE:
                    ok = False
                    break
                if board[rr][cc] is not None:
                    ok = False
                    break
            if not ok:
                continue

            tb = copy.deepcopy(board)
            for dy, dx, col in piece:
                tb[r+dy][c+dx] = col
            cleared, cleared_lines = clear_lines(tb)
            results.append((r, c, cleared, cleared_lines, tb))

    return results


# ---------------- Scoring (English Version) ----------------
def board_cluster_potential(board):
    def runs(col):
        s = 0
        # rows
        for r in range(BOARD_SIZE):
            run = 0
            for c in range(BOARD_SIZE):
                if board[r][c] == col:
                    run += 1
                else:
                    if run > 0:
                        s += run * run
                    run = 0
            if run > 0:
                s += run * run
        # columns
        for c in range(BOARD_SIZE):
            run = 0
            for r in range(BOARD_SIZE):
                if board[r][c] == col:
                    run += 1
                else:
                    if run > 0:
                        s += run * run
                    run = 0
            if run > 0:
                s += run * run
        return s

    return (runs('green') + runs('red')) * POTENTIAL_WEIGHT


def score_candidate(piece, r, c, cleared, cleared_lines, board_before, board_after, counts_before):
    rem_g = max(0, TARGET['green'] - counts_before.get('green', 0))
    rem_r = max(0, TARGET['red']   - counts_before.get('red', 0))
    rem_y = max(0, TARGET['yellow']- counts_before.get('yellow', 0))

    gain_g = min(cleared.get('green', 0), rem_g)
    gain_r = min(cleared.get('red',   0), rem_r)
    gain_y = min(cleared.get('yellow',0), rem_y)

    score = 0.0

    # Primary gains (green + red)
    score += WEIGHT_COLOR_PRIMARY * (gain_g + gain_r)
    # Yellow lesser
    score += WEIGHT_COLOR_YELLOW * gain_y

    # Proximity bonus
    rem_g_after = rem_g - gain_g
    rem_r_after = rem_r - gain_r
    score += NEAR_COMPLETE_BONUS_DIV / (rem_g_after + 1)
    score += NEAR_COMPLETE_BONUS_DIV / (rem_r_after + 1)

    # Achievement bonus
    if rem_g_after <= 0:
        score += ACHIEVEMENT_BONUS
    if rem_r_after <= 0:
        score += ACHIEVEMENT_BONUS

    # Overkill penalties
    for col in ('green','red','yellow'):
        used = cleared.get(col, 0)
        rem  = {'green':rem_g, 'red':rem_r, 'yellow':rem_y}[col]
        if used > rem:
            score -= (used - rem) * OVERKILL_PENALTY

    # Column clear penalty
    for typ, idx in cleared_lines:
        if typ == 'c':
            score -= COLUMN_CLEAR_PENALTY

    # Small cluster potential
    score += board_cluster_potential(board_after)

    return score


# ---------------- Simulation + search ----------------
def simulate_permutation_plan(board, counts, pieces, perm):
    initial = (0, copy.deepcopy(board), copy.deepcopy(counts), [])
    stack = [initial]
    best = None
    nodes = 0

    while stack:
        nodes += 1
        if nodes > MAX_DFS_NODES:
            break

        step, bstate, cstate, placements = stack.pop()

        # End of permutation
        if step >= len(perm):
            temp_counts = copy.deepcopy(counts)
            g_step = math.inf
            r_step = math.inf

            for i, pl in enumerate(placements, start=1):
                _, _, _, cleared, _ = pl
                for col in ('green','red','yellow'):
                    temp_counts[col] = temp_counts.get(col,0) + cleared.get(col,0)
                if temp_counts.get('green',0) >= TARGET['green'] and g_step == math.inf:
                    g_step = i
                if temp_counts.get('red',0)   >= TARGET['red']   and r_step == math.inf:
                    r_step = i

            earliest = min(g_step, r_step)

            # leaf scoring
            tmp = copy.deepcopy(counts)
            total_score = 0.0
            total_over = 0

            for _,_,_, cleared,_ in placements:
                for col in ('green','red','yellow'):
                    rem = max(0, TARGET[col] - tmp.get(col,0))
                    used = min(cleared.get(col,0), rem)
                    if col in ('green','red'):
                        total_score += WEIGHT_COLOR_PRIMARY * used
                    else:
                        total_score += WEIGHT_COLOR_YELLOW * used
                    over = max(0, cleared.get(col,0) - rem)
                    total_over += over
                    tmp[col] = tmp.get(col,0) + cleared.get(col,0)

            rem_g_fin = max(0, TARGET['green'] - tmp.get('green',0))
            rem_r_fin = max(0, TARGET['red']   - tmp.get('red',0))

            total_score += NEAR_COMPLETE_BONUS_DIV / (rem_g_fin + 1)
            total_score += NEAR_COMPLETE_BONUS_DIV / (rem_r_fin + 1)
            if rem_g_fin <= 0:
                total_score += ACHIEVEMENT_BONUS
            if rem_r_fin <= 0:
                total_score += ACHIEVEMENT_BONUS

            total_score -= total_over * OVERKILL_PENALTY
            total_score += board_cluster_potential(bstate)

            cand = (earliest, total_score, placements)

            if best is None:
                best = cand
            else:
                br = best
                if (cand[0] < br[0]) or (cand[0] == br[0] and cand[1] > br[1]):
                    best = cand

            continue

        # Not at leaf — expand
        idx = perm[step]
        piece = pieces[idx]
        cands = get_candidate_positions(bstate, piece)

        if not cands:
            new_pl = placements + [(idx, None, None, {'yellow':0,'green':0,'red':0}, [])]
            stack.append((step+1, copy.deepcopy(bstate), copy.deepcopy(cstate), new_pl))
            continue

        scored = []
        for (r,c,cleared, cleared_lines, tb) in cands:
            sc = score_candidate(piece, r, c, cleared, cleared_lines, bstate, tb, cstate)
            scored.append((sc, (r,c,cleared, cleared_lines, tb)))
        scored.sort(reverse=True, key=lambda x: x[0])
        top = scored[:TOP_K_CANDIDATES]

        for sc,(r,c,cleared, cleared_lines, tb) in top:
            nb = copy.deepcopy(tb)
            nc = copy.deepcopy(cstate)
            for col in cleared:
                nc[col] = nc.get(col,0) + cleared[col]
            new_pl = placements + [(idx, r, c, cleared, cleared_lines)]
            stack.append((step+1, nb, nc, new_pl))

    return best


def suggest_best_sequence(board, counts, pieces):
    if not pieces:
        return None

    best_overall = None

    for perm in itertools.permutations(range(len(pieces))):
        res = simulate_permutation_plan(board, counts, pieces, perm)
        if res is None:
            continue

        steps_to_finish, score, placements = res

        if best_overall is None:
            best_overall = (steps_to_finish, score, placements, perm)
        else:
            bo = best_overall
            if (steps_to_finish < bo[0]) or (steps_to_finish == bo[0] and score > bo[1]):
                best_overall = (steps_to_finish, score, placements, perm)

    if best_overall is None:
        return None

    _, _, placements, _ = best_overall

    plan = []
    for (idx, r, c, cleared, cleared_lines) in placements:
        if r is None:
            plan.append((idx, None, cleared))
        else:
            plan.append((idx, (r,c), cleared))

    return plan


# ---------------- UI (English) ----------------
class PieceEditor(tk.Toplevel):
    def __init__(self, master, on_finish, allowed_colors):
        super().__init__(master)
        self.title("Piece Editor")
        self.on_finish = on_finish
        self.allowed_colors = allowed_colors[:]

        self.grid_size = 4
        self.cell = 36
        self.data = [[None]*self.grid_size for _ in range(self.grid_size)]
        self.current_color = tk.StringVar(value=self.allowed_colors[0] if self.allowed_colors else 'brown')

        self.dragging = False
        self.build_ui()

    def build_ui(self):
        top = ttk.Frame(self)
        top.pack(padx=6, pady=6, anchor='w')

        ttk.Label(top, text="Color:").pack(side='left')
        for c in self.allowed_colors:
            ttk.Radiobutton(top, text=c, value=c, variable=self.current_color).pack(side='left', padx=4)

        self.canvas = tk.Canvas(self, width=self.grid_size*self.cell, height=self.grid_size*self.cell, bg='white')
        self.canvas.pack(padx=8, pady=8)

        self.rects = [[None]*self.grid_size for _ in range(self.grid_size)]
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                x1 = c*self.cell
                y1 = r*self.cell
                x2 = x1+self.cell
                y2 = y1+self.cell
                rect = self.canvas.create_rectangle(x1,y1,x2,y2,
                                                    fill=COLOR_HEX[None], outline='gray')
                self.rects[r][c] = rect

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        btnf = ttk.Frame(self)
        btnf.pack(padx=8, pady=6)

        ttk.Button(btnf, text="OK", command=self.finish).pack(side='left', padx=6)
        ttk.Button(btnf, text="Clear", command=self.clear_all).pack(side='left', padx=6)

    def get_coords(self, event):
        c = event.x // self.cell
        r = event.y // self.cell
        if 0 <= r < self.grid_size and 0 <= c < self.grid_size:
            return r, c
        return None, None

    def paint(self, r,c):
        col = self.current_color.get()
        self.data[r][c] = col
        self.canvas.itemconfig(self.rects[r][c], fill=COLOR_HEX[col])

    def on_press(self, e):
        r,c = self.get_coords(e)
        if r is None:
            return
        self.dragging = True
        self.paint(r,c)

    def on_drag(self, e):
        if not self.dragging:
            return
        r,c = self.get_coords(e)
        if r is None:
            return
        self.paint(r,c)

    def on_release(self, e):
        self.dragging = False

    def clear_all(self):
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                self.data[r][c] = None
                self.canvas.itemconfig(self.rects[r][c], fill=COLOR_HEX[None])

    def finish(self):
        blocks = []
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                if self.data[r][c] is not None:
                    blocks.append((r,c,self.data[r][c]))

        if not blocks:
            messagebox.showwarning("Warning", "Piece is empty.")
            return
        if len(blocks) > 4:
            messagebox.showwarning("Warning", "Piece can have at most 4 blocks.")
            return

        minr = min(b[0] for b in blocks)
        minc = min(b[1] for b in blocks)
        rel = [(r-minr, c-minc, col) for r,c,col in blocks]

        self.on_finish(rel)
        self.destroy()


class PuzzleApp:
    def __init__(self, master):
        self.master = master
        master.title("8x8 Block Puzzle Solver")
        master.geometry("1100x640")

        self.cell = 40

        self.board = apply_initial_setup(create_empty_board())
        self.counts = {'yellow':0,'green':0,'red':0}
        self.pieces = []
        self.piece_widgets = []
        self.highlight_rects = []

        self.build_ui()
        self.update_board()
        self.update_counts()

    def build_ui(self):
        left = ttk.Frame(self.master)
        left.pack(side='left', padx=10, pady=10)

        right = ttk.Frame(self.master)
        right.pack(side='right', padx=10, pady=10, fill='y')

        # Board canvas
        self.canvas = tk.Canvas(
            left,
            width=BOARD_SIZE*self.cell,
            height=BOARD_SIZE*self.cell,
            bg='white'
        )
        self.canvas.pack()

        self.rects = [[None]*BOARD_SIZE for _ in range(BOARD_SIZE)]
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                x1 = c*self.cell
                y1 = r*self.cell
                x2 = x1+self.cell
                y2 = y1+self.cell
                rect = self.canvas.create_rectangle(
                    x1,y1,x2,y2,
                    fill=COLOR_HEX[None], outline='gray'
                )
                self.rects[r][c] = rect

        # Right panel
        top_buttons = ttk.Frame(right)
        top_buttons.pack(pady=6)

        ttk.Button(top_buttons, text="Add Piece", command=self.open_piece_editor).pack(side='left', padx=6)
        ttk.Button(top_buttons, text="Reset Board", command=self.reset_board).pack(side='left', padx=6)

        ttk.Button(right, text="Auto Place Pieces", command=self.compute_and_place_all).pack(pady=8)
        ttk.Button(right, text="Show AI Suggestion", command=self.update_ai).pack(pady=2)

        ttk.Label(right, text="Pieces (Preview & Manual Place):").pack(pady=(6,2))

        # Scroll area
        pf_container = ttk.Frame(right)
        pf_container.pack(fill='both', expand=False)

        self.pieces_canvas = tk.Canvas(pf_container, width=520, height=280)
        self.pieces_canvas.pack(side='left', fill='both', expand=True)

        self.pf_scroll = ttk.Scrollbar(pf_container, orient='vertical',
                                       command=self.pieces_canvas.yview)
        self.pf_scroll.pack(side='right', fill='y')

        self.pieces_canvas.configure(yscrollcommand=self.pf_scroll.set)
        self.pieces_frame = ttk.Frame(self.pieces_canvas)
        self.pieces_canvas.create_window((0,0), window=self.pieces_frame, anchor='nw')

        self.pieces_frame.bind(
            "<Configure>",
            lambda e: self.pieces_canvas.configure(scrollregion=self.pieces_canvas.bbox("all"))
        )

        ttk.Label(right, text="Blocks Cleared:").pack(pady=6)
        self.label_counts = tk.Label(right, text="")
        self.label_counts.pack()

        ttk.Label(right, text="AI Suggestion:").pack(pady=6)
        self.label_suggestion = tk.Label(right, text="", justify='left', anchor='w')
        self.label_suggestion.pack(fill='x')

        self.canvas.bind(
            "<ButtonPress-1>",
            lambda e: messagebox.showinfo(
                "Info",
                "Use the piece list below to manually place pieces,\nor click 'Auto Place Pieces'."
            )
        )

    def update_board(self):
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                col = self.board[r][c]
                self.canvas.itemconfig(self.rects[r][c], fill=COLOR_HEX[col])

        for rect in self.highlight_rects:
            try:
                self.canvas.tag_raise(rect)
            except:
                pass

    def update_counts(self):
        txt = (
            f"Yellow: {self.counts['yellow']} / {TARGET['yellow']}    "
            f"Green: {self.counts['green']} / {TARGET['green']}    "
            f"Red: {self.counts['red']} / {TARGET['red']}"
        )
        if is_goal(self.counts):
            txt += "   ✔ Completed!"
        self.label_counts.config(text=txt)

    def open_piece_editor(self):
        rem = remaining_needed(self.counts)
        allowed = ['brown']
        if rem['yellow'] > 0:
            allowed.append('yellow')
        if rem['green'] > 0:
            allowed.append('green')
        if rem['red'] > 0:
            allowed.append('red')

        if not allowed:
            messagebox.showinfo("Info", "All goals already achieved.")
            return

        PieceEditor(self.master, self.add_piece, allowed)

    def add_piece(self, piece):
        self.pieces.append(piece)
        idx = len(self.pieces)-1

        rowf = ttk.Frame(self.pieces_frame, relief='ridge', padding=4)
        rowf.grid(row=idx, column=0, sticky='w', pady=2)

        # Preview
        preview_cell = 14
        minr = min(b[0] for b in piece)
        minc = min(b[1] for b in piece)
        maxr = max(b[0] for b in piece)
        maxc = max(b[1] for b in piece)
        h = maxr - minr + 1
        w = maxc - minc + 1

        canv = tk.Canvas(rowf, width=w*preview_cell+4, height=h*preview_cell+4,
                         bg='white', highlightthickness=1, highlightbackground='gray')
        canv.pack(side='left', padx=4)

        for dy,dx,col in piece:
            rr = dy - minr
            cc = dx - minc
            x1 = cc*preview_cell
            y1 = rr*preview_cell
            x2 = x1+preview_cell
            y2 = y1+preview_cell
            canv.create_rectangle(x1,y1,x2,y2, fill=COLOR_HEX[col], outline='black')

        lbl = ttk.Label(rowf, text=str(piece), width=28, anchor='w')
        lbl.pack(side='left', padx=6)

        btn_place = ttk.Button(rowf, text="Place", command=lambda i=idx: self.place_single_piece(i))
        btn_place.pack(side='left', padx=4)

        btn_delete = ttk.Button(rowf, text="Delete", command=lambda i=idx: self.delete_piece(i))
        btn_delete.pack(side='left', padx=2)

        self.piece_widgets.append((rowf, canv, lbl, btn_place, btn_delete))
        self.pieces_frame.update_idletasks()
        self.pieces_canvas.configure(scrollregion=self.pieces_canvas.bbox("all"))

        self.update_counts()

    def delete_piece(self, idx):
        if idx < 0 or idx >= len(self.pieces):
            return

        w = self.piece_widgets[idx]
        try:
            w[0].destroy()
        except:
            pass

        self.pieces.pop(idx)
        self.piece_widgets.pop(idx)

        for i,(rowf, *_ ) in enumerate(self.piece_widgets):
            rowf.grid_configure(row=i)

        self.update_counts()

    def clear_highlights(self):
        for rect in self.highlight_rects:
            try:
                self.canvas.delete(rect)
            except:
                pass
        self.highlight_rects = []

    def update_ai(self):
        self.clear_highlights()

        if not self.pieces:
            self.label_suggestion.config(text="")
            return

        plan = suggest_best_sequence(self.board, self.counts, self.pieces)

        if not plan:
            self.label_suggestion.config(text="No suggestion found.")
            self.update_board()
            return

        lines = []
        for step, (idx, pos, cleared) in enumerate(plan, start=1):
            if pos:
                r,c = pos
                lines.append(
                    f"{step}: Piece {idx+1} → row {r+1}, col {c+1} "
                    f"(Cleared: Y{cleared.get('yellow',0)} G{cleared.get('green',0)} R{cleared.get('red',0)})"
                )
                rect = self.canvas.create_rectangle(
                    c*self.cell, r*self.cell,
                    (c+1)*self.cell, (r+1)*self.cell,
                    outline=HIGHLIGHT_COLOR, width=2, dash=(3,3)
                )
                self.highlight_rects.append(rect)
            else:
                lines.append(f"{step}: Piece {idx+1} → Cannot place")

        self.label_suggestion.config(text="\n".join(lines))
        self.update_board()

    def place_single_piece(self, idx):
        if idx < 0 or idx >= len(self.pieces):
            messagebox.showinfo("Info", "No piece selected.")
            return

        piece = self.pieces[idx]
        cands = get_candidate_positions(self.board, piece)

        if not cands:
            messagebox.showinfo("Info", "No valid placement for this piece.")
            return

        scored = []
        for (r,c,cleared, cleared_lines, tb) in cands:
            sc = score_candidate(piece, r, c, cleared, cleared_lines, self.board, tb, self.counts)
            scored.append((sc, (r,c,cleared, cleared_lines, tb)))
        scored.sort(reverse=True, key=lambda x: x[0])
        _, best = scored[0]
        r,c,cleared, cleared_lines, tb = best

        # Recheck placeability
        for dy,dx,_ in piece:
            rr = r+dy
            cc = c+dx
            if rr < 0 or rr >= BOARD_SIZE or cc < 0 or cc >= BOARD_SIZE:
                messagebox.showinfo("Info","Invalid placement.")
                return
            if self.board[rr][cc] is not None:
                messagebox.showinfo("Info","That spot is already filled.")
                return

        self.clear_highlights()

        # Place
        for dy,dx,col in piece:
            self.board[r+dy][c+dx] = col

        cleared_now, cleared_lines_now = clear_lines(self.board)
        for k in cleared_now:
            self.counts[k] = self.counts.get(k,0) + cleared_now[k]

        convert_completed_colors_to_brown(self.board, self.counts)

        self.highlight_piece_shape(piece, r, c)

        # Remove from UI list
        try:
            found_idx = None
            for i,p in enumerate(self.pieces):
                if p == piece:
                    found_idx = i
                    break
            if found_idx is not None:
                w = self.piece_widgets[found_idx]
                try:
                    w[0].destroy()
                except:
                    pass
                self.pieces.pop(found_idx)
                self.piece_widgets.pop(found_idx)
                for i,(rowf,*_) in enumerate(self.piece_widgets):
                    rowf.grid_configure(row=i)
        except:
            pass

        self.update_board()
        self.update_counts()
        self.label_suggestion.config(text="")

    def compute_and_place_all(self):
        if not self.pieces:
            messagebox.showinfo("Info", "No pieces added.")
            return

        self.clear_highlights()

        pieces_snapshot = copy.deepcopy(self.pieces)
        plan = suggest_best_sequence(self.board, self.counts, pieces_snapshot)

        if not plan:
            messagebox.showinfo("Info", "No placement plan found.")
            return

        placed_any = False

        for (idx, pos, cleared) in plan:
            piece = pieces_snapshot[idx]
            if pos is None:
                continue

            r,c = pos

            ok = True
            for dy,dx,_ in piece:
                rr = r+dy
                cc = c+dx
                if rr < 0 or rr >= BOARD_SIZE or cc < 0 or cc >= BOARD_SIZE:
                    ok = False
                    break
                if self.board[rr][cc] is not None:
                    ok = False
                    break

            if not ok:
                continue

            # Place
            for dy,dx,col in piece:
                self.board[r+dy][c+dx] = col

            cleared_now, cleared_lines_now = clear_lines(self.board)
            for k in cleared_now:
                self.counts[k] = self.counts.get(k,0) + cleared_now[k]

            convert_completed_colors_to_brown(self.board, self.counts)
            self.highlight_piece_shape(piece, r, c)

            placed_any = True

            # Remove from UI list
            for i,p in enumerate(self.pieces):
                if p == piece:
                    w = self.piece_widgets[i]
                    try:
                        w[0].destroy()
                    except:
                        pass
                    self.pieces.pop(i)
                    self.piece_widgets.pop(i)
                    break

            for i,(rowf,*_) in enumerate(self.piece_widgets):
                rowf.grid_configure(row=i)

        if not placed_any:
            messagebox.showinfo("Info", "No pieces could be placed.")
        self.update_board()
        self.update_counts()
        self.label_suggestion.config(text="")

    def highlight_piece_shape(self, piece, anchor_r, anchor_c):
        for dy,dx,_ in piece:
            rr = anchor_r + dy
            cc = anchor_c + dx
            x1 = cc*self.cell
            y1 = rr*self.cell
            x2 = (cc+1)*self.cell
            y2 = (rr+1)*self.cell

            rect = self.canvas.create_rectangle(
                x1+2, y1+2, x2-2, y2-2,
                outline=HIGHLIGHT_COLOR, width=3
            )
            self.highlight_rects.append(rect)

        for rect in self.highlight_rects:
            try:
                self.canvas.tag_raise(rect)
            except:
                pass

    def reset_board(self):
        self.board = apply_initial_setup(create_empty_board())
        self.counts = {'yellow':0,'green':0,'red':0}
        self.pieces = []

        for w in self.piece_widgets:
            try:
                w[0].destroy()
            except:
                pass
        self.piece_widgets = []

        self.clear_highlights()
        self.update_board()
        self.update_counts()
        self.label_suggestion.config(text="")


# ---------------- main ----------------
def main():
    root = tk.Tk()
    PuzzleApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
