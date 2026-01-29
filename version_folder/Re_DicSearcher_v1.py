import tkinter as tk
from tkinter import filedialog, ttk
import json
import os
import sys
import time

# --- 設定・定数 (Black & Lime Green) ---
DEFAULT_FILE = "dictionary_data.json"

# カラーパレット
COLOR_BG = "#000000"           # 背景: 黒
COLOR_FG = "#00FF00"           # 文字: ライムグリーン
COLOR_FG_DIM = "#008800"       # 控えめな緑
COLOR_INPUT_BG = "#111111"     # 入力欄背景
COLOR_INPUT_FG = "#FFFFFF"     # 入力文字
COLOR_ACCENT = "#006600"       # ボタン背景
COLOR_ACCENT_HOVER = "#009900" 
COLOR_ERROR = "#CC0000"        # エラー表示

# フォント
FONT_MAIN = ("Consolas", 11)   
FONT_BOLD = ("Consolas", 11, "bold")
FONT_TITLE = ("Consolas", 14, "bold")
FONT_LOG = ("Consolas", 10)

# 品詞リスト
PART_OF_SPEECH_LIST = [
    "N(名詞)", "V(動詞)", "Adj(形容詞)", "Adv(副詞)", 
    "Conj(接続詞)", "Prep(前置詞)", "Pro(代名詞)", 
    "Det(限定詞)", "Aux(助動詞)", "Part(助詞)", "Num(数詞)", "Other"
]

def resource_path(relative_path):
    """PyInstaller対応のリソースパス解決"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ModernDictApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Re.DicSearcher [v1.0]")
        self.root.geometry("950x700")
        self.root.configure(bg=COLOR_BG)
        self.root.withdraw() # スプラッシュ表示中は隠す

        # データ管理
        self.data = {} 
        self.filepath = DEFAULT_FILE
        self.current_mode = "read" 
        
        # ★追加: 検索モード管理変数
        self.search_mode = tk.StringVar(value="contains") # contains, startswith, endswith

        # スプラッシュスクリーン表示
        self.show_splash()

    def show_splash(self):
        """起動画面を表示"""
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.attributes('-topmost', True)
        
        w, h = 500, 300
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        splash.geometry(f"{w}x{h}+{x}+{y}")
        splash.configure(bg=COLOR_BG)

        # 枠線
        tk.Frame(splash, bg=COLOR_FG, width=w, height=2).pack(side=tk.TOP)
        tk.Frame(splash, bg=COLOR_FG, width=w, height=2).pack(side=tk.BOTTOM)
        tk.Frame(splash, bg=COLOR_FG, width=2, height=h).place(x=0, y=0)
        tk.Frame(splash, bg=COLOR_FG, width=2, height=h).place(x=w-2, y=0)

        # ロゴ・テキスト
        content = tk.Frame(splash, bg=COLOR_BG)
        content.pack(expand=True)
        
        try:
            # 画像があれば表示 (Pillowが必要)
            from PIL import Image, ImageTk
            img_path = resource_path("logo.png")
            if os.path.exists(img_path):
                raw_img = Image.open(img_path)
                raw_img.thumbnail((120, 120))
                img = ImageTk.PhotoImage(raw_img)
                lbl = tk.Label(content, image=img, bg=COLOR_BG)
                lbl.image = img
                lbl.pack(pady=10)
            else:
                tk.Label(content, text="📚", font=("Segoe UI Emoji", 60), bg=COLOR_BG, fg=COLOR_FG).pack()
        except:
            tk.Label(content, text="[DICTIONARY]", font=FONT_TITLE, bg=COLOR_BG, fg=COLOR_FG).pack(pady=10)

        tk.Label(content, text="INITIALIZING SYSTEM...", font=FONT_BOLD, bg=COLOR_BG, fg=COLOR_FG).pack(pady=5)
        
        # プログレスバー風アニメーション
        self.loading_lbl = tk.Label(content, text="", font=("Consolas", 10), bg=COLOR_BG, fg=COLOR_FG)
        self.loading_lbl.pack()

        def finish_load():
            splash.destroy()
            self.root.deiconify() # メインウィンドウ表示
            self.setup_ui()       # UI構築
            self.load_data_logic(self.filepath) # データ読み込み

        # 簡易アニメーション
        def update_loading(count=0):
            chars = ["|", "/", "-", "\\"]
            self.loading_lbl.config(text=f"LOADING DATA MODULE {chars[count % 4]}")
            if count < 15: # 約1.5秒
                splash.after(100, update_loading, count+1)
            else:
                finish_load()

        update_loading()

    def setup_ui(self):
        # --- 1. ヘッダー (ファイル & モード) ---
        header_frame = tk.Frame(self.root, bg=COLOR_BG, pady=10, padx=10)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        tk.Button(header_frame, text="📂 FILE LOAD", command=self.open_file_dialog,
                  bg="#333333", fg="white", relief="flat", padx=10).pack(side=tk.LEFT)
        
        self.lbl_filename = tk.Label(header_frame, text="[No File]", bg=COLOR_BG, fg="gray", font=("Consolas", 9))
        self.lbl_filename.pack(side=tk.LEFT, padx=10)

        self.btn_mode = tk.Button(header_frame, text="MODE: READ 📖", command=self.toggle_mode,
                                  bg=COLOR_ACCENT, fg="white", relief="flat", padx=15, font=FONT_BOLD)
        self.btn_mode.pack(side=tk.RIGHT)

        # --- 2. メインエリア ---
        self.content_frame = tk.Frame(self.root, bg=COLOR_BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 閲覧・編集用コンテナ
        self.frame_read = tk.Frame(self.content_frame, bg=COLOR_BG)
        self.setup_read_mode()
        self.frame_write = tk.Frame(self.content_frame, bg=COLOR_BG)
        self.setup_write_mode()

        self.frame_read.pack(fill=tk.BOTH, expand=True) # 初期は閲覧モード

        # --- 3. メッセージログエリア (埋め込み型) ---
        log_container = tk.Frame(self.root, bg=COLOR_BG, padx=10, pady=10)
        log_container.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(log_container, text="--- SYSTEM LOG / MESSAGE ---", font=("Consolas", 9), 
                 bg=COLOR_BG, fg=COLOR_FG_DIM).pack(anchor="w")

        # スクロール付きテキストボックス
        self.log_text = tk.Text(log_container, height=4, bg="#050505", fg=COLOR_FG, 
                                font=FONT_LOG, state="disabled", relief="solid", bd=1)
        self.log_text.pack(fill=tk.X)
        
        # 起動メッセージ
        self.log("System initialized. Ready.")

    # =========================================
    # 閲覧モード (READ MODE)
    # =========================================
    def setup_read_mode(self):
        # 検索バー
        search_frame = tk.Frame(self.frame_read, bg=COLOR_BG, pady=5)
        search_frame.pack(fill=tk.X)
        
        tk.Label(search_frame, text="SEARCH >", bg=COLOR_BG, fg=COLOR_FG, font=FONT_BOLD).pack(side=tk.LEFT)
        self.entry_search = tk.Entry(search_frame, bg=COLOR_INPUT_BG, fg=COLOR_FG, 
                                     insertbackground=COLOR_FG, font=FONT_MAIN, relief="flat")
        self.entry_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, ipady=3)
        self.entry_search.bind('<KeyRelease>', self.on_search)

        # ★追加: 検索モード選択ラジオボタン
        opt_frame = tk.Frame(search_frame, bg=COLOR_BG)
        opt_frame.pack(side=tk.LEFT, padx=10)

        modes = [("含む", "contains"), ("前方一致", "startswith"), ("後方一致", "endswith")]
        for text, mode in modes:
            rb = tk.Radiobutton(opt_frame, text=text, variable=self.search_mode, value=mode,
                                bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG, activebackground=COLOR_BG,
                                font=("Consolas", 9), command=self.on_search)
            rb.pack(side=tk.LEFT, padx=2)

        # リストと詳細
        paned = tk.PanedWindow(self.frame_read, orient=tk.HORIZONTAL, bg=COLOR_BG, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, pady=5)

        # 左：リスト + 並び替えボタン
        left_group = tk.Frame(paned, bg=COLOR_BG)
        paned.add(left_group, minsize=280)

        # 並び替えボタン用フレーム
        order_frame = tk.Frame(left_group, bg=COLOR_BG)
        order_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 2))

        tk.Button(order_frame, text="▲", command=self.move_up, bg="#222222", fg=COLOR_FG, relief="flat", width=2).pack(side=tk.TOP, pady=2)
        tk.Button(order_frame, text="▼", command=self.move_down, bg="#222222", fg=COLOR_FG, relief="flat", width=2).pack(side=tk.TOP, pady=2)

        # リストボックス
        self.listbox = tk.Listbox(left_group, bg="#080808", fg=COLOR_FG, 
                                  selectbackground=COLOR_ACCENT, selectforeground="white",
                                  font=FONT_MAIN, borderwidth=1, relief="solid")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.show_detail)

        sb = tk.Scrollbar(left_group, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)

        # 右：詳細
        detail_frame = tk.Frame(paned, bg=COLOR_BG, padx=15)
        paned.add(detail_frame, minsize=400)

        self.lbl_detail_term = tk.Label(detail_frame, text="", font=("Consolas", 20, "bold"), bg=COLOR_BG, fg="white", anchor="w")
        self.lbl_detail_term.pack(fill=tk.X, pady=(0, 10))

        self.detail_text = tk.Text(detail_frame, bg=COLOR_BG, fg="#DDDDDD", font=FONT_MAIN, 
                                   height=15, state="disabled", relief="flat", wrap="word")
        self.detail_text.pack(fill=tk.BOTH, expand=True)

    # =========================================
    # 書き込みモード (WRITE MODE)
    # =========================================
    def setup_write_mode(self):
        tk.Label(self.frame_write, text="--- EDITOR / REGISTRATION ---", font=FONT_TITLE, bg=COLOR_BG, fg=COLOR_FG).pack(anchor="w", pady=(0, 15))

        self.entries = {}
        
        def create_row(label, key):
            tk.Label(self.frame_write, text=f"■ {label}", font=FONT_BOLD, bg=COLOR_BG, fg=COLOR_FG_DIM).pack(anchor="w")
            entry = tk.Entry(self.frame_write, bg=COLOR_INPUT_BG, fg=COLOR_INPUT_FG, 
                             insertbackground=COLOR_FG, font=FONT_MAIN, relief="flat")
            entry.pack(fill=tk.X, pady=(0, 10), ipady=5)
            self.entries[key] = entry

        create_row("単語 (Term)", "term")
        create_row("発音 (Pronunciation)", "pronunciation")

        # 品詞 (OptionMenu)
        tk.Label(self.frame_write, text="■ 品詞 (Part of Speech)", font=FONT_BOLD, bg=COLOR_BG, fg=COLOR_FG_DIM).pack(anchor="w")
        self.pos_var = tk.StringVar(value=PART_OF_SPEECH_LIST[0])
        pos_menu = tk.OptionMenu(self.frame_write, self.pos_var, *PART_OF_SPEECH_LIST)
        pos_menu.config(bg=COLOR_INPUT_BG, fg=COLOR_FG, activebackground=COLOR_ACCENT, 
                        activeforeground="white", highlightthickness=0, relief="flat", font=FONT_MAIN)
        pos_menu["menu"].config(bg=COLOR_INPUT_BG, fg=COLOR_FG, font=FONT_MAIN)
        pos_menu.pack(fill=tk.X, pady=(0, 10), ipady=3)

        create_row("意味 (Meaning)", "meaning")
        create_row("使用例 (Example)", "example")

        # ボタン
        btn_box = tk.Frame(self.frame_write, bg=COLOR_BG, pady=15)
        btn_box.pack(fill=tk.X)

        tk.Button(btn_box, text="💾 SAVE", command=self.save_entry,
                  bg=COLOR_ACCENT, fg="white", font=FONT_BOLD, relief="flat", padx=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_box, text="CLEAR", command=self.clear_form,
                  bg="#444444", fg="white", font=FONT_MAIN, relief="flat", padx=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_box, text="🗑 DELETE", command=self.delete_entry,
                  bg=COLOR_ERROR, fg="white", font=FONT_MAIN, relief="flat", padx=10).pack(side=tk.RIGHT)

    # =========================================
    # ログ出力システム
    # =========================================
    def log(self, message, level="info"):
        """画面下のログエリアにメッセージを表示"""
        self.log_text.config(state="normal")
        
        timestamp = time.strftime("[%H:%M:%S]")
        
        tag = "info"
        if level == "error": tag = "error"
        elif level == "warn": tag = "warn"
        elif level == "success": tag = "success"

        self.log_text.tag_config("info", foreground=COLOR_FG)
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("warn", foreground="yellow")
        self.log_text.tag_config("success", foreground="#AAFFAA")

        self.log_text.insert(tk.END, f"{timestamp} ", "info")
        self.log_text.insert(tk.END, f"{message}\n", tag)
        self.log_text.see(tk.END) 
        self.log_text.config(state="disabled")

    # =========================================
    # ファイル操作 & データロジック
    # =========================================
    def open_file_dialog(self):
        filename = filedialog.askopenfilename(
            title="Load JSON", filetypes=[("JSON", "*.json"), ("All", "*.*")], initialdir=os.getcwd()
        )
        if filename:
            self.load_data_logic(filename)

    def load_data_logic(self, filepath):
        if not os.path.exists(filepath):
            self.log(f"File not found: {os.path.basename(filepath)}. Starting new.", "warn")
            self.data = {}
            self.filepath = filepath
            self.lbl_filename.config(text=f"[{os.path.basename(filepath)}]")
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = json.load(f)

            if isinstance(content, list):
                self.data = {}
                for item in content:
                    key = item.get("term", item.get("word", "Unknown"))
                    self.data[key] = {
                        "pronunciation": item.get("pronunciation", ""),
                        "pos": item.get("part_of_speech", item.get("pos", "")),
                        "meaning": item.get("definition", item.get("meaning", "")),
                        "example": item.get("example", "")
                    }
                self.log(f"Converted list-format file to dictionary format.", "warn")
            elif isinstance(content, dict):
                self.data = content
            else:
                self.data = {}

            self.filepath = filepath
            self.lbl_filename.config(text=f"[{os.path.basename(filepath)}]")
            self.log(f"Loaded {len(self.data)} items from {os.path.basename(filepath)}.", "success")
            self.refresh_list()
        
        except Exception as e:
            self.log(f"Load Error: {e}", "error")
            self.data = {}

    def save_data(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
            self.log(f"Data saved to {os.path.basename(self.filepath)}", "success")
        except Exception as e:
            self.log(f"Save Error: {e}", "error")

    # =========================================
    # 並び替え & リスト操作 (★検索ロジック更新)
    # =========================================
    def refresh_list(self, query=""):
        self.listbox.delete(0, tk.END)
        query = query.lower()
        mode = self.search_mode.get() # 現在の検索モード取得
        
        # 辞書のキー順序（挿入順・並び替え後）に従って表示
        for word in self.data.keys():
            w_lower = word.lower()
            match = False
            
            # 検索ロジック分岐
            if not query:
                match = True
            elif mode == "contains" and query in w_lower:
                match = True
            elif mode == "startswith" and w_lower.startswith(query):
                match = True
            elif mode == "endswith" and w_lower.endswith(query):
                match = True
            
            if match:
                self.listbox.insert(tk.END, word)

    def move_up(self):
        """選択した単語を一つ上に移動"""
        if self.entry_search.get(): 
            self.log("Clear search before reordering.", "warn")
            return

        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        
        if idx > 0:
            keys = list(self.data.keys())
            keys[idx], keys[idx-1] = keys[idx-1], keys[idx]
            new_data = {k: self.data[k] for k in keys}
            self.data = new_data
            
            self.save_data() 
            self.refresh_list()
            self.listbox.selection_set(idx-1)
            self.listbox.see(idx-1)
            self.log(f"Moved '{keys[idx-1]}' up.", "info")

    def move_down(self):
        """選択した単語を一つ下に移動"""
        if self.entry_search.get(): 
            self.log("Clear search before reordering.", "warn")
            return

        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        keys = list(self.data.keys())

        if idx < len(keys) - 1:
            keys[idx], keys[idx+1] = keys[idx+1], keys[idx]
            new_data = {k: self.data[k] for k in keys}
            self.data = new_data
            
            self.save_data()
            self.refresh_list()
            self.listbox.selection_set(idx+1)
            self.listbox.see(idx+1)
            self.log(f"Moved '{keys[idx+1]}' down.", "info")

    # =========================================
    # 編集・削除
    # =========================================
    def save_entry(self):
        term = self.entries["term"].get().strip()
        if not term:
            self.log("Term is required.", "warn")
            return

        is_new = term not in self.data
        
        self.data[term] = {
            "pronunciation": self.entries["pronunciation"].get().strip(),
            "pos": self.pos_var.get(),
            "meaning": self.entries["meaning"].get().strip(),
            "example": self.entries["example"].get().strip()
        }
        
        self.save_data()
        self.refresh_list(self.entry_search.get())
        
        if is_new:
            self.log(f"Registered new term: {term}", "success")
        else:
            self.log(f"Updated term: {term}", "success")

    def delete_entry(self):
        term = self.entries["term"].get().strip()
        if term in self.data:
            del self.data[term]
            self.save_data()
            self.clear_form()
            self.refresh_list(self.entry_search.get())
            self.log(f"Deleted term: {term}", "warn")
        else:
            self.log("Term not found to delete.", "error")

    def on_search(self, event=None):
        self.refresh_list(self.entry_search.get())

    def show_detail(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        word = self.listbox.get(sel[0])
        d = self.data.get(word, {})

        self.lbl_detail_term.config(text=word)
        content = f"【発音】 {d.get('pronunciation','')}\n【品詞】 {d.get('pos','')}\n\n【意味】\n{d.get('meaning','')}\n\n【例文】\n{d.get('example','')}"
        
        self.detail_text.config(state="normal")
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.insert(tk.END, content)
        self.detail_text.config(state="disabled")

        if self.current_mode == "write":
            self.fill_form(word)

    def fill_form(self, word):
        d = self.data.get(word, {})
        self.clear_form()
        self.entries["term"].insert(0, word)
        self.entries["pronunciation"].insert(0, d.get("pronunciation", ""))
        self.entries["meaning"].insert(0, d.get("meaning", ""))
        self.entries["example"].insert(0, d.get("example", ""))
        if d.get("pos"): self.pos_var.set(d.get("pos"))

    def clear_form(self):
        for e in self.entries.values(): e.delete(0, tk.END)
        self.pos_var.set(PART_OF_SPEECH_LIST[0])

    def toggle_mode(self):
        if self.current_mode == "read":
            self.frame_read.pack_forget()
            self.frame_write.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "write"
            self.btn_mode.config(text="MODE: WRITE ✎", bg="#444444")
            try:
                sel = self.listbox.curselection()
                if sel: self.fill_form(self.listbox.get(sel[0]))
            except: pass
        else:
            self.frame_write.pack_forget()
            self.frame_read.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "read"
            self.btn_mode.config(text="MODE: READ 📖", bg=COLOR_ACCENT)

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass

    root = tk.Tk()
    app = ModernDictApp(root)
    root.mainloop()