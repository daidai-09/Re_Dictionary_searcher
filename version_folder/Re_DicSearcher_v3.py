import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sqlite3
import json
import os
import sys
import time
import re # 正規表現モジュールを追加

# ==========================================
#  設定・定数
# ==========================================
DB_FILE = "dictionary.db"

THEMES = {
    "Dark": {
        "bg": "#000000", "fg": "#00FF00", "fg_dim": "#008800",
        "input_bg": "#111111", "input_fg": "#FFFFFF",
        "accent": "#006600", "accent_hover": "#009900",
        "list_bg": "#080808", "list_fg": "#00FF00",
        "select_bg": "#006600", "select_fg": "#FFFFFF",
        "log_fg_info": "#00FF00", "log_fg_err": "#FF0000",
        "btn_bg": "#333333", "btn_fg": "#FFFFFF",
        "link_fg": "#00FFFF" # リンク色(シアン)
    },
    "Light": {
        "bg": "#F0F0F0", "fg": "#000000", "fg_dim": "#555555",
        "input_bg": "#FFFFFF", "input_fg": "#000000",
        "accent": "#4CAF50", "accent_hover": "#45a049",
        "list_bg": "#FFFFFF", "list_fg": "#000000",
        "select_bg": "#4CAF50", "select_fg": "#FFFFFF",
        "log_fg_info": "#000000", "log_fg_err": "#FF0000",
        "btn_bg": "#DDDDDD", "btn_fg": "#000000",
        "link_fg": "#0000FF" # リンク色(青)
    }
}

PART_OF_SPEECH_LIST = [
    "N(名詞)", "V(動詞)", "Adj(形容詞)", "Adv(副詞)", 
    "Conj(接続詞)", "Prep(前置詞)", "Pro(代名詞)", 
    "Det(限定詞)", "Aux(助動詞)", "Part(助詞)", "Num(数詞)", "Other"
]

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ==========================================
#  データベース管理クラス
# ==========================================
class DatabaseManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_file)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    term TEXT UNIQUE,
                    pronunciation TEXT,
                    pos TEXT,
                    meaning TEXT,
                    example TEXT,
                    sort_order INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    def get_all_words(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dictionary ORDER BY sort_order ASC")
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def upsert_word(self, data):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM dictionary WHERE term = ?", (data['term'],))
            exists = cursor.fetchone()
            if exists:
                cursor.execute("""
                    UPDATE dictionary SET pronunciation=?, pos=?, meaning=?, example=? WHERE term=?
                """, (data['pronunciation'], data['pos'], data['meaning'], data['example'], data['term']))
                return "updated"
            else:
                cursor.execute("SELECT MAX(sort_order) FROM dictionary")
                max_order = cursor.fetchone()[0]
                new_order = 1 if max_order is None else max_order + 1
                cursor.execute("""
                    INSERT INTO dictionary (term, pronunciation, pos, meaning, example, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (data['term'], data['pronunciation'], data['pos'], data['meaning'], data['example'], new_order))
                return "created"

    def delete_word(self, term):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM dictionary WHERE term = ?", (term,))

    def update_order(self, term1, order1, term2, order2):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE dictionary SET sort_order = ? WHERE term = ?", (order1, term1))
            cursor.execute("UPDATE dictionary SET sort_order = ? WHERE term = ?", (order2, term2))
            conn.commit()

    def get_setting(self, key, default=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            res = cursor.fetchone()
            return res[0] if res else default

    def set_setting(self, key, value):
        with self.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

# ==========================================
#  メインアプリケーション
# ==========================================
class ReDicSearcherApp:
    def __init__(self, root):
        self.root = root
        self.root.geometry("950x750")
        self.root.withdraw() 

        self.db = DatabaseManager(DB_FILE)
        
        self.current_theme_name = self.db.get_setting("theme", "Dark")
        self.splash_style = self.db.get_setting("splash_style", "Classic")
        
        self.colors = THEMES[self.current_theme_name]
        self.search_mode = tk.StringVar(value="contains")
        self.data_cache = []
        self.widgets = {}
        
        self.apply_theme_to_root()
        self.setup_shortcuts() # ショートカット設定
        self.show_splash()

    def apply_theme_to_root(self):
        self.root.configure(bg=self.colors["bg"])
        self.root.title(f"Re.DicSearcher v3.0 [{self.current_theme_name}]")

    # ==========================================
    #  ショートカットキー設定 (v3.0)
    # ==========================================
    def setup_shortcuts(self):
        # Ctrl + F : 検索バーにフォーカス
        self.root.bind('<Control-f>', lambda e: self.focus_search())
        # Ctrl + S : 保存 (Writeモード時)
        self.root.bind('<Control-s>', lambda e: self.save_entry())
        # Ctrl + M : モード切替
        self.root.bind('<Control-m>', lambda e: self.toggle_mode())
        # Ctrl + N : クリア/新規 (Writeモード時)
        self.root.bind('<Control-n>', lambda e: self.clear_form())

    def focus_search(self):
        if self.current_mode == "read":
            self.entry_search.focus_set()
            self.entry_search.select_range(0, tk.END)

    # ==========================================
    #  スプラッシュスクリーン
    # ==========================================
    def show_splash(self):
        if self.splash_style == "Modern": self.show_splash_modern()
        else: self.show_splash_classic()

    def show_splash_modern(self):
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.attributes('-topmost', True)
        w, h = 500, 300
        x = (self.root.winfo_screenwidth()//2) - (w//2)
        y = (self.root.winfo_screenheight()//2) - (h//2)
        splash.geometry(f"{w}x{h}+{x}+{y}")
        splash.configure(bg=self.colors["bg"])
        try:
            from PIL import Image, ImageTk
            img_path = resource_path("logo.png")
            if os.path.exists(img_path):
                raw = Image.open(img_path)
                raw.thumbnail((100, 100))
                img = ImageTk.PhotoImage(raw)
                lbl = tk.Label(splash, image=img, bg=self.colors["bg"])
                lbl.image = img
                lbl.pack(pady=20)
            else: raise Exception
        except:
            tk.Label(splash, text="Re.Dic", font=("Consolas", 40, "bold"), bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=20)
        tk.Label(splash, text="LOADING SYSTEM...", font=("Consolas", 10), bg=self.colors["bg"], fg=self.colors["fg"]).pack(side=tk.BOTTOM, pady=20)
        splash.after(1500, lambda: self.startup_sequence(splash))

    def show_splash_classic(self):
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.attributes('-topmost', True)
        w, h = 500, 300
        x = (self.root.winfo_screenwidth()//2) - (w//2)
        y = (self.root.winfo_screenheight()//2) - (h//2)
        splash.geometry(f"{w}x{h}+{x}+{y}")
        splash.configure(bg=self.colors["bg"])
        tk.Frame(splash, bg=self.colors["fg"], width=w, height=2).pack(side=tk.TOP)
        tk.Frame(splash, bg=self.colors["fg"], width=w, height=2).pack(side=tk.BOTTOM)
        tk.Frame(splash, bg=self.colors["fg"], width=2, height=h).place(x=0, y=0)
        tk.Frame(splash, bg=self.colors["fg"], width=2, height=h).place(x=w-2, y=0)
        content = tk.Frame(splash, bg=self.colors["bg"])
        content.pack(expand=True)
        tk.Label(content, text="[DICTIONARY SYSTEM]", font=("Consolas", 16, "bold"), bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=10)
        tk.Label(content, text="INITIALIZING...", font=("Consolas", 12, "bold"), bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=5)
        loading_lbl = tk.Label(content, text="", font=("Consolas", 12), bg=self.colors["bg"], fg=self.colors["fg"])
        loading_lbl.pack(pady=10)
        def update_loading(count=0):
            chars = ["|", "/", "-", "\\"]
            loading_lbl.config(text=f"LOADING MODULES {chars[count % 4]}")
            if count < 18: splash.after(80, update_loading, count+1)
            else: self.startup_sequence(splash)
        update_loading()

    def startup_sequence(self, splash):
        self.data_cache = self.db.get_all_words()
        self.setup_ui()
        splash.destroy()
        self.root.deiconify()
        self.log(f"System ready. {len(self.data_cache)} words loaded.", "success")

    def setup_ui(self):
        self.widgets = {}
        # Header
        header = tk.Frame(self.root, bg=self.colors["bg"], pady=10, padx=10)
        header.pack(fill=tk.X)
        self.widgets["header_frame"] = header
        self.btn_import = tk.Button(header, text="📂 IMPORT", command=self.import_json_dialog, relief="flat", padx=10)
        self.btn_import.pack(side=tk.LEFT, padx=(0, 5))
        self.widgets["btn_import"] = self.btn_import
        self.btn_config = tk.Button(header, text="⚙ CONFIG", command=self.open_config_dialog, relief="flat", padx=10)
        self.btn_config.pack(side=tk.LEFT)
        self.widgets["btn_config"] = self.btn_config
        self.btn_mode = tk.Button(header, text="MODE: READ (Ctrl+M)", command=self.toggle_mode, relief="flat", padx=15, font=("Consolas", 11, "bold"))
        self.btn_mode.pack(side=tk.RIGHT)
        self.widgets["btn_mode"] = self.btn_mode

        # Content
        self.content_frame = tk.Frame(self.root, bg=self.colors["bg"])
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.widgets["content_frame"] = self.content_frame
        self.frame_read = tk.Frame(self.content_frame, bg=self.colors["bg"])
        self.setup_read_mode()
        self.frame_write = tk.Frame(self.content_frame, bg=self.colors["bg"])
        self.setup_write_mode()
        self.current_mode = "read"
        self.frame_read.pack(fill=tk.BOTH, expand=True)

        # Log
        log_frame = tk.Frame(self.root, bg=self.colors["bg"], padx=10, pady=10)
        log_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.widgets["log_frame"] = log_frame
        self.lbl_log_title = tk.Label(log_frame, text="--- SYSTEM LOG ---", font=("Consolas", 9))
        self.lbl_log_title.pack(anchor="w")
        self.widgets["lbl_log_title"] = self.lbl_log_title
        self.log_text = tk.Text(log_frame, height=4, font=("Consolas", 10), state="disabled", relief="solid", bd=1)
        self.log_text.pack(fill=tk.X)
        self.widgets["log_text"] = self.log_text

        self.apply_theme_to_widgets()
        self.refresh_list()

    def setup_read_mode(self):
        self.widgets["frame_read"] = self.frame_read
        search_frame = tk.Frame(self.frame_read, bg=self.colors["bg"], pady=5)
        search_frame.pack(fill=tk.X)
        self.widgets["search_frame"] = search_frame
        lbl_search = tk.Label(search_frame, text="SEARCH >", font=("Consolas", 11, "bold"))
        lbl_search.pack(side=tk.LEFT)
        self.widgets["lbl_search"] = lbl_search
        self.entry_search = tk.Entry(search_frame, font=("Consolas", 11), relief="flat")
        self.entry_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, ipady=3)
        self.entry_search.bind('<KeyRelease>', self.on_search)
        self.widgets["entry_search"] = self.entry_search
        
        opt_frame = tk.Frame(search_frame, bg=self.colors["bg"])
        opt_frame.pack(side=tk.LEFT)
        self.widgets["opt_frame"] = opt_frame
        self.radios = []
        for text, mode in [("In", "contains"), ("Start", "startswith"), ("End", "endswith")]:
            rb = tk.Radiobutton(opt_frame, text=text, variable=self.search_mode, value=mode,
                                command=self.on_search, font=("Consolas", 9), selectcolor=self.colors["bg"])
            rb.pack(side=tk.LEFT)
            self.radios.append(rb)

        paned = tk.PanedWindow(self.frame_read, orient=tk.HORIZONTAL, bg=self.colors["bg"], sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, pady=5)
        self.widgets["paned"] = paned
        left_group = tk.Frame(paned, bg=self.colors["bg"])
        paned.add(left_group, minsize=280)
        self.widgets["left_group"] = left_group
        order_frame = tk.Frame(left_group, bg=self.colors["bg"])
        order_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.widgets["order_frame"] = order_frame
        self.btn_up = tk.Button(order_frame, text="▲", command=self.move_up, relief="flat", width=2)
        self.btn_up.pack(side=tk.TOP, pady=2)
        self.btn_down = tk.Button(order_frame, text="▼", command=self.move_down, relief="flat", width=2)
        self.btn_down.pack(side=tk.TOP, pady=2)
        self.widgets["btn_up"] = self.btn_up
        self.widgets["btn_down"] = self.btn_down
        
        self.listbox = tk.Listbox(left_group, font=("Consolas", 11), borderwidth=1, relief="solid")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.show_detail)
        self.widgets["listbox"] = self.listbox
        sb = tk.Scrollbar(left_group, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)

        detail_frame = tk.Frame(paned, bg=self.colors["bg"], padx=15)
        paned.add(detail_frame, minsize=400)
        self.widgets["detail_frame"] = detail_frame
        self.lbl_detail_term = tk.Label(detail_frame, text="", font=("Consolas", 20, "bold"), anchor="w")
        self.lbl_detail_term.pack(fill=tk.X, pady=(0, 10))
        self.widgets["lbl_detail_term"] = self.lbl_detail_term
        self.detail_text = tk.Text(detail_frame, font=("Consolas", 11), height=15, state="disabled", relief="flat", wrap="word")
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        self.widgets["detail_text"] = self.detail_text

    def setup_write_mode(self):
        self.widgets["frame_write"] = self.frame_write
        self.entry_labels = []
        self.entries = {}
        lbl_title = tk.Label(self.frame_write, text="EDITOR / REGISTRATION", font=("Consolas", 14, "bold"), anchor="w")
        lbl_title.pack(pady=(0, 15))
        self.widgets["lbl_write_title"] = lbl_title
        def create_row(label, key):
            lbl = tk.Label(self.frame_write, text=f"■ {label}", font=("Consolas", 10, "bold"), anchor="w")
            lbl.pack(anchor="w")
            self.entry_labels.append(lbl)
            ent = tk.Entry(self.frame_write, font=("Consolas", 11), relief="flat")
            ent.pack(fill=tk.X, pady=(0, 10), ipady=5)
            self.entries[key] = ent
            self.widgets[f"entry_{key}"] = ent
        create_row("単語 (Term)", "term")
        create_row("発音 (Pronunciation)", "pronunciation")
        lbl_pos = tk.Label(self.frame_write, text="■ 品詞 (Part of Speech)", font=("Consolas", 10, "bold"), anchor="w")
        lbl_pos.pack(anchor="w")
        self.entry_labels.append(lbl_pos)
        self.pos_var = tk.StringVar(value=PART_OF_SPEECH_LIST[0])
        self.pos_menu = tk.OptionMenu(self.frame_write, self.pos_var, *PART_OF_SPEECH_LIST)
        self.pos_menu.config(relief="flat", highlightthickness=0, font=("Consolas", 11))
        self.pos_menu.pack(fill=tk.X, pady=(0, 10), ipady=3)
        self.widgets["pos_menu"] = self.pos_menu
        create_row("意味 (Meaning)", "meaning")
        create_row("使用例 (Example)", "example")
        btn_box = tk.Frame(self.frame_write, bg=self.colors["bg"], pady=15)
        btn_box.pack(fill=tk.X)
        self.widgets["btn_box"] = btn_box
        self.btn_save = tk.Button(btn_box, text="💾 SAVE (Ctrl+S)", command=self.save_entry, relief="flat", padx=20, font=("Consolas", 10, "bold"))
        self.btn_save.pack(side=tk.LEFT, padx=5)
        self.widgets["btn_save"] = self.btn_save
        self.btn_clear = tk.Button(btn_box, text="CLEAR (Ctrl+N)", command=self.clear_form, relief="flat", padx=10)
        self.btn_clear.pack(side=tk.LEFT, padx=5)
        self.widgets["btn_clear"] = self.btn_clear
        self.btn_delete = tk.Button(btn_box, text="🗑 DELETE", command=self.delete_entry, relief="flat", padx=10)
        self.btn_delete.pack(side=tk.RIGHT)
        self.widgets["btn_delete"] = self.btn_delete

    # ==========================================
    #  ロジック (リンク機能追加)
    # ==========================================
    def show_detail(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        term = self.listbox.get(sel[0])
        item = next((x for x in self.data_cache if x['term'] == term), None)
        if not item: return

        self.lbl_detail_term.config(text=term)
        content = f"【発音】 {item['pronunciation']}\n【品詞】 {item['pos']}\n\n【意味】\n{item['meaning']}\n\n【例文】\n{item['example']}"
        
        self.detail_text.config(state="normal")
        self.detail_text.delete(1.0, tk.END)
        
        # --- リンク解析と表示 ---
        pattern = re.compile(r'\[(.*?)\]') # [単語] を探す正規表現
        last_pos = 0
        for match in pattern.finditer(content):
            # リンクの前のテキスト
            self.detail_text.insert(tk.END, content[last_pos:match.start()])
            
            # リンク部分
            link_word = match.group(1)
            # リンクタグを追加して挿入 (タグ名は 'link_単語名' とする)
            tag_name = f"link_{link_word}"
            self.detail_text.insert(tk.END, link_word, ("hyperlink", tag_name))
            
            # イベントバインド (クロージャの問題回避のため default arg を使用)
            def on_link_click(event, word=link_word):
                self.jump_to_word(word)
                
            self.detail_text.tag_bind(tag_name, "<Button-1>", on_link_click)
            self.detail_text.tag_bind(tag_name, "<Enter>", lambda e: self.detail_text.config(cursor="hand2"))
            self.detail_text.tag_bind(tag_name, "<Leave>", lambda e: self.detail_text.config(cursor=""))

            last_pos = match.end()
            
        # 残りのテキスト
        self.detail_text.insert(tk.END, content[last_pos:])
        
        # リンクの見た目設定
        self.detail_text.tag_config("hyperlink", foreground=self.colors.get("link_fg", "blue"), underline=1)
        
        self.detail_text.config(state="disabled")

        if self.current_mode == "write": self.fill_form(item)

    def jump_to_word(self, word):
        """リンクをクリックしたときのジャンプ処理"""
        # リストにあるか確認
        items = self.listbox.get(0, tk.END)
        try:
            # 大文字小文字を区別せず検索
            idx = -1
            for i, item in enumerate(items):
                if item.lower() == word.lower():
                    idx = i
                    break
            
            if idx != -1:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(idx)
                self.listbox.see(idx)
                self.listbox.event_generate("<<ListboxSelect>>") # イベント発火
                self.log(f"Jumped to link: {word}", "info")
            else:
                self.log(f"Link not found: {word}", "warn")
        except Exception as e:
            print(e)

    # --- Config Dialog, Theme, Import, Save/Delete, etc... (変更なしor微調整) ---
    def open_config_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Settings")
        dlg.geometry("400x300")
        c = self.colors
        dlg.configure(bg=c["bg"])
        dlg.transient(self.root); dlg.grab_set()
        tk.Label(dlg, text="CONFIGURATION", font=("Consolas", 14, "bold"), bg=c["bg"], fg=c["fg"]).pack(pady=15)
        
        frame_theme = tk.LabelFrame(dlg, text="UI Theme", font=("Consolas", 10), bg=c["bg"], fg=c["fg_dim"], relief="solid", bd=1)
        frame_theme.pack(fill=tk.X, padx=20, pady=5)
        self.var_theme = tk.StringVar(value=self.current_theme_name)
        def on_change(): self.apply_temp_theme(self.var_theme.get(), dlg, rbs)
        rb1 = tk.Radiobutton(frame_theme, text="Dark", variable=self.var_theme, value="Dark", command=on_change, bg=c["bg"], fg=c["fg"], selectcolor=c["bg"], font=("Consolas", 10))
        rb2 = tk.Radiobutton(frame_theme, text="Light", variable=self.var_theme, value="Light", command=on_change, bg=c["bg"], fg=c["fg"], selectcolor=c["bg"], font=("Consolas", 10))
        rb1.pack(side=tk.LEFT, padx=20); rb2.pack(side=tk.LEFT, padx=20)
        
        frame_splash = tk.LabelFrame(dlg, text="Splash Screen", font=("Consolas", 10), bg=c["bg"], fg=c["fg_dim"], relief="solid", bd=1)
        frame_splash.pack(fill=tk.X, padx=20, pady=5)
        self.var_splash = tk.StringVar(value=self.splash_style)
        rb3 = tk.Radiobutton(frame_splash, text="Classic", variable=self.var_splash, value="Classic", bg=c["bg"], fg=c["fg"], selectcolor=c["bg"], font=("Consolas", 10))
        rb4 = tk.Radiobutton(frame_splash, text="Modern", variable=self.var_splash, value="Modern", bg=c["bg"], fg=c["fg"], selectcolor=c["bg"], font=("Consolas", 10))
        rb3.pack(side=tk.LEFT, padx=20); rb4.pack(side=tk.LEFT, padx=20)
        rbs = [rb1, rb2, rb3, rb4]
        
        def save():
            self.db.set_setting("theme", self.var_theme.get())
            self.db.set_setting("splash_style", self.var_splash.get())
            self.current_theme_name = self.var_theme.get()
            self.splash_style = self.var_splash.get()
            self.colors = THEMES[self.current_theme_name]
            self.apply_theme_to_root()
            self.apply_theme_to_widgets()
            self.log("Config Saved.", "success")
            dlg.destroy()
        tk.Button(dlg, text="SAVE & CLOSE", command=save, bg=c["accent"], fg="white", font=("Consolas", 10, "bold"), relief="flat", padx=15).pack(pady=20)
        self.apply_temp_theme(self.current_theme_name, dlg, rbs)

    def apply_temp_theme(self, theme_name, dlg, rbs):
        c = THEMES[theme_name]
        dlg.configure(bg=c["bg"])
        for child in dlg.winfo_children():
            if isinstance(child, (tk.LabelFrame, tk.Label, tk.Frame)): child.configure(bg=c["bg"])
            if hasattr(child, "cget") and "fg" in child.keys(): child.configure(fg=c["fg"])
        for rb in rbs: rb.configure(bg=c["bg"], fg=c["fg"], selectcolor=c["bg"], activebackground=c["bg"])

    def toggle_mode(self):
        if self.current_mode == "read":
            self.frame_read.pack_forget()
            self.frame_write.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "write"
            self.btn_mode.config(text="MODE: WRITE (Ctrl+M)")
            try:
                sel = self.listbox.curselection()
                if sel:
                    term = self.listbox.get(sel[0])
                    item = next((x for x in self.data_cache if x['term'] == term), None)
                    if item: self.fill_form(item)
            except: pass
        else:
            self.frame_write.pack_forget()
            self.frame_read.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "read"
            self.btn_mode.config(text="MODE: READ (Ctrl+M)")

    def apply_theme_to_widgets(self):
        c = self.colors
        # Common
        for name, w in self.widgets.items():
            if "frame" in name or "group" in name or "box" in name: w.configure(bg=c["bg"])
            if "lbl" in name: w.configure(bg=c["bg"], fg=c["fg"])
            if "entry" in name: w.configure(bg=c["input_bg"], fg=c["input_fg"], insertbackground=c["fg"])
        
        for lbl in self.entry_labels: lbl.configure(bg=c["bg"], fg=c["fg_dim"])
        
        btn_bg = c.get("btn_bg", "#333333"); btn_fg = c.get("btn_fg", "#FFFFFF")
        for btn in [self.btn_import, self.btn_config, self.btn_up, self.btn_down]: btn.configure(bg=btn_bg, fg=c["fg"])
        self.btn_mode.configure(bg=c["accent"], fg="#FFFFFF")
        self.btn_save.configure(bg=c["accent"], fg="#FFFFFF")
        self.btn_clear.configure(bg="#444444" if self.current_theme_name=="Dark" else "#AAAAAA", fg="#FFFFFF")
        self.btn_delete.configure(bg="#CC0000", fg="#FFFFFF")
        
        self.listbox.configure(bg=c["list_bg"], fg=c["list_fg"], selectbackground=c["select_bg"], selectforeground=c["select_fg"])
        self.detail_text.configure(bg=c["bg"], fg=c["fg"])
        self.log_text.configure(bg="#050505" if self.current_theme_name=="Dark" else "#FFFFFF", fg=c["fg"])
        for rb in self.radios: rb.configure(bg=c["bg"], fg=c["fg"], selectcolor=c["bg"], activebackground=c["bg"], activeforeground=c["fg"])
        self.pos_menu.configure(bg=c["input_bg"], fg=c["fg"], activebackground=c["accent"], activeforeground="#FFFFFF")
        self.pos_menu["menu"].configure(bg=c["input_bg"], fg=c["fg"])

    # Other logic
    def log(self, message, level="info"):
        self.log_text.config(state="normal")
        c = self.colors
        self.log_text.tag_config("info", foreground=c["log_fg_info"])
        self.log_text.tag_config("error", foreground=c["log_fg_err"])
        self.log_text.tag_config("success", foreground=c["accent"])
        self.log_text.tag_config("warn", foreground="#FFD700" if self.current_theme_name=="Dark" else "#FF8C00")
        self.log_text.insert(tk.END, f"{time.strftime('[%H:%M:%S]')} ", "info")
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.see(tk.END); self.log_text.config(state="disabled")

    def import_json_dialog(self):
        filename = filedialog.askopenfilename(title="Import JSON", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if filename: self.import_json_logic(filename)

    def import_json_logic(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: content = json.load(f)
            items = content if isinstance(content, list) else [dict(term=k, **v) for k, v in content.items()]
            count = 0
            for item in items:
                term = item.get("term", item.get("word", ""))
                if term:
                    self.db.upsert_word({
                        'term': term, 'pronunciation': item.get("pronunciation", ""),
                        'pos': item.get("part_of_speech", item.get("pos", "")),
                        'meaning': item.get("definition", item.get("meaning", "")),
                        'example': item.get("example", "")
                    })
                    count += 1
            self.log(f"Imported {count} items.", "success"); self.refresh_list()
        except Exception as e: self.log(f"Import Error: {e}", "error")

    def refresh_list(self, query=""):
        self.listbox.delete(0, tk.END)
        self.data_cache = self.db.get_all_words()
        query = query.lower(); mode = self.search_mode.get()
        for item in self.data_cache:
            w = item['term']; w_l = w.lower(); m = False
            if not query: m = True
            elif mode == "contains" and query in w_l: m = True
            elif mode == "startswith" and w_l.startswith(query): m = True
            elif mode == "endswith" and w_l.endswith(query): m = True
            if m: self.listbox.insert(tk.END, w)

    def on_search(self, event=None): self.refresh_list(self.entry_search.get())
    def save_entry(self):
        if self.current_mode != "write": return # ショートカット暴発防止
        data = {k: self.entries[k].get().strip() for k in ["term", "pronunciation", "meaning", "example"]}
        data["pos"] = self.pos_var.get()
        if not data['term']: return self.log("Term required.", "warn")
        res = self.db.upsert_word(data)
        self.refresh_list(self.entry_search.get())
        self.log(f"{'Registered' if res=='created' else 'Updated'}: {data['term']}", "success")
    def delete_entry(self):
        term = self.entries["term"].get().strip()
        if term and messagebox.askyesno("Delete", f"Delete '{term}'?"):
            self.db.delete_word(term); self.clear_form(); self.refresh_list(self.entry_search.get())
            self.log(f"Deleted: {term}", "warn")
    def fill_form(self, item):
        self.clear_form()
        for k in ["term", "pronunciation", "meaning", "example"]: self.entries[k].insert(0, item[k])
        self.pos_var.set(item['pos'])
    def clear_form(self):
        for ent in self.entries.values(): ent.delete(0, tk.END)
        self.pos_var.set(PART_OF_SPEECH_LIST[0])
    def move_up(self): self._move(-1)
    def move_down(self): self._move(1)
    def _move(self, d):
        if self.entry_search.get(): return self.log("Clear search first.", "warn")
        sel = self.listbox.curselection()
        if not sel: return
        i = sel[0]; ti = i + d
        if 0 <= ti < len(self.data_cache):
            self.db.update_order(self.data_cache[i]['term'], self.data_cache[ti]['sort_order'],
                                 self.data_cache[ti]['term'], self.data_cache[i]['sort_order'])
            self.refresh_list(); self.listbox.selection_set(ti); self.listbox.see(ti)

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    root = tk.Tk()
    app = ReDicSearcherApp(root)
    root.mainloop()