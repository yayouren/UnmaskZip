#!/usr/bin/env python3
"""
解压小助手 GUI 版 - 支持拖拽、每文件状态、同目录解压
"""

import sys, os, re, json, base64, shutil, hashlib, subprocess, tempfile, traceback, threading
from pathlib import Path

# ---------- 加密 ----------
try:
    from cryptography.fernet import Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

# ---------- GUI ----------
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkinterdnd2 import TkinterDnD

# ---------- 解压库 ----------
try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False

if getattr(sys, "frozen", False):
    SCRIPT_DIR = Path(sys.executable).parent
else:
    SCRIPT_DIR = Path(__file__).parent

CONFIG_FILE = SCRIPT_DIR / "config.json"
PASSWORDS_FILE = SCRIPT_DIR / "passwords.dat"
KEY_FILE = SCRIPT_DIR / ".key"
BASE_OUTPUT = SCRIPT_DIR / "_extracted"

TARGET_EXTS = {".zip", ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm",
               ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

_7Z_PATHS = [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]
_RAR_PATHS = [r"C:\Program Files\WinRAR\WinRAR.exe", r"C:\Program Files (x86)\WinRAR\WinRAR.exe"]

# ===================== 加密工具 =====================
def _get_cipher():
    if not KEY_FILE.exists():
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
    else:
        key = KEY_FILE.read_bytes()
    return Fernet(key)

def encrypt_data(data: str) -> str:
    if HAS_FERNET:
        return _get_cipher().encrypt(data.encode()).decode()
    return base64.b64encode(data.encode()).decode()

def decrypt_data(enc: str) -> str:
    if HAS_FERNET:
        return _get_cipher().decrypt(enc.encode()).decode()
    return base64.b64decode(enc.encode()).decode()

# ===================== 配置 =====================
DEFAULT_CONFIG = {"method": "auto", "external_tool": "", "output_dir": str(BASE_OUTPUT)}

def load_config():
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except: pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def load_passwords():
    if not PASSWORDS_FILE.exists(): return []
    try:
        data = json.loads(PASSWORDS_FILE.read_text(encoding="utf-8"))
        return [decrypt_data(p) for p in data]
    except: return []

def save_passwords(pwds):
    data = [encrypt_data(p) for p in pwds]
    PASSWORDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ===================== 外部工具扫描 =====================
def scan_external_tools():
    found = []
    try:
        import winreg
        for hive, key in [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\7-Zip"),
                           (winreg.HKEY_CURRENT_USER, r"SOFTWARE\7-Zip")]:
            try:
                with winreg.OpenKey(hive, key) as k:
                    p, _ = winreg.QueryValueEx(k, "Path")
                    exe = Path(p) / "7z.exe"
                    if exe.exists(): found.append((str(exe), "7-Zip"))
            except: pass
        for hive, key in [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe"),
                           (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe")]:
            try:
                with winreg.OpenKey(hive, key) as k:
                    p, _ = winreg.QueryValueEx(k, "")
                    if Path(p).exists(): found.append((p, "WinRAR"))
            except: pass
    except: pass
    for name in ["7z.exe", "7zr.exe", "WinRAR.exe"]:
        p = shutil.which(name)
        if p and p not in [f[0] for f in found]: found.append((p, Path(p).stem))
    for p in _7Z_PATHS + _RAR_PATHS:
        if Path(p).exists() and p not in [f[0] for f in found]: found.append((p, Path(p).stem))
    return found

# ===================== 解压核心 =====================
def _extract_pyzipper(filepath, out_dir, passwords, log_cb):
    try:
        with pyzipper.AESZipFile(filepath, "r") as zf:
            zf.extractall(out_dir)
        log_cb(f"  [√] 无密码 (pyzipper)")
        return True
    except RuntimeError: pass
    except: return False
    for pwd in passwords:
        try:
            with pyzipper.AESZipFile(filepath, "r") as zf:
                zf.extractall(out_dir, pwd=pwd.encode("utf-8"))
            log_cb(f"  [√] 密码解压 (pyzipper): {pwd}")
            return True
        except RuntimeError: continue
        except: continue
    return False

def _extract_pyzipper_pk(filepath, out_dir, passwords, log_cb):
    if not HAS_PYZIPPER: return False
    try: raw = filepath.read_bytes()
    except: return False
    pos = raw.rfind(b'PK\x05\x06')
    if pos == -1: pos = raw.find(b'PK\x03\x04')
    if pos == -1: return False
    tmp = Path(tempfile.gettempdir()) / f"_ext_{filepath.stem}.zip"
    try:
        tmp.write_bytes(raw[pos:])
        ok = _extract_pyzipper(tmp, out_dir, passwords, log_cb)
        try: tmp.unlink()
        except: pass
        return ok
    except: return False

def _extract_external(filepath, out_dir, passwords, tool_path, log_cb):
    if not tool_path or not Path(tool_path).exists(): return False
    is_rar = "rar" in Path(tool_path).name.lower()
    cf = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    try:
        cmd = [tool_path, "x", "-y", str(filepath), f"-o{out_dir}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, creationflags=cf)
        if r.returncode == 0:
            log_cb(f"  [√] 无密码 ({Path(tool_path).stem})")
            return True
    except: pass
    for pwd in passwords:
        try:
            cmd = [tool_path, "x", "-y", f"-p{pwd}", str(filepath), f"-o{out_dir}"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, creationflags=cf)
            if r.returncode == 0:
                log_cb(f"  [√] 密码解压 ({Path(tool_path).stem}): {pwd}")
                return True
        except: continue
    return False

def _flatten_single(out_dir, base_out, log_cb):
    items = list(out_dir.iterdir())
    if len(items) != 1: return
    item = items[0]
    dest = base_out / item.name

    if dest.exists():
        if item.is_dir():
            # 文件夹存在 → 合并内容
            try:
                for child in item.iterdir():
                    cd = dest / child.name
                    if cd.exists():
                        stem, suffix = child.stem, child.suffix
                        n = 1
                        while cd.exists():
                            cd = dest / f"{stem}_{n}{suffix}"
                            n += 1
                    shutil.move(str(child), str(cd))
                item.rmdir()
                out_dir.rmdir()
                log_cb(f"    → 合并到: {dest.name}")
            except Exception as e:
                log_cb(f"    [!] 合并失败: {e}")
            return
        else:
            # 文件重名 → 加后缀
            stem, suffix = dest.stem, dest.suffix
            n = 1
            while dest.exists():
                dest = base_out / f"{stem}_{n}{suffix}"
                n += 1
    try:
        shutil.move(str(item), str(dest))
        out_dir.rmdir()
        log_cb(f"    → 平铺: {dest.name}")
    except Exception as e:
        log_cb(f"    [!] 整理失败: {e}")

def process_one_file(fp, passwords, method, tool_path, base_out, log_cb):
    """处理单个文件，返回是否成功"""
    fp = Path(fp)
    log_cb(f"[*] {fp.name}")

    out_dir = base_out / fp.stem
    if out_dir.exists() and any(out_dir.iterdir()):
        log_cb(f"  [-] 已解压，跳过")
        return True

    out_dir.mkdir(parents=True, exist_ok=True)
    ok = False

    if method in ("auto", "pyzipper") and HAS_PYZIPPER:
        ok = _extract_pyzipper(fp, out_dir, passwords, log_cb)
    if not ok and method in ("auto", "7z", "rar") and tool_path:
        ok = _extract_external(fp, out_dir, passwords, tool_path, log_cb)
    if not ok and method == "auto":
        ok = _extract_pyzipper_pk(fp, out_dir, passwords, log_cb)

    if not ok:
        log_cb(f"  [-] 非压缩包或密码不匹配")
        try:
            if not any(out_dir.iterdir()): out_dir.rmdir()
        except: pass
        return False

    # 递归处理内层
    _recurse_dir(out_dir, passwords, method, tool_path, base_out, log_cb)

    # 平铺
    if out_dir.exists():
        _flatten_single(out_dir, base_out, log_cb)
    return True

def _recurse_dir(folder, passwords, method, tool_path, base_out, log_cb):
    targets = []
    try:
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in TARGET_EXTS:
                targets.append(f)
    except: return
    for f in sorted(targets):
        out_dir = base_out / f.stem
        if out_dir.exists() and any(out_dir.iterdir()): continue
        out_dir.mkdir(parents=True, exist_ok=True)
        ok = False
        if method in ("auto", "pyzipper") and HAS_PYZIPPER:
            ok = _extract_pyzipper(f, out_dir, passwords, log_cb)
        if not ok and method in ("auto", "7z", "rar") and tool_path:
            ok = _extract_external(f, out_dir, passwords, tool_path, log_cb)
        if not ok and method == "auto":
            ok = _extract_pyzipper_pk(f, out_dir, passwords, log_cb)
        if not ok:
            try:
                if not any(out_dir.iterdir()): out_dir.rmdir()
            except: pass
            continue
        if out_dir.exists():
            _flatten_single(out_dir, base_out, log_cb)

# ===================== GUI =====================
class App:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("解压小助手")
        self.root.geometry("750x580")
        self.root.minsize(650, 450)

        self.config = load_config()
        self.passwords = load_passwords()
        self.files = []
        self._file_ids = {}

        self._build_menu()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        menubar.add_command(label="密码本", command=self._open_passwords)
        menubar.add_command(label="设置", command=self._open_settings)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Button(top, text="添加文件", command=self._add_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="清空列表", command=self._clear_files).pack(side=tk.LEFT, padx=3)

        self.same_dir_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="解压到同目录", variable=self.same_dir_var).pack(side=tk.LEFT, padx=10)

        self.log_visible = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="显示日志", variable=self.log_visible,
                        command=self._toggle_log).pack(side=tk.LEFT, padx=10)

        ttk.Button(top, text="开始解压", command=self._start_extract).pack(side=tk.RIGHT, padx=3)

        # Treeview
        list_frame = ttk.LabelFrame(self.root, text="文件列表（可拖拽文件/文件夹到此处）", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(list_frame, columns=("name", "status"), show="headings", height=8)
        self.tree.heading("name", text="文件名")
        self.tree.heading("status", text="状态")
        self.tree.column("name", width=450, minwidth=200)
        self.tree.column("status", width=100, minwidth=80, anchor=tk.CENTER)
        tree_scroll = ttk.Scrollbar(list_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Delete>", lambda e: self._remove_selected())
        self.tree.drop_target_register('*')
        self.tree.dnd_bind('<<Drop>>', self._on_drop)

        # 进度条
        prog_frame = ttk.Frame(self.root, padding=10)
        prog_frame.pack(fill=tk.X)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.prog_label = ttk.Label(prog_frame, text="0/0", width=8)
        self.prog_label.pack(side=tk.RIGHT, padx=5)

        # 日志
        self.log_frame = ttk.LabelFrame(self.root, text="日志", padding=5)
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log = scrolledtext.ScrolledText(self.log_frame, height=8, state=tk.DISABLED, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        self.status = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W, padding=5)
        self.status.pack(fill=tk.X)

        self.log_msg("解压小助手 GUI 已启动")
        self.log_msg(f"密码本: {len(self.passwords)} 个密码")
        self.log_msg(f"解压方式: {self.config.get('method', 'auto')}")

    def _toggle_log(self):
        if self.log_visible.get():
            self.log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5,
                                after=self.tree.master)
        else:
            self.log_frame.pack_forget()

    def log_msg(self, msg):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _add_files(self):
        for p in filedialog.askopenfilenames(title="选择文件"):
            self._append_file(p)

    def _on_drop(self, event):
        paths = re.findall(r'\{(.+?)\}', event.data)
        if not paths: paths = event.data.split()
        added = 0
        for p in paths:
            p = p.strip()
            if not p or not Path(p).exists(): continue
            pp = Path(p)
            if pp.is_dir(): added += self._scan_dir(pp)
            elif self._append_file(p): added += 1
        if added: self.log_msg(f"[*] 拖入 {added} 个文件")

    def _scan_dir(self, folder):
        count = 0
        try:
            for f in Path(folder).rglob("*"):
                if f.is_file() and f.suffix.lower() in TARGET_EXTS:
                    if self._append_file(str(f)): count += 1
        except Exception as e:
            self.log_msg(f"[!] 扫描出错: {e}")
        return count

    def _append_file(self, path):
        if path in self._file_ids: return False
        item_id = self.tree.insert("", tk.END, values=(Path(path).name, "等待"))
        self._file_ids[path] = item_id
        self.files.append(path)
        return True

    def _clear_files(self):
        self.files.clear()
        self._file_ids.clear()
        for item in self.tree.get_children(): self.tree.delete(item)

    def _remove_selected(self):
        for item_id in self.tree.selection():
            for p, iid in list(self._file_ids.items()):
                if iid == item_id:
                    del self._file_ids[p]
                    if p in self.files: self.files.remove(p)
                    break
            self.tree.delete(item_id)

    def _set_status(self, path, st):
        if path in self._file_ids:
            self.tree.set(self._file_ids[path], "status", st)

    def _start_extract(self):
        if not self.files: return messagebox.showwarning("提示", "请先添加文件")
        if not self.passwords: return messagebox.showwarning("提示", "密码本为空")

        self.progress["value"] = 0
        self.prog_label.config(text="0/0")
        self.status.config(text="解压中...")
        self.log_msg("\n" + "=" * 40)

        for p in self.files: self._set_status(p, "等待")

        same_dir = self.same_dir_var.get()
        total = len(self.files)

        def log_cb(msg):
            self.root.after(0, lambda: self.log_msg(msg))

        def done():
            self.root.after(0, lambda: self.status.config(text="完成"))

        def worker():
            try:
                files = list(self.files)
                method = self.config.get("method", "auto")
                tool = self.config.get("external_tool", "")
                for i, fp in enumerate(files):
                    self.root.after(0, lambda p=fp: self._set_status(p, "解压中"))
                    base = Path(fp).parent if same_dir else Path(self.config.get("output_dir", str(BASE_OUTPUT)))
                    base.mkdir(parents=True, exist_ok=True)
                    ok = process_one_file(fp, self.passwords, method, tool, base, log_cb)
                    self.root.after(0, lambda p=fp, o=ok: self._set_status(p, "完成 ✅" if o else "失败 ❌"))
                    pct = int((i + 1) / total * 100)
                    self.root.after(0, lambda v=pct: self.progress.configure(value=v))
                    self.root.after(0, lambda v=pct, t=total: self.prog_label.configure(text=f"{v}% ({i+1}/{t})"))
                log_cb("[*] 全部完成")
            except Exception:
                log_cb(traceback.format_exc())
            finally:
                done()

        threading.Thread(target=worker, daemon=True).start()

    def _open_settings(self):
        SettingsDialog(self.root, self.config, self._on_config_changed)

    def _on_config_changed(self, cfg):
        self.config = cfg
        save_config(cfg)
        self.log_msg(f"[*] 设置已更新")

    def _open_passwords(self):
        PasswordDialog(self.root, self.passwords, self._on_passwords_changed)

    def _on_passwords_changed(self, pwds):
        self.passwords = pwds
        save_passwords(pwds)
        self.log_msg(f"[*] 密码本已更新: {len(pwds)} 个密码")

    def _on_close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()

# ===================== 设置对话框 =====================
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config, callback):
        super().__init__(parent)
        self.title("设置")
        self.geometry("500x380")
        self.resizable(False, False)
        self.config = dict(config)
        self.callback = callback
        self.tools = scan_external_tools()
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="优先解压方式:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.method_var = tk.StringVar(value=self.config.get("method", "auto"))
        methods = [("自动", "auto")]
        if HAS_PYZIPPER: methods.append(("pyzipper (内置)", "pyzipper"))
        methods += [("7-Zip", "7z"), ("WinRAR", "rar")]
        for i, (text, val) in enumerate(methods):
            ttk.Radiobutton(frame, text=text, variable=self.method_var, value=val).grid(
                row=i, column=1, sticky=tk.W, padx=10)

        row = len(methods)
        ttk.Label(frame, text="外部工具路径:").grid(row=row, column=0, sticky=tk.W, pady=10)
        self.tool_var = tk.StringVar(value=self.config.get("external_tool", ""))
        tf = ttk.Frame(frame); tf.grid(row=row, column=1, sticky=tk.EW, padx=10)
        ttk.Entry(tf, textvariable=self.tool_var, width=35).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(tf, text="浏览", command=self._browse_tool).pack(side=tk.LEFT, padx=2)

        row += 1
        if self.tools:
            ttk.Label(frame, text="扫描到:").grid(row=row, column=0, sticky=tk.W, pady=5)
            lf = ttk.Frame(frame); lf.grid(row=row, column=1, sticky=tk.EW, padx=10)
            for path, name in self.tools:
                f = ttk.Frame(lf); f.pack(fill=tk.X)
                ttk.Label(f, text=f"{name}: {path}", font=("", 7)).pack(side=tk.LEFT)
                ttk.Button(f, text="选用", width=4, command=lambda p=path: self.tool_var.set(p)).pack(side=tk.RIGHT)
        else:
            ttk.Label(frame, text="未扫描到", foreground="gray").grid(row=row, column=1, sticky=tk.W, padx=10, pady=5)

        row += 1
        ttk.Label(frame, text="输出目录:").grid(row=row, column=0, sticky=tk.W, pady=10)
        self.out_var = tk.StringVar(value=self.config.get("output_dir", str(BASE_OUTPUT)))
        of = ttk.Frame(frame); of.grid(row=row, column=1, sticky=tk.EW, padx=10)
        ttk.Entry(of, textvariable=self.out_var, width=35).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(of, text="浏览", command=self._browse_out).pack(side=tk.LEFT, padx=2)

        row += 1
        btn = ttk.Frame(frame); btn.grid(row=row, column=0, columnspan=2, pady=20)
        ttk.Button(btn, text="保存", command=self._save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="取消", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _browse_tool(self):
        p = filedialog.askopenfilename(title="选择解压工具", filetypes=[("可执行文件", "*.exe")])
        if p: self.tool_var.set(p)

    def _browse_out(self):
        p = filedialog.askdirectory(title="选择输出目录")
        if p: self.out_var.set(p)

    def _save(self):
        self.config["method"] = self.method_var.get()
        self.config["external_tool"] = self.tool_var.get()
        self.config["output_dir"] = self.out_var.get()
        self.callback(self.config)
        self.destroy()

# ===================== 密码本对话框 =====================
class PasswordDialog(tk.Toplevel):
    def __init__(self, parent, passwords, callback):
        super().__init__(parent)
        self.title("密码本")
        self.geometry("500x420")
        self.resizable(True, True)
        self.passwords = list(passwords)
        self.callback = callback
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        lf = ttk.LabelFrame(frame, text=f"密码列表 ({len(self.passwords)} 条)", padding=5)
        lf.pack(fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(lf, height=12)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(lf, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)
        for p in self.passwords: self.listbox.insert(tk.END, p)

        btn_row = ttk.Frame(frame); btn_row.pack(fill=tk.X, pady=5)
        self.entry = ttk.Entry(btn_row, width=20); self.entry.pack(side=tk.LEFT, padx=2)
        self.entry.bind("<Return>", lambda e: self._add())
        ttk.Button(btn_row, text="添加", command=self._add).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="删除选中", command=self._delete).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="导入", command=self._import).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="导出", command=self._export).pack(side=tk.LEFT, padx=2)

        bottom = ttk.Frame(frame); bottom.pack(fill=tk.X, pady=10)
        ttk.Button(bottom, text="保存", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _add(self):
        t = self.entry.get().strip()
        if t and t not in self.passwords:
            self.passwords.append(t); self.listbox.insert(tk.END, t); self.entry.delete(0, tk.END)

    def _delete(self):
        sel = self.listbox.curselection()
        if not sel: return
        for i in reversed(sel): self.listbox.delete(i); del self.passwords[i]

    def _import(self):
        p = filedialog.askopenfilename(title="导入密码", filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not p: return
        try:
            with open(p, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            added = 0
            for l in lines:
                if l not in self.passwords:
                    self.passwords.append(l); self.listbox.insert(tk.END, l); added += 1
            messagebox.showinfo("导入完成", f"导入了 {added} 条密码")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _export(self):
        p = filedialog.asksaveasfilename(title="导出密码", defaultextension=".txt", filetypes=[("文本文件", "*.txt")])
        if not p: return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 密码本导出\n")
                for pw in self.passwords: f.write(pw + "\n")
            messagebox.showinfo("导出完成", f"已导出 {len(self.passwords)} 条密码")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _save(self):
        self.callback(self.passwords)
        self.destroy()

# ===================== 入口 =====================
def main():
    app = App()
    app.run()

if __name__ == "__main__":
    main()
