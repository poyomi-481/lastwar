# 📘 **Block Puzzle Solver — User Guide (English Version)**

This tool is a solver for an 8×8 block-puzzle game.
Its goal is to automatically place your custom pieces in a way that clears:

* **10 Yellow**
* **5 Green**
* **5 Red**

using the **fewest possible placements**.

The initial board layout is always fixed, and the internal algorithm tries to find the optimal placement order.

---

# 🚀 **How to Use the Program**

## 1. Download and Extract the ZIP

1. Download `solver.zip`
2. Right-click → **Extract All**
3. Open the extracted folder
4. Double-click **solver.exe**

⚠ **Do not run from inside the ZIP. It must be extracted first.**

---

# 🖥️ **Main Window Overview**

When the application opens, you will see:

* An **8×8 board** on the left
* Piece editing and piece list controls on the right
* Buttons for adding pieces and auto-placement
* Counters for how many Yellow/Green/Red you have cleared so far

---

# 🎨 **Add Piece**

Use this button to create a new block piece that you want to place on the board.

### How to use:

1. Click **Add Piece**
2. A 4×4 editor window appears
3. Select a color and click/drag on cells to paint blocks
4. Each piece may contain **1 to 4 blocks**
5. Once finished, click **OK**

Your new piece will appear in the **Piece List** on the right side.

---

# 🤖 **Auto Place Pieces**

This button runs the solver to automatically place *all* pieces in the list.

### Solver Goal

Place the pieces in a way that clears:

* **5 Greens**
* **5 Reds**
* **10 Yellows**

in the **minimum number of steps**.

### How the solver thinks:

* Green and Red have **equal priority**
* The solver determines which color can reach its target of 5 **faster**, and prioritizes that color
* Yellow is handled after Green/Red
* Over-clearing (using more blocks than needed) is penalized
* Hundreds of placement permutations are evaluated
* The solver chooses the placement order and coordinates that maximize progress

### To use:

1. Add multiple pieces with **Add Piece**
2. Click **Auto Place Pieces**
3. The solver automatically finds the best placement
4. Successfully placed pieces are highlighted on the board
5. Those pieces are removed from the list

If a piece cannot be placed, it is simply skipped.

---

# 🔄 **Reset Board**

Resets:

* The 8×8 board back to its fixed initial layout
* All counters (Yellow/Green/Red)
* All pieces added in the list
* All highlights

Use this when starting a new run.

---

# ❓ **Frequently Asked Questions**

### **Q. Do I need Python installed?**

A. No. This EXE is a standalone application.

### **Q. Windows shows a security warning.**

A. This is normal for downloadable executables.
Click **More Info → Run Anyway**.

### **Q. The app takes several seconds to launch.**

A. Normal. The solver engine initializes on startup.

