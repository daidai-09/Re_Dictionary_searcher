import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sqlite3
import json
import os
import sys
import time
import re
from typing import List, Dict, Optional, Any
from pathlib import Path

# ==========================================
#  設定・定数
# ==========================================
APP_TITLE = "Re.DicSearcher v4.0"
DB_FILE = "dictionary.db"

# テーマ定義
THEMES = {
    "Dark": {
        "bg": "#1e1e1e", "fg": "#e0e0e0", "fg_dim": "#808080",
        "input_bg": "#2d2d2d", "input_fg": "#ffffff",
        "accent": "#4caf50", "accent_hover": "#43a047",
        "list_bg": "#252526", "list_fg": "#e0e0e0",
        "select_bg": "#264f78", "select_fg": "#ffffff",
        "log_fg_info": "#4ec9b0", "log_fg_err": "#f44747",
        "btn_bg": "#3c3c3c", "btn_fg": "#cccccc",
        "link_fg": "#569cd6"  # VSCode風ブルー
    },
    "Light": {
        "bg": "#f3f3f3", "fg": "#101010", "fg_dim": "#666666",
        "input_bg": "#ffffff", "input_fg": "#000000",
        "accent": "#007acc", "accent_hover": "#0062a3",
        "list_bg": "#ffffff", "list_fg": "#000000",
        "select_bg": "#cce8ff", "select_fg": "#000000",
        "log_fg_info": "#000000", "log_fg_err": "#cd3131",
        "btn_bg": "#e1e1e1", "btn_fg": "#333333",
        "link_fg": "#0000FF"
    }
}

PART_OF_SPEECH_LIST = [
    "N(名詞)", "V(動詞)", "Adj(形容詞)", "Adv(副詞)", 
    "Conj(接続詞)", "Prep(前置詞)", "Pro(代名詞)", 
    "Det(限定詞)", "Aux(助動詞)", "Part(助詞)", "Num(数詞)", "Other"
]

def resource_path(relative_path: str) -> str:
    """PyInstallerと開発環境の両方でリソースパスを解決する"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ==========================================
#  データベース管理クラス
# ==========================================
class DatabaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row  # 辞書ライクにアクセス可能にする
        return conn

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
            # インデックス作成（検索高速化）
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_term ON dictionary(term)")
            conn.commit()

    def get_all_words(self) -> List[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dictionary ORDER BY sort_order ASC")
            return [dict(row) for row in cursor.fetchall()]

    def upsert_word(self, data: dict) -> str:
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
                res = cursor.fetchone()
                max_order = res[0] if res[0] is not None else 0
                
                cursor.execute("""
                    INSERT INTO dictionary (term, pronunciation, pos, meaning, example, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (data['term'], data['pronunciation'], data['pos'], data['meaning'], data['example'], max_order + 1))
                return "created"

    def delete_word(self, term: str):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM dictionary WHERE term = ?", (term,))

    def swap_order(self, term1: str, term2: str):
        """2つの単語のsort_orderを入れ替える"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 現在のオーダーを取得
            cursor.execute("SELECT sort_order FROM dictionary WHERE term=?", (term1,))
            o1 = cursor.fetchone()[0]
            cursor.execute("SELECT sort_order FROM dictionary WHERE term=?", (term2,))
            o2 = cursor.fetchone()[0]
            
            # 入れ替え
            cursor.execute("UPDATE dictionary SET sort_order=? WHERE term=?", (o2, term1))
            cursor.execute("UPDATE dictionary SET sort_order=? WHERE term=?", (o1, term2))
            conn.commit()

    def get_setting(self, key: str, default: str = None) -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            res = cursor.fetchone()
            return res[0] if res else default

    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

# ==========================================
#  テーマ管理ヘルパー
# ==========================================
class ThemeManager:
    def __init__(self, db: DatabaseManager, root: tk.Tk):
        self.db = db
        self.root = root
        self.current_theme_name = self.db.get_setting("theme", "Dark")
        self.colors = THEMES[self.current_theme_name]

    def set_theme(self, theme_name: str):
        if theme_name in THEMES:
            self.current_theme_name = theme_name
            self.colors = THEMES[theme_name]
            self.db.set_setting("theme", theme_name)

    def apply_to_root(self):
        self.root.configure(bg=self.colors["bg"])

# ==========================================
#  メインアプリケーション
# ==========================================
class ReDicSearcherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.db = DatabaseManager(DB_FILE)
        self.tm = ThemeManager(self.db, self.root)
        
        self.root.geometry("1000x750")
        self.root.minsize(800, 600)
        self.root.title(f"{APP_TITLE}")
        self.root.withdraw() 

        # State Variables
        self.search_mode = tk.StringVar(value="contains")
        self.data_cache: List[dict] = []
        self.widgets: Dict[str, Any] = {}
        self.current_mode = "read"
        
        # Init
        self.tm.apply_to_root()
        self.setup_shortcuts()
        
        # スプラッシュ設定を取得して表示
        self.splash_style = self.db.get_setting("splash_style", "Modern")
        self.root.after(100, self.show_splash) # 少し待ってから表示

    def setup_shortcuts(self):
        shortcuts = {
            '<Control-f>': self.focus_search,
            '<Control-s>': self.save_entry,
            '<Control-m>': self.toggle_mode,
            '<Control-n>': self.clear_form,
        }
        for key, func in shortcuts.items():
            self.root.bind(key, lambda e, f=func: f())

    # ==========================================
    #  UI構築・スプラッシュ
    # ==========================================
    def show_splash(self):
        # 簡易的なロード処理
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.attributes('-topmost', True)
        
        w, h = 400, 250
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        splash.geometry(f"{w}x{h}+{x}+{y}")
        splash.configure(bg=self.tm.colors["bg"])
        
        c = self.tm.colors
        # ロゴ部分
        tk.Label(splash, text="Re.Dic", font=("Consolas", 36, "bold"), 
                 bg=c["bg"], fg=c["accent"]).pack(expand=True)
        lbl_status = tk.Label(splash, text="Loading Database...", font=("Consolas", 10), 
                              bg=c["bg"], fg=c["fg_dim"])
        lbl_status.pack(side=tk.BOTTOM, pady=20)
        
        splash.update()
        
        # 重い処理をここで実行
        self.data_cache = self.db.get_all_words()
        self.setup_ui()
        
        # 演出用（短くする）
        time.sleep(0.5) 
        
        splash.destroy()
        self.root.deiconify()
        self.log(f"System initialized. {len(self.data_cache)} words loaded.", "success")

    def setup_ui(self):
        # メインコンテナ（パディング用）
        main_container = tk.Frame(self.root, bg=self.tm.colors["bg"])
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. Header Area
        self._setup_header(main_container)
        
        # 2. Content Area
        self.content_frame = tk.Frame(main_container, bg=self.tm.colors["bg"])
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.widgets["content_frame"] = self.content_frame
        
        self.frame_read = tk.Frame(self.content_frame, bg=self.tm.colors["bg"])
        self._setup_read_mode()
        
        self.frame_write = tk.Frame(self.content_frame, bg=self.tm.colors["bg"])
        self._setup_write_mode()

        self.frame_read.pack(fill=tk.BOTH, expand=True) # 初期表示

        # 3. Log Area
        self._setup_log_area(main_container)

        self.apply_theme_to_widgets()
        self.refresh_list()

    def _setup_header(self, parent):
        header = tk.Frame(parent, bg=self.tm.colors["bg"], pady=10, padx=10)
        header.pack(fill=tk.X)
        self.widgets["header_frame"] = header

        # ボタン類
        btn_params = {"relief": "flat", "padx": 10, "font": ("Consolas", 10)}
        
        self.btn_import = tk.Button(header, text="📂 IMPORT", command=self.import_json_dialog, **btn_params)
        self.btn_import.pack(side=tk.LEFT, padx=(0, 5))
        
        self.btn_config = tk.Button(header, text="⚙ CONFIG", command=self.open_config_dialog, **btn_params)
        self.btn_config.pack(side=tk.LEFT)
        
        self.btn_mode = tk.Button(header, text="MODE: READ (Ctrl+M)", command=self.toggle_mode, 
                                  font=("Consolas", 10, "bold"), relief="flat", padx=15)
        self.btn_mode.pack(side=tk.RIGHT)
        
        self.widgets.update({
            "btn_import": self.btn_import, "btn_config": self.btn_config, "btn_mode": self.btn_mode
        })

    def _setup_read_mode(self):
        # 検索バー
        search_frame = tk.Frame(self.frame_read, bg=self.tm.colors["bg"], pady=5)
        search_frame.pack(fill=tk.X)
        self.widgets["search_frame"] = search_frame

        tk.Label(search_frame, text="SEARCH >", font=("Consolas", 11, "bold"), 
                 bg=self.tm.colors["bg"], fg=self.tm.colors["fg"]).pack(side=tk.LEFT)

        self.entry_search = tk.Entry(search_frame, font=("Consolas", 12), relief="flat")
        self.entry_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, ipady=5)
        self.entry_search.bind('<KeyRelease>', self.on_search)
        self.widgets["entry_search"] = self.entry_search

        # 検索オプション
        opt_frame = tk.Frame(search_frame, bg=self.tm.colors["bg"])
        opt_frame.pack(side=tk.LEFT)
        self.radios = []
        for text, mode in [("In", "contains"), ("Start", "startswith"), ("End", "endswith")]:
            rb = tk.Radiobutton(opt_frame, text=text, variable=self.search_mode, value=mode,
                                command=self.on_search, font=("Consolas", 9), 
                                selectcolor=self.tm.colors["bg"], relief="flat")
            rb.pack(side=tk.LEFT)
            self.radios.append(rb)

        # メインパネル (リスト + 詳細)
        paned = tk.PanedWindow(self.frame_read, orient=tk.HORIZONTAL, bg=self.tm.colors["bg"], sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, pady=5)
        self.widgets["paned"] = paned

        # 左側: リスト
        left_group = tk.Frame(paned, bg=self.tm.colors["bg"])
        paned.add(left_group, minsize=250)
        self.widgets["left_group"] = left_group

        # 並び替えボタン
        order_frame = tk.Frame(left_group, bg=self.tm.colors["bg"])
        order_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.widgets["order_frame"] = order_frame
        
        self.btn_up = tk.Button(order_frame, text="▲", command=self.move_up, relief="flat", width=2)
        self.btn_up.pack(side=tk.TOP, pady=2)
        self.btn_down = tk.Button(order_frame, text="▼", command=self.move_down, relief="flat", width=2)
        self.btn_down.pack(side=tk.TOP, pady=2)
        self.widgets.update({"btn_up": self.btn_up, "btn_down": self.btn_down})

        # リストボックス
        list_frame = tk.Frame(left_group)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        sb = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(list_frame, font=("Consolas", 12), borderwidth=0, 
                                  yscrollcommand=sb.set, exportselection=False)
        sb.config(command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.show_detail)
        self.widgets["listbox"] = self.listbox

        # 右側: 詳細
        detail_frame = tk.Frame(paned, bg=self.tm.colors["bg"], padx=20)
        paned.add(detail_frame, minsize=400)
        self.widgets["detail_frame"] = detail_frame

        self.lbl_detail_term = tk.Label(detail_frame, text="", font=("Consolas", 24, "bold"), anchor="w")
        self.lbl_detail_term.pack(fill=tk.X, pady=(0, 10))
        self.widgets["lbl_detail_term"] = self.lbl_detail_term

        self.detail_text = tk.Text(detail_frame, font=("Consolas", 12), state="disabled", relief="flat", wrap="word", padx=5, pady=5)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        self.widgets["detail_text"] = self.detail_text

    def _setup_write_mode(self):
        self.entries = {}
        self.entry_labels = []
        
        title = tk.Label(self.frame_write, text="EDITOR / REGISTRATION", font=("Consolas", 14, "bold"), anchor="w")
        title.pack(pady=(0, 15))
        self.widgets["lbl_write_title"] = title

        # フォーム生成ヘルパー
        def create_field(label_text, key):
            lbl = tk.Label(self.frame_write, text=f"■ {label_text}", font=("Consolas", 10, "bold"), anchor="w")
            lbl.pack(anchor="w")
            self.entry_labels.append(lbl)
            ent = tk.Entry(self.frame_write, font=("Consolas", 12), relief="flat")
            ent.pack(fill=tk.X, pady=(0, 15), ipady=5)
            self.entries[key] = ent
            self.widgets[f"entry_{key}"] = ent

        create_field("単語 (Term)", "term")
        create_field("発音 (Pronunciation)", "pronunciation")

        # 品詞
        lbl_pos = tk.Label(self.frame_write, text="■ 品詞 (Part of Speech)", font=("Consolas", 10, "bold"), anchor="w")
        lbl_pos.pack(anchor="w")
        self.entry_labels.append(lbl_pos)
        self.pos_var = tk.StringVar(value=PART_OF_SPEECH_LIST[0])
        self.pos_menu = tk.OptionMenu(self.frame_write, self.pos_var, *PART_OF_SPEECH_LIST)
        self.pos_menu.config(relief="flat", highlightthickness=0, font=("Consolas", 11))
        self.pos_menu.pack(fill=tk.X, pady=(0, 15), ipady=5)
        self.widgets["pos_menu"] = self.pos_menu

        create_field("意味 (Meaning)", "meaning")
        create_field("使用例 (Example)", "example")

        # アクションボタン
        btn_box = tk.Frame(self.frame_write, bg=self.tm.colors["bg"], pady=20)
        btn_box.pack(fill=tk.X)
        self.widgets["btn_box"] = btn_box

        self.btn_save = tk.Button(btn_box, text="💾 SAVE (Ctrl+S)", command=self.save_entry, relief="flat", padx=20, font=("Consolas", 10, "bold"))
        self.btn_save.pack(side=tk.LEFT, padx=5)
        
        self.btn_clear = tk.Button(btn_box, text="CLEAR (Ctrl+N)", command=self.clear_form, relief="flat", padx=10, font=("Consolas", 10))
        self.btn_clear.pack(side=tk.LEFT, padx=5)
        
        self.btn_delete = tk.Button(btn_box, text="🗑 DELETE", command=self.delete_entry, relief="flat", padx=10, font=("Consolas", 10))
        self.btn_delete.pack(side=tk.RIGHT)
        
        self.widgets.update({"btn_save": self.btn_save, "btn_clear": self.btn_clear, "btn_delete": self.btn_delete})

    def _setup_log_area(self, parent):
        log_frame = tk.Frame(parent, bg=self.tm.colors["bg"], padx=10, pady=5)
        log_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.widgets["log_frame"] = log_frame

        self.log_text = tk.Text(log_frame, height=5, font=("Consolas", 9), state="disabled", relief="flat", bd=0)
        self.log_text.pack(fill=tk.X)
        self.widgets["log_text"] = self.log_text

    # ==========================================
    #  ロジック: 表示・検索・詳細
    # ==========================================
    def refresh_list(self, query: str = ""):
        self.listbox.delete(0, tk.END)
        self.data_cache = self.db.get_all_words()
        
        query = query.lower()
        mode = self.search_mode.get()
        
        # フィルタリング
        filtered_items = []
        for item in self.data_cache:
            term = item['term']
            term_l = term.lower()
            match = False
            
            if not query:
                match = True
            elif mode == "contains" and query in term_l:
                match = True
            elif mode == "startswith" and term_l.startswith(query):
                match = True
            elif mode == "endswith" and term_l.endswith(query):
                match = True
            
            if match:
                filtered_items.append(term)
        
        # 一括挿入（高速化）
        if filtered_items:
            self.listbox.insert(tk.END, *filtered_items)

    def on_search(self, event=None):
        self.refresh_list(self.entry_search.get())

    def show_detail(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        term = self.listbox.get(sel[0])
        
        # キャッシュから検索（線形探索だが件数が少なければOK。多ければ辞書型に変えるべき）
        item = next((x for x in self.data_cache if x['term'] == term), None)
        if not item: return

        self.lbl_detail_term.config(text=term)
        
        # テキスト生成
        content = (
            f"【発音】 {item['pronunciation']}\n"
            f"【品詞】 {item['pos']}\n\n"
            f"【意味】\n{item['meaning']}\n\n"
            f"【例文】\n{item['example']}"
        )
        
        self.detail_text.config(state="normal")
        self.detail_text.delete(1.0, tk.END)
        
        # リンク解析と描画
        self._render_text_with_links(content)
        
        self.detail_text.config(state="disabled")

        if self.current_mode == "write":
            self.fill_form(item)

    def _render_text_with_links(self, content: str):
        """[word]形式のリンクを解析してテキストウィジェットに挿入"""
        pattern = re.compile(r'\[(.*?)\]')
        last_pos = 0
        
        for match in pattern.finditer(content):
            # リンク前の通常テキスト
            self.detail_text.insert(tk.END, content[last_pos:match.start()])
            
            link_word = match.group(1)
            tag_name = f"link_{match.start()}" # ユニークなタグ名にする
            
            self.detail_text.insert(tk.END, link_word, ("hyperlink", tag_name))
            
            # イベントバインド
            self.detail_text.tag_bind(tag_name, "<Button-1>", lambda e, w=link_word: self.jump_to_word(w))
            self.detail_text.tag_bind(tag_name, "<Enter>", lambda e: self.detail_text.config(cursor="hand2"))
            self.detail_text.tag_bind(tag_name, "<Leave>", lambda e: self.detail_text.config(cursor=""))

            last_pos = match.end()
            
        self.detail_text.insert(tk.END, content[last_pos:])
        
        # リンクの見た目
        self.detail_text.tag_config("hyperlink", foreground=self.tm.colors.get("link_fg", "blue"), underline=1)

    def jump_to_word(self, word: str):
        """リンクジャンプ：リスト内を検索して選択状態にする"""
        target = word.lower()
        items = self.listbox.get(0, tk.END)
        
        for idx, item in enumerate(items):
            if item.lower() == target:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(idx)
                self.listbox.see(idx)
                self.listbox.event_generate("<<ListboxSelect>>")
                self.log(f"Jumped to link: {word}", "info")
                return
        
        self.log(f"Link not found in current list: {word}", "warn")

    # ==========================================
    #  ロジック: 編集・モード切替・その他
    # ==========================================
    def toggle_mode(self):
        if self.current_mode == "read":
            self.frame_read.pack_forget()
            self.frame_write.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "write"
            self.btn_mode.config(text="MODE: WRITE (Ctrl+M)", bg=self.tm.colors["accent"], fg="#FFF")
            
            # 選択中の単語があればフォームに反映
            sel = self.listbox.curselection()
            if sel:
                term = self.listbox.get(sel[0])
                item = next((x for x in self.data_cache if x['term'] == term), None)
                if item: self.fill_form(item)
                
        else:
            self.frame_write.pack_forget()
            self.frame_read.pack(fill=tk.BOTH, expand=True)
            self.current_mode = "read"
            self.btn_mode.config(text="MODE: READ (Ctrl+M)")

    def save_entry(self):
        if self.current_mode != "write": return
        
        data = {k: self.entries[k].get().strip() for k in ["term", "pronunciation", "meaning", "example"]}
        data["pos"] = self.pos_var.get()
        
        if not data['term']:
            self.log("Term is required.", "warn")
            return
            
        res = self.db.upsert_word(data)
        self.log(f"{'Registered' if res=='created' else 'Updated'}: {data['term']}", "success")
        
        # 検索状態を維持しつつリスト更新
        current_search = self.entry_search.get()
        self.refresh_list(current_search)

    def delete_entry(self):
        term = self.entries["term"].get().strip()
        if not term: return
        
        if messagebox.askyesno("Delete", f"Are you sure you want to delete '{term}'?"):
            self.db.delete_word(term)
            self.clear_form()
            self.refresh_list(self.entry_search.get())
            self.log(f"Deleted: {term}", "warn")

    def fill_form(self, item):
        self.clear_form()
        for k in ["term", "pronunciation", "meaning", "example"]:
            self.entries[k].insert(0, item[k])
        self.pos_var.set(item['pos'])

    def clear_form(self):
        for ent in self.entries.values():
            ent.delete(0, tk.END)
        self.pos_var.set(PART_OF_SPEECH_LIST[0])

    def focus_search(self):
        if self.current_mode == "read":
            self.entry_search.focus_set()
            self.entry_search.select_range(0, tk.END)

    def move_up(self): self._move_item(-1)
    def move_down(self): self._move_item(1)

    def _move_item(self, direction):
        if self.entry_search.get():
            self.log("Sorting is disabled while searching.", "warn")
            return
            
        sel = self.listbox.curselection()
        if not sel: return
        
        idx = sel[0]
        target_idx = idx + direction
        
        if 0 <= target_idx < len(self.data_cache):
            term1 = self.data_cache[idx]['term']
            term2 = self.data_cache[target_idx]['term']
            
            self.db.swap_order(term1, term2)
            self.refresh_list()
            
            self.listbox.selection_set(target_idx)
            self.listbox.see(target_idx)

    # ==========================================
    #  設定・インポート・ログ・テーマ適用
    # ==========================================
    def open_config_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Settings")
        dlg.geometry("400x250")
        c = self.tm.colors
        dlg.configure(bg=c["bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="CONFIGURATION", font=("Consolas", 14, "bold"), 
                 bg=c["bg"], fg=c["fg"]).pack(pady=15)
        
        # テーマ選択
        frame = tk.LabelFrame(dlg, text="UI Theme", bg=c["bg"], fg=c["fg_dim"])
        frame.pack(fill=tk.X, padx=20, pady=5)
        
        var_theme = tk.StringVar(value=self.tm.current_theme_name)
        
        for t in THEMES.keys():
            tk.Radiobutton(frame, text=t, variable=var_theme, value=t, 
                           bg=c["bg"], fg=c["fg"], selectcolor=c["bg"]).pack(side=tk.LEFT, padx=20)
        
        def save():
            new_theme = var_theme.get()
            if new_theme != self.tm.current_theme_name:
                self.tm.set_theme(new_theme)
                self.apply_theme_to_widgets()
            dlg.destroy()
            self.log("Settings saved.", "success")

        tk.Button(dlg, text="SAVE", command=save, bg=c["accent"], fg="white", 
                  relief="flat", padx=20).pack(pady=20)

    def import_json_dialog(self):
        filename = filedialog.askopenfilename(title="Import JSON", filetypes=[("JSON", "*.json")])
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                
                items = content if isinstance(content, list) else [dict(term=k, **v) for k, v in content.items()]
                count = 0
                for item in items:
                    term = item.get("term", item.get("word"))
                    if term:
                        self.db.upsert_word({
                            'term': term, 
                            'pronunciation': item.get("pronunciation", ""),
                            'pos': item.get("part_of_speech", item.get("pos", "")),
                            'meaning': item.get("definition", item.get("meaning", "")),
                            'example': item.get("example", "")
                        })
                        count += 1
                self.log(f"Imported {count} items.", "success")
                self.refresh_list()
            except Exception as e:
                self.log(f"Import Error: {e}", "error")

    def log(self, message: str, level: str = "info"):
        self.log_text.config(state="normal")
        c = self.tm.colors
        
        tags = {
            "info": c["log_fg_info"],
            "error": c["log_fg_err"],
            "success": c["accent"],
            "warn": "#FFD700" if self.tm.current_theme_name == "Dark" else "#FF8C00"
        }
        
        for tag, color in tags.items():
            self.log_text.tag_config(tag, foreground=color)
            
        timestamp = time.strftime('[%H:%M:%S]')
        self.log_text.insert(tk.END, f"{timestamp} ", "info")
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def apply_theme_to_widgets(self):
        """現在のテーマカラーを全ウィジェットに適用"""
        c = self.tm.colors
        self.root.configure(bg=c["bg"])
        
        # 再帰的に適用しない（ウィジェット個別に設定が必要なため）
        # 主要なコンテナとラベル
        for w in [self.widgets.get("header_frame"), self.widgets.get("content_frame"), 
                  self.widgets.get("log_frame"), self.widgets.get("search_frame"),
                  self.widgets.get("left_group"), self.widgets.get("order_frame"),
                  self.widgets.get("detail_frame"), self.widgets.get("btn_box"),
                  self.frame_read, self.frame_write, self.widgets.get("paned")]:
            if w: w.configure(bg=c["bg"])

        # ラベル
        for w in [self.widgets.get("lbl_search"), self.widgets.get("lbl_detail_term"), 
                  self.widgets.get("lbl_write_title"), self.widgets.get("lbl_log_title")]:
            if w: w.configure(bg=c["bg"], fg=c["fg"])
        
        for lbl in self.entry_labels:
            lbl.configure(bg=c["bg"], fg=c["fg_dim"])

        # 入力フィールド
        entry_conf = {"bg": c["input_bg"], "fg": c["input_fg"], "insertbackground": c["fg"]}
        if self.entry_search: self.entry_search.configure(**entry_conf)
        for ent in self.entries.values(): ent.configure(**entry_conf)
        
        # リストボックス・テキスト
        if self.listbox:
            self.listbox.configure(bg=c["list_bg"], fg=c["list_fg"], 
                                   selectbackground=c["select_bg"], selectforeground=c["select_fg"])
        if self.detail_text:
            self.detail_text.configure(bg=c["bg"], fg=c["fg"])
        if self.log_text:
            self.log_text.configure(bg=c["input_bg"], fg=c["fg"])

        # ボタン
        btn_bg = c.get("btn_bg", "#333333")
        for key in ["btn_import", "btn_config", "btn_up", "btn_down", "btn_clear"]:
            if w := self.widgets.get(key): w.configure(bg=btn_bg, fg=c["fg"])
            
        if w := self.widgets.get("btn_save"): w.configure(bg=c["accent"], fg="#FFF")
        if w := self.widgets.get("btn_delete"): w.configure(bg="#d32f2f", fg="#FFF")
        if w := self.widgets.get("btn_mode"): 
             w.configure(bg=c["accent"] if self.current_mode == "write" else btn_bg, 
                         fg="#FFF" if self.current_mode == "write" else c["fg"])

        # ラジオボタン
        for rb in self.radios:
            rb.configure(bg=c["bg"], fg=c["fg"], selectcolor=c["bg"], 
                         activebackground=c["bg"], activeforeground=c["fg"])
        
        # OptionMenu
        if hasattr(self, "pos_menu"):
            self.pos_menu.configure(bg=c["input_bg"], fg=c["fg"], 
                                    activebackground=c["accent"], activeforeground="#FFF")
            self.pos_menu["menu"].configure(bg=c["input_bg"], fg=c["fg"])

if __name__ == "__main__":
    # 高DPI対応 (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    
    root = tk.Tk()
    app = ReDicSearcherApp(root)
    root.mainloop()