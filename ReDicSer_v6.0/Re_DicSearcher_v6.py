import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sqlite3
import json
import os
import sys
import time
import re
import shutil

# ==========================================
#  定数・設定
# ==========================================
APP_VERSION = "v6.0"
DEFAULT_DB_NAME = "dictionary.db"
CONFIG_FILE = "system.config"

THEMES = {
    "Dark": {
        "bg": "#000000", "fg": "#00FF00", "fg_dim": "#008800",
        "input_bg": "#111111", "input_fg": "#FFFFFF",
        "accent": "#006600", "accent_hover": "#009900",
        "list_bg": "#080808", "list_fg": "#00FF00",
        "select_bg": "#006600", "select_fg": "#FFFFFF",
        "log_fg_info": "#00FF00", "log_fg_err": "#FF0000",
        "btn_bg": "#333333", "btn_fg": "#FFFFFF",
        "link_fg": "#00FFFF", "clear_btn_bg": "#440000", "clear_btn_fg": "#FF8888"
    },
    "Light": {
        "bg": "#F0F0F0", "fg": "#000000", "fg_dim": "#555555",
        "input_bg": "#FFFFFF", "input_fg": "#000000",
        "accent": "#4CAF50", "accent_hover": "#45a049",
        "list_bg": "#FFFFFF", "list_fg": "#000000",
        "select_bg": "#4CAF50", "select_fg": "#FFFFFF",
        "log_fg_info": "#000000", "log_fg_err": "#FF0000",
        "btn_bg": "#DDDDDD", "btn_fg": "#000000",
        "link_fg": "#0000FF", "clear_btn_bg": "#FFDDDD", "clear_btn_fg": "#FF0000"
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
#  システム設定管理
# ==========================================
class SystemConfig:
    def __init__(self):
        self.config = {
            "last_db_path": DEFAULT_DB_NAME,
            "theme": "Dark",
            "splash_style": "Classic"
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config.update(json.load(f))
            except: pass

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except: pass

    def get(self, key): return self.config.get(key)
    def set(self, key, value):
        self.config[key] = value
        self.save()

# ==========================================
#  データベース管理クラス
# ==========================================
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.connect()
        self.migrate_db()

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)

    def close(self):
        if self.conn:
            self.conn.close()

    def migrate_db(self):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    term TEXT,
                    pronunciation TEXT,
                    pos TEXT,
                    meaning TEXT,
                    example TEXT,
                    sort_order INTEGER,
                    UNIQUE(term, pos)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS db_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def get_all_words(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM dictionary ORDER BY sort_order ASC")
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def upsert_word(self, data):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM dictionary WHERE term = ? AND pos = ?", (data['term'], data['pos']))
        exists = cursor.fetchone()
        if exists:
            cursor.execute("""
                UPDATE dictionary SET pronunciation=?, meaning=?, example=? WHERE term=? AND pos=?
            """, (data['pronunciation'], data['meaning'], data['example'], data['term'], data['pos']))
            self.conn.commit()
            return "updated"
        else:
            cursor.execute("SELECT MAX(sort_order) FROM dictionary")
            max_order = cursor.fetchone()[0]
            new_order = 1 if max_order is None else max_order + 1
            cursor.execute("""
                INSERT INTO dictionary (term, pronunciation, pos, meaning, example, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data['term'], data['pronunciation'], data['pos'], data['meaning'], data['example'], new_order))
            self.conn.commit()
            return "created"

    def delete_word(self, term, pos):
        self.conn.execute("DELETE FROM dictionary WHERE term = ? AND pos = ?", (term, pos))
        self.conn.commit()

    def update_order(self, id1, order1, id2, order2):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE dictionary SET sort_order = ? WHERE id = ?", (order1, id1))
        cursor.execute("UPDATE dictionary SET sort_order = ? WHERE id = ?", (order2, id2))
        self.conn.commit()

# ==========================================
#  メインアプリケーション
# ==========================================
class ReDicSearcherApp:
    def __init__(self, root):
        self.root = root
        self.root.geometry("1000x780")
        self.root.withdraw() 

        self.sys_config = SystemConfig()
        last_db = self.sys_config.get("last_db_path")
        if not os.path.exists(last_db) and last_db != DEFAULT_DB_NAME:
            last_db = DEFAULT_DB_NAME
            
        self.db_manager = DatabaseManager(last_db)
        
        self.current_theme_name = self.sys_config.get("theme")
        self.splash_style = self.sys_config.get("splash_style")
        self.colors = THEMES[self.current_theme_name]
        
        self.search_mode = tk.StringVar(value="contains")
        self.data_cache = []
        self.widgets = {}
        self.display_items = []
        
        self.apply_theme_to_root()
        self.setup_shortcuts()
        self.show_splash()

    def apply_theme_to_root(self):
        self.root.configure(bg=self.colors["bg"])
        db_name = os.path.basename(self.db_manager.db_path)
        self.root.title(f"Re.DicSearcher {APP_VERSION} [Cartridge: {db_name}]")

    def setup_shortcuts(self):
        self.root.bind('<Control-f>', lambda e: self.focus_search())
        self.root.bind('<Control-s>', lambda e: self.save_entry())
        self.root.bind('<Control-m>', lambda e: self.toggle_mode())
        self.root.bind('<Control-n>', lambda e: self.clear_form())
        self.root.bind('<Escape>', lambda e: self.clear_search())

    def focus_search(self):
        if self.current_mode == "read":
            self.entry_search.focus_set(); self.entry_search.select_range(0, tk.END)

    def show_splash(self):
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True); splash.attributes('-topmost', True)
        w, h = 500, 300
        x = (self.root.winfo_screenwidth()//2) - (w//2)
        y = (self.root.winfo_screenheight()//2) - (h//2)
        splash.geometry(f"{w}x{h}+{x}+{y}"); splash.configure(bg=self.colors["bg"])
        
        if self.splash_style == "Modern":
            # Modern Style
            try:
                from PIL import Image, ImageTk
                img_path = resource_path("logo.png")
                if os.path.exists(img_path):
                    raw = Image.open(img_path); raw.thumbnail((100, 100))
                    img = ImageTk.PhotoImage(raw)
                    lbl = tk.Label(splash, image=img, bg=self.colors["bg"])
                    lbl.image = img; lbl.pack(pady=20)
            except: pass
            tk.Label(splash, text=f"Re.Dic {APP_VERSION}", font=("Consolas", 30, "bold"), bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=10)
            tk.Label(splash, text=f"Loading: {os.path.basename(self.db_manager.db_path)}", font=("Consolas", 10), bg=self.colors["bg"], fg=self.colors["fg"]).pack(side=tk.BOTTOM, pady=20)
            splash.after(1500, lambda: self.startup_sequence(splash))
        else:
            # Classic Style (Animation restored)
            tk.Frame(splash, bg=self.colors["fg"], width=w, height=2).pack(side=tk.TOP)
            tk.Frame(splash, bg=self.colors["fg"], width=w, height=2).pack(side=tk.BOTTOM)
            tk.Frame(splash, bg=self.colors["fg"], width=2, height=h).place(x=0, y=0)
            tk.Frame(splash, bg=self.colors["fg"], width=2, height=h).place(x=w-2, y=0)
            
            content = tk.Frame(splash, bg=self.colors["bg"])
            content.pack(expand=True)
            tk.Label(content, text=f"[SYSTEM {APP_VERSION}]", font=("Consolas", 16, "bold"), bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=10)
            tk.Label(content, text=f"MOUNTING: {os.path.basename(self.db_manager.db_path)}", font=("Consolas", 10), bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=5)
            
            loading_lbl = tk.Label(content, text="", font=("Consolas", 12), bg=self.colors["bg"], fg=self.colors["fg"])
            loading_lbl.pack(pady=10)
            
            def update_loading(count=0):
                chars = ["|", "/", "-", "\\"]
                loading_lbl.config(text=f"LOADING MODULES {chars[count % 4]}")
                if count < 20: 
                    splash.after(80, update_loading, count+1)
                else:
                    self.startup_sequence(splash)
            update_loading()

    def startup_sequence(self, splash):
        self.data_cache = self.db_manager.get_all_words()
        self.setup_ui()
        splash.destroy()
        self.root.deiconify()
        self.log(f"System ready {APP_VERSION}. Cartridge loaded: {os.path.basename(self.db_manager.db_path)}", "success")

    def setup_ui(self):
        self.widgets = {}
        # Header
        header = tk.Frame(self.root, bg=self.colors["bg"], pady=10, padx=10)
        header.pack(fill=tk.X)
        self.widgets["header_frame"] = header

        self.btn_db = tk.Button(header, text="💾 CARTRIDGE", command=self.open_db_menu, relief="flat", padx=10)
        self.btn_db.pack(side=tk.LEFT, padx=(0, 5))
        self.widgets["btn_db"] = self.btn_db

        self.btn_config = tk.Button(header, text="⚙ CONFIG", command=self.open_config_dialog, relief="flat", padx=10)
        self.btn_config.pack(side=tk.LEFT)
        self.widgets["btn_config"] = self.btn_config

        self.btn_mode = tk.Button(header, text="MODE: READ", command=self.toggle_mode, relief="flat", padx=15, font=("Consolas", 11, "bold"))
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
        self.entry_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0), ipady=3)
        self.entry_search.bind('<KeyRelease>', self.on_search)
        self.widgets["entry_search"] = self.entry_search

        self.btn_clear_search = tk.Button(search_frame, text="×", command=self.clear_search, relief="flat", width=3, font=("Consolas", 10, "bold"))
        self.btn_clear_search.pack(side=tk.LEFT, padx=(0, 10))
        self.widgets["btn_clear_search"] = self.btn_clear_search

        opt_frame = tk.Frame(search_frame, bg=self.colors["bg"])
        opt_frame.pack(side=tk.LEFT)
        self.widgets["opt_frame"] = opt_frame
        self.radios = []
        for text, mode in [("In", "contains"), ("Start", "startswith"), ("End", "endswith")]:
            rb = tk.Radiobutton(opt_frame, text=text, variable=self.search_mode, value=mode, command=self.on_search, font=("Consolas", 9), selectcolor=self.colors["bg"])
            rb.pack(side=tk.LEFT); self.radios.append(rb)

        paned = tk.PanedWindow(self.frame_read, orient=tk.HORIZONTAL, bg=self.colors["bg"], sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, pady=5)
        self.widgets["paned"] = paned
        left_group = tk.Frame(paned, bg=self.colors["bg"])
        paned.add(left_group, minsize=280)
        self.widgets["left_group"] = left_group
        order_frame = tk.Frame(left_group, bg=self.colors["bg"]); order_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.widgets["order_frame"] = order_frame
        self.btn_up = tk.Button(order_frame, text="▲", command=self.move_up, relief="flat", width=2); self.btn_up.pack(side=tk.TOP, pady=2)
        self.btn_down = tk.Button(order_frame, text="▼", command=self.move_down, relief="flat", width=2); self.btn_down.pack(side=tk.TOP, pady=2)
        self.widgets["btn_up"] = self.btn_up; self.widgets["btn_down"] = self.btn_down
        
        self.listbox = tk.Listbox(left_group, font=("Consolas", 11), borderwidth=1, relief="solid")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.show_detail)
        self.widgets["listbox"] = self.listbox
        sb = tk.Scrollbar(left_group, orient=tk.VERTICAL, command=self.listbox.yview); sb.pack(side=tk.RIGHT, fill=tk.Y); self.listbox.config(yscrollcommand=sb.set)

        detail_frame = tk.Frame(paned, bg=self.colors["bg"], padx=15); paned.add(detail_frame, minsize=400)
        self.widgets["detail_frame"] = detail_frame
        self.lbl_detail_term = tk.Label(detail_frame, text="", font=("Consolas", 20, "bold"), anchor="w"); self.lbl_detail_term.pack(fill=tk.X, pady=(0, 10))
        self.widgets["lbl_detail_term"] = self.lbl_detail_term
        self.detail_text = tk.Text(detail_frame, font=("Consolas", 11), height=15, state="disabled", relief="flat", wrap="word"); self.detail_text.pack(fill=tk.BOTH, expand=True)
        self.widgets["detail_text"] = self.detail_text

    def setup_write_mode(self):
        self.widgets["frame_write"] = self.frame_write
        self.entry_labels = []; self.entries = {}
        lbl_title = tk.Label(self.frame_write, text="EDITOR / REGISTRATION", font=("Consolas", 14, "bold"), anchor="w"); lbl_title.pack(pady=(0, 15))
        self.widgets["lbl_write_title"] = lbl_title
        def create_row(label, key):
            lbl = tk.Label(self.frame_write, text=f"■ {label}", font=("Consolas", 10, "bold"), anchor="w"); lbl.pack(anchor="w"); self.entry_labels.append(lbl)
            ent = tk.Entry(self.frame_write, font=("Consolas", 11), relief="flat"); ent.pack(fill=tk.X, pady=(0, 10), ipady=5); self.entries[key] = ent
            self.widgets[f"entry_{key}"] = ent
        create_row("単語 (Term)", "term"); create_row("発音 (Pronunciation)", "pronunciation")
        lbl_pos = tk.Label(self.frame_write, text="■ 品詞 (Part of Speech)", font=("Consolas", 10, "bold"), anchor="w"); lbl_pos.pack(anchor="w"); self.entry_labels.append(lbl_pos)
        self.pos_var = tk.StringVar(value=PART_OF_SPEECH_LIST[0])
        self.pos_menu = tk.OptionMenu(self.frame_write, self.pos_var, *PART_OF_SPEECH_LIST); self.pos_menu.config(relief="flat", highlightthickness=0, font=("Consolas", 11)); self.pos_menu.pack(fill=tk.X, pady=(0, 10), ipady=3); self.widgets["pos_menu"] = self.pos_menu
        create_row("意味 (Meaning)", "meaning"); create_row("使用例 (Example)", "example")
        btn_box = tk.Frame(self.frame_write, bg=self.colors["bg"], pady=15); btn_box.pack(fill=tk.X); self.widgets["btn_box"] = btn_box
        self.btn_save = tk.Button(btn_box, text="💾 SAVE (Ctrl+S)", command=self.save_entry, relief="flat", padx=20, font=("Consolas", 10, "bold")); self.btn_save.pack(side=tk.LEFT, padx=5); self.widgets["btn_save"] = self.btn_save
        self.btn_clear = tk.Button(btn_box, text="CLEAR (Ctrl+N)", command=self.clear_form, relief="flat", padx=10); self.btn_clear.pack(side=tk.LEFT, padx=5); self.widgets["btn_clear"] = self.btn_clear
        self.btn_delete = tk.Button(btn_box, text="🗑 DELETE", command=self.delete_entry, relief="flat", padx=10); self.btn_delete.pack(side=tk.RIGHT); self.widgets["btn_delete"] = self.btn_delete

    # ==========================================
    #  ★ 機能ロジック (不足していた部分を全て実装)
    # ==========================================
    def open_db_menu(self):
        dlg = tk.Toplevel(self.root); dlg.title("Cartridge Menu"); dlg.geometry("350x450"); c = self.colors; dlg.configure(bg=c["bg"])
        dlg.transient(self.root); dlg.grab_set()
        tk.Label(dlg, text="CARTRIDGE SYSTEM", font=("Consolas", 14, "bold"), bg=c["bg"], fg=c["fg"]).pack(pady=15)
        current_name = os.path.basename(self.db_manager.db_path)
        tk.Label(dlg, text=f"MOUNTED: {current_name}", font=("Consolas", 10), bg=c["bg"], fg=c["accent"]).pack()
        tk.Label(dlg, text="-------------------", font=("Consolas", 10), bg=c["bg"], fg=c["fg_dim"]).pack(pady=5)
        tk.Label(dlg, text="[SWITCH / NEW]", font=("Consolas", 10, "bold"), bg=c["bg"], fg=c["fg"]).pack(pady=5)
        
        def do_new():
            path = filedialog.asksaveasfilename(title="Create New Cartridge", defaultextension=".db", filetypes=[("DB Files", "*.db")])
            if path: self.switch_db(path); dlg.destroy()
        def do_load():
            path = filedialog.askopenfilename(title="Load Cartridge", filetypes=[("DB Files", "*.db")])
            if path: self.switch_db(path); dlg.destroy()
            
        btn_style = {"bg": c.get("btn_bg", "#333333"), "fg": c["fg"], "relief": "flat", "width": 25, "font": ("Consolas", 10)}
        tk.Button(dlg, text="🆕 CREATE NEW DB", command=do_new, **btn_style).pack(pady=2)
        tk.Button(dlg, text="📂 LOAD EXISTING DB", command=do_load, **btn_style).pack(pady=2)
        tk.Label(dlg, text="-------------------", font=("Consolas", 10), bg=c["bg"], fg=c["fg_dim"]).pack(pady=10)
        tk.Label(dlg, text="[EXPORT DATA]", font=("Consolas", 10, "bold"), bg=c["bg"], fg=c["fg"]).pack(pady=5)
        
        def do_export_json():
            path = filedialog.asksaveasfilename(title="Export to JSON", defaultextension=".json", filetypes=[("JSON Files", "*.json")])
            if path:
                try:
                    data = self.db_manager.get_all_words()
                    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
                    self.log(f"Exported to JSON: {os.path.basename(path)}", "success"); dlg.destroy()
                except Exception as e: self.log(f"Export Error: {e}", "error")
        
        def do_export_db():
            path = filedialog.asksaveasfilename(title="Export to New DB (Backup)", defaultextension=".db", filetypes=[("DB Files", "*.db")])
            if path:
                try:
                    shutil.copy2(self.db_manager.db_path, path)
                    self.log(f"Exported DB Copy: {os.path.basename(path)}", "success"); dlg.destroy()
                except Exception as e: self.log(f"Export Error: {e}", "error")
        
        def do_import_json(): dlg.destroy(); self.import_json_dialog()
        
        tk.Button(dlg, text="📤 EXPORT TO JSON", command=do_export_json, **btn_style).pack(pady=2)
        tk.Button(dlg, text="💾 EXPORT TO DB (COPY)", command=do_export_db, **btn_style).pack(pady=2)
        tk.Label(dlg, text="- or -", font=("Consolas", 8), bg=c["bg"], fg=c["fg_dim"]).pack()
        tk.Button(dlg, text="📥 IMPORT FROM JSON", command=do_import_json, **btn_style).pack(pady=2)
        tk.Button(dlg, text="CLOSE", command=dlg.destroy, bg=c["accent"], fg="white", relief="flat", padx=10).pack(side=tk.BOTTOM, pady=20)
        self.apply_temp_theme(self.current_theme_name, dlg, [])

    def switch_db(self, new_db_path):
        self.db_manager.close()
        self.db_manager = DatabaseManager(new_db_path)
        self.sys_config.set("last_db_path", new_db_path)
        self.entry_search.delete(0, tk.END)
        self.apply_theme_to_root()
        self.refresh_list()
        self.log(f"Switched Cartridge: {os.path.basename(new_db_path)}", "success")

    def clear_search(self):
        self.entry_search.delete(0, tk.END); self.refresh_list()
        if self.current_mode == "read": self.entry_search.focus_set()

    def jump_to_word_filter(self, word):
        self.entry_search.delete(0, tk.END); self.entry_search.insert(0, word)
        self.search_mode.set("contains"); self.refresh_list(word)
        self.log(f"Filtered by link: {word}", "info")
        if self.listbox.size() > 0: self.listbox.selection_set(0); self.show_detail(None)

    def apply_theme_to_widgets(self):
        c = self.colors
        for name, w in self.widgets.items():
            if "frame" in name or "group" in name or "box" in name: w.configure(bg=c["bg"])
            if "lbl" in name: w.configure(bg=c["bg"], fg=c["fg"])
            if "entry" in name: w.configure(bg=c["input_bg"], fg=c["input_fg"], insertbackground=c["fg"])
        for lbl in self.entry_labels: lbl.configure(bg=c["bg"], fg=c["fg_dim"])
        btn_bg = c.get("btn_bg", "#333333")
        for btn in [self.btn_db, self.btn_config, self.btn_up, self.btn_down]: btn.configure(bg=btn_bg, fg=c["fg"])
        self.btn_clear_search.configure(bg=c.get("clear_btn_bg", "#440000"), fg=c.get("clear_btn_fg", "#FF0000"))
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

    def open_config_dialog(self):
        dlg = tk.Toplevel(self.root); dlg.title("Settings"); dlg.geometry("400x300"); c = self.colors; dlg.configure(bg=c["bg"])
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
            self.sys_config.set("theme", self.var_theme.get()); self.sys_config.set("splash_style", self.var_splash.get())
            self.current_theme_name = self.var_theme.get(); self.splash_style = self.var_splash.get()
            self.colors = THEMES[self.current_theme_name]; self.apply_theme_to_root(); self.apply_theme_to_widgets()
            self.log("Config Saved.", "success"); dlg.destroy()
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
            self.frame_read.pack_forget(); self.frame_write.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "write"; self.btn_mode.config(text="MODE: WRITE (Ctrl+M)")
            try:
                sel = self.listbox.curselection()
                if sel and sel[0] < len(self.display_items): self.fill_form(self.display_items[sel[0]])
            except: pass
        else:
            self.frame_write.pack_forget(); self.frame_read.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "read"; self.btn_mode.config(text="MODE: READ (Ctrl+M)")

    def log(self, message, level="info"):
        self.log_text.config(state="normal")
        c = self.colors
        self.log_text.tag_config("info", foreground=c["log_fg_info"]); self.log_text.tag_config("error", foreground=c["log_fg_err"])
        self.log_text.tag_config("success", foreground=c["accent"]); self.log_text.tag_config("warn", foreground="#FFD700" if self.current_theme_name=="Dark" else "#FF8C00")
        self.log_text.insert(tk.END, f"{time.strftime('[%H:%M:%S]')} ", "info"); self.log_text.insert(tk.END, f"{message}\n", level)
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
                    self.db_manager.upsert_word({
                        'term': term, 'pronunciation': item.get("pronunciation", ""),
                        'pos': item.get("part_of_speech", item.get("pos", "")),
                        'meaning': item.get("definition", item.get("meaning", "")),
                        'example': item.get("example", "")
                    }); count += 1
            self.log(f"Imported {count} items.", "success"); self.refresh_list()
        except Exception as e: self.log(f"Import Error: {e}", "error")

    def on_search(self, event=None): self.refresh_list(self.entry_search.get())
    def refresh_list(self, query=""):
        self.listbox.delete(0, tk.END)
        self.data_cache = self.db_manager.get_all_words()
        self.display_items = []
        query = query.lower(); mode = self.search_mode.get()
        for item in self.data_cache:
            w = item['term']; w_l = w.lower(); m = False
            if not query: m = True
            elif mode == "contains" and query in w_l: m = True
            elif mode == "startswith" and w_l.startswith(query): m = True
            elif mode == "endswith" and w_l.endswith(query): m = True
            if m:
                display_str = f"{item['term']} ({item['pos'].split('(')[0]})" 
                self.listbox.insert(tk.END, display_str)
                self.display_items.append(item)

    def show_detail(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx >= len(self.display_items): return
        item = self.display_items[idx]
        self.lbl_detail_term.config(text=item['term'])
        content = f"【発音】 {item['pronunciation']}\n【品詞】 {item['pos']}\n\n【意味】\n{item['meaning']}\n\n【例文】\n{item['example']}"
        self.detail_text.config(state="normal")
        self.detail_text.delete(1.0, tk.END)
        pattern = re.compile(r'\[(.*?)\]')
        last_pos = 0
        for match in pattern.finditer(content):
            self.detail_text.insert(tk.END, content[last_pos:match.start()])
            link_word = match.group(1)
            tag_name = f"link_{link_word}"
            self.detail_text.insert(tk.END, link_word, ("hyperlink", tag_name))
            def on_link_click(event, word=link_word): self.jump_to_word_filter(word)
            self.detail_text.tag_bind(tag_name, "<Button-1>", on_link_click)
            self.detail_text.tag_bind(tag_name, "<Enter>", lambda e: self.detail_text.config(cursor="hand2"))
            self.detail_text.tag_bind(tag_name, "<Leave>", lambda e: self.detail_text.config(cursor=""))
            last_pos = match.end()
        self.detail_text.insert(tk.END, content[last_pos:])
        self.detail_text.tag_config("hyperlink", foreground=self.colors.get("link_fg", "blue"), underline=1)
        self.detail_text.config(state="disabled")
        if self.current_mode == "write": self.fill_form(item)

    def save_entry(self):
        if self.current_mode != "write": return
        data = {k: self.entries[k].get().strip() for k in ["term", "pronunciation", "meaning", "example"]}
        data["pos"] = self.pos_var.get()
        if not data['term']: return self.log("Term required.", "warn")
        res = self.db_manager.upsert_word(data)
        self.refresh_list(self.entry_search.get())
        self.log(f"{'Registered' if res=='created' else 'Updated'}: {data['term']}", "success")
    def delete_entry(self):
        term = self.entries["term"].get().strip(); pos = self.pos_var.get()
        if term and messagebox.askyesno("Delete", f"Delete '{term} ({pos})'?"):
            self.db_manager.delete_word(term, pos); self.clear_form(); self.refresh_list(self.entry_search.get())
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
        if 0 <= ti < len(self.display_items):
            item1 = self.display_items[i]; item2 = self.display_items[ti]
            self.db_manager.update_order(item1['id'], item2['sort_order'], item2['id'], item1['sort_order'])
            self.refresh_list(); self.listbox.selection_set(ti); self.listbox.see(ti)

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    root = tk.Tk()
    app = ReDicSearcherApp(root)
    root.mainloop()