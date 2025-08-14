"""
Rock–Paper–Scissors (Tkinter)
Single-file app: no third-party installs required.

Improvements:
- Light/Dark theme toggle (button + 'T' key)
- Animated feedback: flash on win/tie, shake on loss
- Confetti celebration when match is won (widget raise/lower fixed for macOS)
- Streak tracking + simple achievements (First Win, Hot Streak 3)
- Polished ttk styling; keyboard: R/P/S, N, T, Esc
"""

import csv
import random
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_TITLE = "Rock–Paper–Scissors • Tk"
CHOICES = ["Rock", "Paper", "Scissors"]
EMOJI = {"Rock": "🪨", "Paper": "📄", "Scissors": "✂️"}
BEATS = {"Rock": "Scissors", "Paper": "Rock", "Scissors": "Paper"}

class RPSApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=16)
        self.pack(fill="both", expand=True)
        self.master = master

        # ---- State ----
        self.theme = tk.StringVar(value="Light")         # Light | Dark
        self.difficulty = tk.StringVar(value="Adaptive") # Adaptive | Random
        self.best_of = tk.IntVar(value=5)
        self.target_wins = (self.best_of.get() // 2) + 1

        self.user_score = tk.IntVar(value=0)
        self.cpu_score = tk.IntVar(value=0)
        self.tie_count = tk.IntVar(value=0)
        self.rounds = tk.IntVar(value=0)

        self.curr_streak = tk.IntVar(value=0)      # +ve = user streak, -ve = cpu streak
        self.best_user_streak = tk.IntVar(value=0)
        self.best_cpu_streak = tk.IntVar(value=0)

        self.status_text = tk.StringVar(value="Choose your move to begin!")
        self.history = []          # [{"time":..., "user":..., "cpu":..., "result":...}]
        self.user_recent = []      # recent human choices (for Adaptive)
        self.achievements = set()  # session-only simple badges

        # build UI
        self._style()
        self._build_ui()
        self._bind_shortcuts(master)

    # ---------- UI / Style ----------
    def _style(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        if self.theme.get() == "Dark":
            bg, fg, acc, sub = "#0f172a", "#e2e8f0", "#38bdf8", "#1f2937"
        else:
            bg, fg, acc, sub = "#f8fafc", "#0f172a", "#2563eb", "#e5e7eb"

        self.master.configure(bg=bg)
        s = self.style
        s.configure("TFrame", background=bg)
        s.configure("TLabelframe", background=bg, foreground=fg)
        s.configure("TLabelframe.Label", background=bg, foreground=fg)
        s.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 11))
        s.configure("Header.TLabel", background=bg, foreground=fg, font=("Segoe UI", 12, "bold"))
        s.configure("TButton", font=("Segoe UI", 11, "bold"))
        s.map("TButton", foreground=[("active", fg)], background=[("active", acc)])

        # Keep canvases in sync with theme
        if hasattr(self, "confetti"):
            self.confetti.configure(bg=bg)
        if hasattr(self, "result_lbl"):
            self._paint_result("neutral")

    # --- widget stacking helpers (fix for Canvas.raise/lower on macOS) ---
    def _widget_raise(self, w):
        # Raise the widget in the window stacking order (NOT canvas items)
        w.tk.call('raise', w._w)

    def _widget_lower(self, w):
        # Lower the widget behind others
        w.tk.call('lower', w._w)

    def _build_ui(self):
        # Top bar: settings
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0,10))

        ttk.Label(bar, text="Difficulty:").pack(side="left")
        ttk.OptionMenu(bar, self.difficulty, self.difficulty.get(), "Adaptive", "Random").pack(side="left", padx=(4,12))

        ttk.Label(bar, text="Best of:").pack(side="left")
        self.best_spin = ttk.Spinbox(bar, from_=1, to=21, increment=2, width=4,
                                     textvariable=self.best_of, command=self._on_bestof_change)
        self.best_spin.pack(side="left", padx=(4,8))

        ttk.Button(bar, text="New Match (N)", command=self.new_match).pack(side="left", padx=(4,8))
        ttk.Button(bar, text="Export CSV", command=self.export_csv).pack(side="left", padx=(4,8))
        ttk.Button(bar, text="Theme (T)", command=self.toggle_theme).pack(side="right", padx=(8,0))

        # Scoreboard
        sb = ttk.Labelframe(self, text="Scoreboard")
        sb.pack(fill="x", pady=(0,10))
        self._kv(sb, "Rounds", self.rounds).grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self._kv(sb, "You", self.user_score).grid(row=0, column=1, padx=8, pady=6, sticky="w")
        self._kv(sb, "Computer", self.cpu_score).grid(row=0, column=2, padx=8, pady=6, sticky="w")
        self._kv(sb, "Ties", self.tie_count).grid(row=0, column=3, padx=8, pady=6, sticky="w")
        self.target_lbl = ttk.Label(sb, text=f"Target wins: {self.target_wins}", style="Header.TLabel")
        self.target_lbl.grid(row=0, column=4, padx=8, pady=6, sticky="w")

        # Streaks + achievements
        st = ttk.Labelframe(self, text="Streaks & Achievements")
        st.pack(fill="x", pady=(0,10))
        self._kv(st, "Current streak", self.curr_streak, fmt=lambda v: f"{v:+d}").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self._kv(st, "Your best", self.best_user_streak).grid(row=0, column=1, padx=8, pady=6, sticky="w")
        self._kv(st, "CPU best", self.best_cpu_streak).grid(row=0, column=2, padx=8, pady=6, sticky="w")
        self.ach_label = ttk.Label(st, text="Badges: —")
        self.ach_label.grid(row=0, column=3, padx=8, pady=6, sticky="w")

        # Big status/result
        self.result_lbl = ttk.Label(self, textvariable=self.status_text, anchor="center")
        self.result_lbl.pack(fill="x", ipady=8, pady=(0,10))
        self._paint_result("neutral")

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(0,10))
        ttk.Button(btns, text=f"{EMOJI['Rock']}  Rock  (R)", command=lambda: self.play("Rock")).pack(side="left", expand=True, fill="x", padx=4)
        ttk.Button(btns, text=f"{EMOJI['Paper']}  Paper  (P)", command=lambda: self.play("Paper")).pack(side="left", expand=True, fill="x", padx=4)
        ttk.Button(btns, text=f"{EMOJI['Scissors']}  Scissors  (S)", command=lambda: self.play("Scissors")).pack(side="left", expand=True, fill="x", padx=4)
        ttk.Button(btns, text="Reset Match", command=self.reset_match).pack(side="left", padx=4)

        # History panel
        hist = ttk.Labelframe(self, text="Last 10 Rounds")
        hist.pack(fill="both", expand=True)
        self.hist_box = tk.Listbox(hist, height=8)
        self.hist_box.pack(side="left", fill="both", expand=True, padx=(8,0), pady=8)
        ttk.Scrollbar(hist, command=self.hist_box.yview).pack(side="left", fill="y", pady=8)
        self.hist_box.config(yscrollcommand=lambda *args: None)

        # Confetti overlay (celebration)
        self.confetti = tk.Canvas(self, bg=self.master.cget("bg"), bd=0, highlightthickness=0)
        self.confetti.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._widget_lower(self.confetti)  # put behind until needed

    def _kv(self, parent, key, varobj, fmt=str):
        f = ttk.Frame(parent)
        ttk.Label(f, text=f"{key}: ", style="Header.TLabel").pack(side="left")
        lab = ttk.Label(f, text=fmt(varobj.get()) if hasattr(varobj, "get") else fmt(varobj))
        lab.pack(side="left")
        if hasattr(varobj, "trace_add"):
            def update(*_):
                lab.config(text=fmt(varobj.get()))
            varobj.trace_add("write", update)
        return f

    def _bind_shortcuts(self, root):
        root.bind("<Key-r>", lambda e: self.play("Rock"))
        root.bind("<Key-p>", lambda e: self.play("Paper"))
        root.bind("<Key-s>", lambda e: self.play("Scissors"))
        root.bind("<Key-n>", lambda e: self.new_match())
        root.bind("<Key-t>", lambda e: self.toggle_theme())
        root.bind("<Escape>", lambda e: root.destroy())

    # ---------- Theme ----------
    def toggle_theme(self):
        self.theme.set("Dark" if self.theme.get() == "Light" else "Light")
        self._apply_theme_colors()

    # ---------- Game Options ----------
    def _on_bestof_change(self):
        try:
            v = int(self.best_of.get())
        except Exception:
            v = 5
        if v % 2 == 0:
            v += 1  # force odd
            self.best_of.set(v)
        self.target_wins = (v // 2) + 1
        self.target_lbl.config(text=f"Target wins: {self.target_wins}")
        self.status_text.set(f"Match target set to best of {v} — first to {self.target_wins} wins.")
        self._paint_result("neutral")

    # ---------- Game Logic ----------
    def new_match(self):
        self.reset_match()
        self.status_text.set(f"New match started: best of {self.best_of.get()} (first to {self.target_wins}).")
        self._paint_result("neutral")

    def reset_match(self):
        self.user_score.set(0)
        self.cpu_score.set(0)
        self.tie_count.set(0)
        self.rounds.set(0)
        self.curr_streak.set(0)
        self.hist_box.delete(0, "end")
        self.status_text.set("Match reset. Ready!")

    def play(self, user_choice: str):
        if user_choice not in CHOICES:
            return
        cpu_choice = self._cpu_pick()
        result = self._decide(user_choice, cpu_choice)

        # Update scores & streaks
        self.rounds.set(self.rounds.get() + 1)
        if result == "Win":
            self.user_score.set(self.user_score.get() + 1)
            self.curr_streak.set(self.curr_streak.get() + 1 if self.curr_streak.get() >= 0 else 1)
            self.best_user_streak.set(max(self.best_user_streak.get(), self.curr_streak.get()))
        elif result == "Lose":
            self.cpu_score.set(self.cpu_score.get() + 1)
            self.curr_streak.set(self.curr_streak.get() - 1 if self.curr_streak.get() <= 0 else -1)
            self.best_cpu_streak.set(max(self.best_cpu_streak.get(), abs(self.curr_streak.get())))
        else:
            self.tie_count.set(self.tie_count.get() + 1)

        # Save recent human choices for adaptive bot (window 7)
        self.user_recent.append(user_choice)
        if len(self.user_recent) > 7:
            self.user_recent.pop(0)

        # Record history (full history for CSV; listbox shows last 10)
        stamp = datetime.now().strftime("%H:%M:%S")
        rec = {"time": stamp, "user": user_choice, "cpu": cpu_choice, "result": result}
        self.history.append(rec)
        self.hist_box.insert(0, f"[{stamp}] You: {user_choice} {EMOJI[user_choice]}  |  CPU: {cpu_choice} {EMOJI[cpu_choice]}  → {result}")
        if self.hist_box.size() > 10:
            self.hist_box.delete("end")

        # Update status + animations
        if result == "Win":
            self.status_text.set(f"You WIN! {EMOJI[user_choice]} beats {EMOJI[BEATS[user_choice]]}.")
            self._paint_result("win")
            self._unlock("First Win")
            if self.curr_streak.get() >= 3:
                self._unlock("Hot Streak (3)")
        elif result == "Lose":
            self.status_text.set(f"You LOSE. {EMOJI[cpu_choice]} beats {EMOJI[BEATS[cpu_choice]]}.")
            self._paint_result("lose")
            self._shake()  # subtle shake animation
        else:
            self.status_text.set(f"Tie. You both picked {user_choice} {EMOJI[user_choice]}.")
            self._paint_result("tie")

        # Check match winner
        if self.user_score.get() >= self.target_wins or self.cpu_score.get() >= self.target_wins:
            winner = "You" if self.user_score.get() > self.cpu_score.get() else "Computer"
            color = "win" if winner == "You" else "lose"
            self._paint_result(color)
            if winner == "You":
                self._celebrate_confetti()
            messagebox.showinfo("Match complete", f"{winner} won the match!\n\nScore: You {self.user_score.get()} – {self.cpu_score.get()} CPU")
            self.reset_match()

    def _cpu_pick(self) -> str:
        if self.difficulty.get() == "Random" or not self.user_recent:
            return random.choice(CHOICES)
        # Adaptive: predict from recent frequency; counter it with 70% prob
        counts = {c: 0 for c in CHOICES}
        for c in self.user_recent:
            counts[c] += 1
        predicted = max(counts, key=counts.get)
        counter = self._counter_to(predicted)
        return counter if random.random() < 0.7 else random.choice(CHOICES)

    @staticmethod
    def _counter_to(choice: str) -> str:
        for k, v in BEATS.items():
            if v == choice:
                return k
        return random.choice(CHOICES)

    @staticmethod
    def _decide(user: str, cpu: str) -> str:
        if user == cpu:
            return "Tie"
        return "Win" if BEATS[user] == cpu else "Lose"

    # ---------- Visual polish ----------
    def _paint_result(self, mode: str):
        neutral = "#f6f8fa" if self.theme.get() == "Light" else "#111827"
        colors = {
            "win":    "#e6ffed" if self.theme.get() == "Light" else "#064e3b",
            "lose":   "#ffecec" if self.theme.get() == "Light" else "#4c0519",
            "tie":    "#eef2ff" if self.theme.get() == "Light" else "#1e293b",
            "neutral": neutral,
        }
        self.result_lbl.configure(background=colors.get(mode, neutral), anchor="center", padding=8)

    def _shake(self):
        # subtle horizontal shake for loss feedback
        w = self.master
        try:
            orig = w.winfo_x(), w.winfo_y()
        except tk.TclError:
            return
        dx = [0, 8, -8, 6, -6, 4, -4, 2, -2, 0]
        def step(i=0):
            if i >= len(dx):
                try: w.geometry(f"+{orig[0]}+{orig[1]}")
                except tk.TclError: pass
                return
            try:
                w.geometry(f"+{orig[0]+dx[i]}+{orig[1]}")
            except tk.TclError:
                pass
            w.after(14, lambda: step(i+1))
        step()

    def _celebrate_confetti(self, n=120, duration_ms=1000):
        # Simple confetti animation (circles falling) with safe widget stacking
        self._widget_raise(self.confetti)
        self.confetti.delete("all")
        W = self.confetti.winfo_width() or self.winfo_width()
        H = self.confetti.winfo_height() or self.winfo_height()
        rng = random.Random()
        parts = []
        colors = ["#ef4444","#f59e0b","#10b981","#3b82f6","#a855f7","#ec4899","#22d3ee"]
        for _ in range(n):
            x = rng.randint(0, max(W, 10))
            y = -rng.randint(0, 60)
            dx = rng.uniform(-1.2, 1.2)
            dy = rng.uniform(2.0, 5.0)
            r  = rng.randint(2,4)
            item = self.confetti.create_oval(x, y, x+r, y+r, fill=rng.choice(colors), width=0)
            parts.append([item, dx, dy])

        steps = max(1, int(duration_ms / 16))
        def tick(i=0):
            for item, dx, dy in parts:
                self.confetti.move(item, dx, dy)
            if i < steps:
                self.after(16, lambda: tick(i+1))
            else:
                self._widget_lower(self.confetti)
        tick()

    # ---------- Achievements ----------
    def _unlock(self, name: str):
        if name in self.achievements:
            self._refresh_badges()
            return
        self.achievements.add(name)
        self._refresh_badges()
        messagebox.showinfo("Achievement unlocked!", name)

    def _refresh_badges(self):
        if not self.achievements:
            self.ach_label.config(text="Badges: —")
        else:
            self.ach_label.config(text="Badges: " + ", ".join(sorted(self.achievements)))

    # ---------- Export ----------
    def export_csv(self):
        if not self.history:
            messagebox.showinfo("Export CSV", "No rounds played yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files","*.csv"), ("All files","*.*")],
            initialfile=f"rps_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["time","user","cpu","result"])
            w.writeheader()
            w.writerows(self.history)
        messagebox.showinfo("Export CSV", f"Saved round history to:\n{path}")

def main():
    root = tk.Tk()
    root.title(APP_TITLE)
    # Reasonable default size & min size
    root.geometry("760x560")
    root.minsize(660, 500)
    app = RPSApp(root)
    # macOS: bring to front (best effort)
    try:
        root.lift()
        root.call('wm', 'attributes', '.', '-topmost', True)
        root.after(10, lambda: root.call('wm', 'attributes', '.', '-topmost', False))
    except tk.TclError:
        pass
    root.mainloop()

if __name__ == "__main__":
    main()