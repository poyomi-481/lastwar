#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
solver_final_with_buttons_and_previews_v2.py

- ウィンドウ横幅を広げた
- 自動配置ボタン押下前に既存ハイライトを全消去
- 配置後のハイライトを piece の形（各セル単位）で描画
- 個別配置でも同様に古いハイライトを消去して新しいハイライトのみ表示
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

# Preferred rows fixed (0-based)
PREFERRED_ROWS = [3, 4]
# Preferred columns (edge columns)
PREFERRED_COLS = [0, BOARD_SIZE-1]

# Search/pruning parameters
TOP_K_CANDIDATES = 30
MAX_DFS_NODES = 45000

# Weights (intentionally extreme so preferred-row logic dominates)
PREF_ROW_COLOR_WEIGHT = {'green': 9000.0, 'red': 8500.0, 'yellow': 7000.0, 'brown': 10.0}
PREF_COL_COLOR_WEIGHT = 2000.0
COLUMN_DEFICIT_PENALTY_PER_DY = 2000.0
PREFERRED_ROW_CLEAR_BONUS = 12000.0
COLUMN_CLEAR_PENALTY = 10000.0
OVERKILL_PENALTY = 12000.0
POTENTIAL_WEIGHT = 0.5

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
    rows = [r for r in range(BOARD_SIZE) if all(board[r][c] is not None for c in range(BOARD_SIZE))]
    cols = [c for c in range(BOARD_SIZE) if all(board[r][c] is not None for r in range(BOARD_SIZE))]
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
    for (r,c) in to_clear:
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

# ---------------- Candidate generation (no rotation) ----------------
def get_candidate_positions(board, piece):
    candidates = []
    # special-case example preserved
    if piece == [(0,0,'red'), (1,0,'green'), (2,0,'brown')]:
        r, c = 3, 0
        tb = copy.deepcopy(board)
        for dy, dx, col in piece:
            tb[r+dy][c+dx] = col
        cleared, cleared_lines = clear_lines(tb)
        candidates.append((r, c, cleared, cleared_lines, tb))
        return candidates
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            ok = True
            for dy, dx, _ in piece:
                rr = r + dy; cc = c + dx
                if not (0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE) or board[rr][cc] is not None:
                    ok = False; break
            if not ok: continue
            tb = copy.deepcopy(board)
            for dy, dx, col in piece:
                tb[r+dy][c+dx] = col
            cleared, cleared_lines = clear_lines(tb)
            candidates.append((r, c, cleared, cleared_lines, tb))
    return candidates

# ---------------- Scoring helpers ----------------
def board_cluster_potential(board):
    def runs(col):
        s = 0
        for r in range(BOARD_SIZE):
            run = 0
            for c in range(BOARD_SIZE):
                if board[r][c] == col:
                    run += 1
                else:
                    if run > 0:
                        s += run*run
                    run = 0
            if run > 0: s += run*run
        for c in range(BOARD_SIZE):
            run = 0
            for r in range(BOARD_SIZE):
                if board[r][c] == col:
                    run += 1
                else:
                    if run > 0:
                        s += run*run
                    run = 0
            if run > 0: s += run*run
        return s
    return (runs('green') + runs('red')) * POTENTIAL_WEIGHT

def score_candidate_strict(piece, r, c, cleared, cleared_lines, board_before, board_after, counts_before):
    score = 0.0
    pref_blocks_val = 0.0
    for dy,dx,col in piece:
        rr = r + dy
        if rr in PREFERRED_ROWS:
            pref_blocks_val += PREF_ROW_COLOR_WEIGHT.get(col, 50.0)
    score += pref_blocks_val
    pref_col_val = 0.0
    for dy,dx,col in piece:
        cc = c + dx
        if cc in PREFERRED_COLS:
            pref_col_val += PREF_COL_COLOR_WEIGHT
    score += pref_col_val
    vert_pen = sum(abs(dy) * COLUMN_DEFICIT_PENALTY_PER_DY for dy,dx,_ in piece)
    score -= vert_pen
    clear_bonus = 0.0; clear_penalty = 0.0
    for typ, idx in cleared_lines:
        if typ == 'r':
            clear_bonus += PREFERRED_ROW_CLEAR_BONUS if idx in PREFERRED_ROWS else 100.0
        else:
            clear_penalty += COLUMN_CLEAR_PENALTY
    score += clear_bonus - clear_penalty
    for col in ('green','red','yellow'):
        used = cleared.get(col, 0)
        rem = max(0, TARGET[col] - counts_before.get(col, 0))
        if used > rem:
            score -= (used - rem) * OVERKILL_PENALTY
    score += board_cluster_potential(board_after)
    return score

# ---------------- Simulation & search (unchanged) ----------------
def simulate_permutation_plan(board, counts, pieces, perm):
    initial = (0, copy.deepcopy(board), copy.deepcopy(counts), [])
    best = None
    nodes = 0
    stack = [initial]
    while stack:
        nodes += 1
        if nodes > MAX_DFS_NODES:
            break
        step, bstate, cstate, placements = stack.pop()
        if step >= len(perm):
            temp_counts = copy.deepcopy(counts)
            step_reached = math.inf
            for i, pl in enumerate(placements, start=1):
                _,__,___, cleared, _ = pl
                for col in ('green','red','yellow'):
                    temp_counts[col] = temp_counts.get(col,0) + cleared.get(col,0)
                if temp_counts.get('green',0) >= TARGET['green'] and temp_counts.get('red',0) >= TARGET['red'] and step_reached == math.inf:
                    step_reached = i
            if step_reached is math.inf:
                step_reached = math.inf
            total_pref_value = 0.0; total_over = 0
            tmp = copy.deepcopy(counts)
            for _,_,_, cleared, _ in placements:
                for col in ('green','red','yellow'):
                    used = min(cleared.get(col,0), max(0, TARGET[col] - tmp.get(col,0)))
                    total_pref_value += used * 10.0
                    over = max(0, cleared.get(col,0) - max(0, TARGET[col] - tmp.get(col,0)))
                    total_over += over
                    tmp[col] = tmp.get(col,0) + cleared.get(col,0)
            score = total_pref_value - total_over * OVERKILL_PENALTY + board_cluster_potential(bstate)
            cand = (step_reached, score, placements)
            if best is None:
                best = cand
            else:
                br = best
                if cand[0] < br[0] or (cand[0] == br[0] and cand[1] > br[1]):
                    best = cand
            continue

        idx = perm[step]
        piece = pieces[idx]
        cands = get_candidate_positions(bstate, piece)
        if not cands:
            new_placements = placements + [(idx, None, None, {'yellow':0,'green':0,'red':0}, [])]
            stack.append((step+1, copy.deepcopy(bstate), copy.deepcopy(cstate), new_placements))
            continue

        scored = []
        for (r,c,cleared, cleared_lines, tb) in cands:
            sc = score_candidate_strict(piece, r, c, cleared, cleared_lines, bstate, tb, cstate)
            scored.append((sc, (r,c,cleared, cleared_lines, tb)))
        scored.sort(reverse=True, key=lambda x: x[0])
        top = scored[:TOP_K_CANDIDATES]
        for sc, (r,c,cleared, cleared_lines, tb) in top:
            nb = copy.deepcopy(tb)
            nc = copy.deepcopy(cstate)
            for col in cleared:
                nc[col] = nc.get(col,0) + cleared[col]
            new_placements = placements + [(idx, r, c, cleared, cleared_lines)]
            stack.append((step+1, nb, nc, new_placements))
    return best

def suggest_best_sequence(board, counts, pieces):
    if not pieces:
        return None
    best_overall = None
    for perm in itertools.permutations(range(len(pieces))):
        res = simulate_permutation_plan(board, counts, pieces, perm)
        if res is None:
            continue
        steps_to_pref, score, placements = res
        if best_overall is None:
            best_overall = (steps_to_pref, score, placements, perm)
        else:
            bo = best_overall
            if steps_to_pref < bo[0] or (steps_to_pref == bo[0] and score > bo[1]):
                best_overall = (steps_to_pref, score, placements, perm)
    if best_overall is None:
        return None
    _, _, placements, _ = best_overall
    plan = []
    for (idx, r, c, cleared, cleared_lines) in placements:
        plan.append((idx, (r,c) if r is not None else None, cleared))
    return plan

# ---------------- UI ----------------
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
        self._build()

    def _build(self):
        top = ttk.Frame(self); top.pack(padx=6,pady=6, anchor='w')
        ttk.Label(top, text="色:").pack(side='left')
        for c in self.allowed_colors:
            ttk.Radiobutton(top, text=c, value=c, variable=self.current_color).pack(side='left', padx=4)
        self.canvas = tk.Canvas(self, width=self.grid_size*self.cell, height=self.grid_size*self.cell, bg='white')
        self.canvas.pack(padx=8,pady=8)
        self.rects = [[None]*self.grid_size for _ in range(self.grid_size)]
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                x1 = c*self.cell; y1 = r*self.cell; x2 = x1+self.cell; y2 = y1+self.cell
                rect = self.canvas.create_rectangle(x1,y1,x2,y2, fill=COLOR_HEX[None], outline='gray')
                self.rects[r][c] = rect
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        btnf = ttk.Frame(self); btnf.pack(padx=8,pady=6)
        ttk.Button(btnf, text="確定", command=self._finish).pack(side='left', padx=6)
        ttk.Button(btnf, text="クリア", command=self._clear).pack(side='left', padx=6)

    def _coords(self, event):
        c = event.x // self.cell; r = event.y // self.cell
        if 0 <= r < self.grid_size and 0 <= c < self.grid_size:
            return r,c
        return None, None

    def _paint(self, r,c):
        col = self.current_color.get()
        self.data[r][c] = col
        self.canvas.itemconfig(self.rects[r][c], fill=COLOR_HEX[col])

    def _press(self, e):
        r,c = self._coords(e)
        if r is None: return
        self.dragging = True
        self._paint(r,c)
    def _drag(self, e):
        if not self.dragging: return
        r,c = self._coords(e)
        if r is None: return
        self._paint(r,c)
    def _release(self, e):
        self.dragging = False
    def _clear(self):
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                self.data[r][c] = None
                self.canvas.itemconfig(self.rects[r][c], fill=COLOR_HEX[None])
    def _finish(self):
        blocks = []
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                if self.data[r][c] is not None:
                    blocks.append((r,c,self.data[r][c]))
        if not blocks:
            messagebox.showwarning("警告","ピースが空です")
            return
        if len(blocks) > 4:
            messagebox.showwarning("警告","ピースは最大4つまで")
            return
        minr = min(b[0] for b in blocks); minc = min(b[1] for b in blocks)
        rel = [(r-minr, c-minc, col) for r,c,col in blocks]
        self.on_finish(rel)
        self.destroy()

class PuzzleApp:
    def __init__(self, master):
        self.master = master
        master.title("8x8 Block Puzzle — solver_final (Preferred Rows Max)")
        # make window wider
        master.geometry("1100x640")
        self.cell = 40
        self.board = apply_initial_setup(create_empty_board())
        self.counts = {'yellow':0,'green':0,'red':0}
        self.pieces = []
        self.piece_widgets = []
        self.highlight_rects = []
        self._build_ui()
        self.update_board()
        self.update_counts()

    def _build_ui(self):
        left = ttk.Frame(self.master); left.pack(side='left', padx=10, pady=10)
        right = ttk.Frame(self.master); right.pack(side='right', padx=10, pady=10, fill='y')
        self.canvas = tk.Canvas(left, width=BOARD_SIZE*self.cell, height=BOARD_SIZE*self.cell, bg='white')
        self.canvas.pack()
        self.rects = [[None]*BOARD_SIZE for _ in range(BOARD_SIZE)]
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                x1 = c*self.cell; y1 = r*self.cell; x2 = x1+self.cell; y2 = y1+self.cell
                rect = self.canvas.create_rectangle(x1,y1,x2,y2, fill=COLOR_HEX[None], outline='gray')
                self.rects[r][c] = rect
        for pr in PREFERRED_ROWS:
            self.canvas.create_rectangle(0, pr*self.cell, BOARD_SIZE*self.cell, (pr+1)*self.cell, outline='#1E90FF', width=2)
        for pc in PREFERRED_COLS:
            self.canvas.create_rectangle(pc*self.cell, 0, (pc+1)*self.cell, BOARD_SIZE*self.cell, outline='#1E90FF', width=2)

        # Right panel
        btnf = ttk.Frame(right); btnf.pack(pady=6)
        ttk.Button(btnf, text="Piece Editor", command=self.open_piece_editor).pack(side='left', padx=6)
        ttk.Button(btnf, text="Reset Board", command=self.reset_board).pack(side='left', padx=6)
        ttk.Button(right, text="計算して自動配置", command=self.compute_and_place_all).pack(pady=8)

        ttk.Label(right, text="ピース一覧（プレビュー & 個別配置）").pack(pady=(6,2))
        # piece list area (wider)
        pf_container = ttk.Frame(right)
        pf_container.pack(fill='both', expand=False)
        self.pieces_canvas = tk.Canvas(pf_container, width=520, height=280)
        self.pieces_canvas.pack(side='left', fill='both', expand=True)
        self.pf_scroll = ttk.Scrollbar(pf_container, orient='vertical', command=self.pieces_canvas.yview)
        self.pf_scroll.pack(side='right', fill='y')
        self.pieces_canvas.configure(yscrollcommand=self.pf_scroll.set)
        self.pieces_frame = ttk.Frame(self.pieces_canvas)
        self.pieces_canvas.create_window((0,0), window=self.pieces_frame, anchor='nw')
        self.pieces_frame.bind("<Configure>", lambda e: self.pieces_canvas.configure(scrollregion=self.pieces_canvas.bbox("all")))

        ttk.Label(right, text="消したブロック数").pack(pady=6)
        self.label_counts = tk.Label(right, text="")
        self.label_counts.pack()
        ttk.Label(right, text="AI提案（押すと計算します）").pack(pady=6)
        self.label_suggestion = tk.Label(right, text="", justify='left', anchor='w')
        self.label_suggestion.pack(fill='x')

        # small help tooltip on canvas click
        self.canvas.bind("<ButtonPress-1>", lambda e: messagebox.showinfo("Info","ピース一覧の個別配置ボタンか、上の「計算して自動配置」を押してください。"))

    def update_board(self):
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                col = self.board[r][c]
                self.canvas.itemconfig(self.rects[r][c], fill=COLOR_HEX[col])
        # ensure highlights on top
        for rect in self.highlight_rects:
            try: self.canvas.tag_raise(rect)
            except: pass

    def update_counts(self):
        txt = f"黄: {self.counts['yellow']} / {TARGET['yellow']}   緑: {self.counts['green']} / {TARGET['green']}   赤: {self.counts['red']} / {TARGET['red']}"
        if is_goal(self.counts):
            txt += "   🎉 クリア！"
        self.label_counts.config(text=txt)

    def open_piece_editor(self):
        rem = remaining_needed(self.counts)
        allowed = ['brown']
        if rem['yellow'] > 0: allowed.append('yellow')
        if rem['green'] > 0: allowed.append('green')
        if rem['red'] > 0: allowed.append('red')
        if not allowed:
            messagebox.showinfo("Info","すべての目標が達成済みです。")
            return
        PieceEditor(self.master, self.add_piece, allowed)

    def add_piece(self, piece):
        self.pieces.append(piece)
        idx = len(self.pieces)-1
        rowf = ttk.Frame(self.pieces_frame, relief='ridge', padding=4)
        rowf.grid(row=idx, column=0, sticky='w', pady=2)
        preview_cell = 14
        minr = min(b[0] for b in piece); minc = min(b[1] for b in piece)
        maxr = max(b[0] for b in piece); maxc = max(b[1] for b in piece)
        h = maxr - minr + 1; w = maxc - minc + 1
        canv = tk.Canvas(rowf, width=w*preview_cell+4, height=h*preview_cell+4, bg='white', highlightthickness=1, highlightbackground='gray')
        canv.pack(side='left', padx=4)
        for dy,dx,col in piece:
            rr = dy - minr; cc = dx - minc
            x1 = cc*preview_cell; y1 = rr*preview_cell; x2 = x1+preview_cell; y2 = y1+preview_cell
            canv.create_rectangle(x1,y1,x2,y2, fill=COLOR_HEX[col], outline='black')
        txt = str(piece)
        lbl = ttk.Label(rowf, text=txt, width=28, anchor='w')
        lbl.pack(side='left', padx=6)
        btn_place = ttk.Button(rowf, text="このピースを配置", command=lambda i=idx: self.place_single_piece_ui(i))
        btn_place.pack(side='left', padx=4)
        btn_delete = ttk.Button(rowf, text="削除", command=lambda i=idx: self.delete_piece_ui(i))
        btn_delete.pack(side='left', padx=2)
        self.piece_widgets.append((rowf, canv, lbl, btn_place, btn_delete))
        self.pieces_frame.update_idletasks()
        self.pieces_canvas.configure(scrollregion=self.pieces_canvas.bbox("all"))
        self.update_counts()

    def delete_piece_ui(self, idx):
        if idx < 0 or idx >= len(self.pieces): return
        w = self.piece_widgets[idx]
        try: w[0].destroy()
        except: pass
        self.pieces.pop(idx)
        self.piece_widgets.pop(idx)
        for i, (rowf, *_ ) in enumerate(self.piece_widgets):
            rowf.grid_configure(row=i)
        self.update_counts()

    def clear_highlights(self):
        for rect in self.highlight_rects:
            try: self.canvas.delete(rect)
            except: pass
        self.highlight_rects = []

    def update_ai(self):
        # display suggestion (does not auto-place)
        self.clear_highlights()
        if not self.pieces:
            self.label_suggestion.config(text="")
            return
        plan = suggest_best_sequence(self.board, self.counts, self.pieces)
        if not plan:
            self.label_suggestion.config(text="配置提案なし")
            self.update_board()
            return
        lines = []
        for step, (idx, pos, cleared) in enumerate(plan, start=1):
            if pos:
                r,c = pos
                lines.append(f"{step}: ピース{idx+1} → 行{r+1} 列{c+1}（消去: Y{cleared.get('yellow',0)} G{cleared.get('green',0)} R{cleared.get('red',0)}）")
                rect = self.canvas.create_rectangle(c*self.cell, r*self.cell, (c+1)*self.cell, (r+1)*self.cell, outline=HIGHLIGHT_COLOR, width=2, dash=(3,3))
                self.highlight_rects.append(rect)
            else:
                lines.append(f"{step}: ピース{idx+1} → 配置不可/消去0")
        self.label_suggestion.config(text="\n".join(lines))
        self.update_board()

    def place_single_piece_ui(self, idx):
        if idx < 0 or idx >= len(self.pieces):
            messagebox.showinfo("Info","ピースが選択されていません。")
            return
        piece = self.pieces[idx]
        cands = get_candidate_positions(self.board, piece)
        if not cands:
            messagebox.showinfo("配置不可","配置可能な場所がありません。")
            return
        scored = []
        for (r,c,cleared, cleared_lines, tb) in cands:
            sc = score_candidate_strict(piece, r, c, cleared, cleared_lines, self.board, tb, self.counts)
            scored.append((sc, (r,c,cleared, cleared_lines, tb)))
        scored.sort(reverse=True, key=lambda x: x[0])
        _, best = scored[0]
        r,c,cleared, cleared_lines, tb = best
        ok = True
        for dy,dx,_ in piece:
            rr = r + dy; cc = c + dx
            if not (0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE) or self.board[rr][cc] is not None:
                ok = False; break
        if not ok:
            messagebox.showinfo("配置不可","提案位置に配置できません（既に塞がれています）。")
            return
        # clear previous highlights (user requested)
        self.clear_highlights()
        # place
        for dy,dx,col in piece:
            self.board[r+dy][c+dx] = col
        cleared_counts, cleared_lines2 = clear_lines(self.board)
        for k in cleared_counts:
            self.counts[k] = self.counts.get(k,0) + cleared_counts[k]
        convert_completed_colors_to_brown(self.board, self.counts)
        # highlight piece shape (per-cell)
        self.highlight_piece_shape(piece, r, c)
        # remove piece from lists & UI
        try:
            found_idx = None
            for i,p in enumerate(self.pieces):
                if p == piece:
                    found_idx = i; break
            if found_idx is not None:
                w = self.piece_widgets[found_idx]
                try: w[0].destroy()
                except: pass
                self.pieces.pop(found_idx)
                self.piece_widgets.pop(found_idx)
                for i, (rowf, *_ ) in enumerate(self.piece_widgets):
                    rowf.grid_configure(row=i)
        except Exception as e:
            print("警告: ピース削除で問題:", e)
        self.update_board()
        self.update_counts()
        self.label_suggestion.config(text="")

    def compute_and_place_all(self):
        if not self.pieces:
            messagebox.showinfo("Info","追加されたピースがありません。")
            return
        # clear previous highlights before auto placement (user requested)
        self.clear_highlights()
        pieces_snapshot = copy.deepcopy(self.pieces)
        plan = suggest_best_sequence(self.board, self.counts, pieces_snapshot)
        if not plan:
            messagebox.showinfo("Info","配置提案が見つかりませんでした。")
            return
        placed_any = False
        # iterate and place; keep highlights for the pieces placed in this run
        for (idx, pos, cleared) in plan:
            piece = pieces_snapshot[idx]
            if pos is None:
                continue
            r,c = pos
            can_place = True
            for dy,dx,_ in piece:
                rr = r + dy; cc = c + dx
                if not (0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE) or self.board[rr][cc] is not None:
                    can_place = False; break
            if not can_place:
                continue
            for dy,dx,col in piece:
                self.board[r+dy][c+dx] = col
            cleared_counts, cleared_lines2 = clear_lines(self.board)
            for k in cleared_counts:
                self.counts[k] = self.counts.get(k,0) + cleared_counts[k]
            convert_completed_colors_to_brown(self.board, self.counts)
            # highlight piece shape (per-cell)
            self.highlight_piece_shape(piece, r, c)
            placed_any = True
            # remove first matching piece from UI list
            for i,p in enumerate(self.pieces):
                if p == piece:
                    try:
                        w = self.piece_widgets[i]
                        w[0].destroy()
                    except:
                        pass
                    self.pieces.pop(i)
                    self.piece_widgets.pop(i)
                    break
            for i, (rowf, *_ ) in enumerate(self.piece_widgets):
                rowf.grid_configure(row=i)
        if not placed_any:
            messagebox.showinfo("Info","条件により配置できるピースはありませんでした。")
        self.update_board()
        self.update_counts()
        self.label_suggestion.config(text="")

    def highlight_piece_shape(self, piece, anchor_r, anchor_c):
        """
        Highlight each cell of the placed piece so the highlight matches piece shape.
        """
        # for each block cell, draw a rect with thicker outline (no fill) so shape is clear
        for dy,dx,_ in piece:
            rr = anchor_r + dy; cc = anchor_c + dx
            x1 = cc * self.cell; y1 = rr * self.cell
            x2 = (cc+1) * self.cell; y2 = (rr+1) * self.cell
            rect = self.canvas.create_rectangle(x1+2, y1+2, x2-2, y2-2, outline=HIGHLIGHT_COLOR, width=3)
            self.highlight_rects.append(rect)
        # raise highlights above board cells
        for rect in self.highlight_rects:
            try: self.canvas.tag_raise(rect)
            except: pass

    def reset_board(self):
        self.board = apply_initial_setup(create_empty_board())
        self.counts = {'yellow':0,'green':0,'red':0}
        self.pieces = []
        for w in self.piece_widgets:
            try: w[0].destroy()
            except: pass
        self.piece_widgets = []
        self.clear_highlights()
        self.update_board()
        self.update_counts()
        self.label_suggestion.config(text="")

# ---------------- main ----------------
def main():
    root = tk.Tk()
    app = PuzzleApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
