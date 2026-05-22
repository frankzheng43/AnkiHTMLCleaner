"""
Anki Apkg 清理工具 — 三标签页版
仅支持旧版 apkg（collection.anki2，无 zstd 压缩）
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import zipfile
import sqlite3
import os
import re
import html
import shutil
import tempfile
import threading
import struct

# zstd 支持（可选）
try:
    import zstandard as _zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


# ── 清理引擎 ──────────────────────────────────────────────

class CleanEngine:
    def __init__(self, config):
        self.config = config

    def clean(self, text):
        if not text:
            return text

        if self.config.get('rm_style'):
            text = re.sub(r'\s+style\s*=\s*"[^"]*"', '', text)
            text = re.sub(r"\s+style\s*=\s*'[^']*'", '', text)
        if self.config.get('rm_class'):
            text = re.sub(r'\s+class\s*=\s*"[^"]*"', '', text)
            text = re.sub(r"\s+class\s*=\s*'[^']*'", '', text)
        if self.config.get('rm_span'):
            text = re.sub(r'</?span\b[^>]*>', '', text)
        if self.config.get('rm_tbody'):
            text = re.sub(r'</?tbody\b[^>]*>', '', text)
        if self.config.get('p_to_br'):
            text = re.sub(r'<p\b[^>]*>', '', text)
            text = re.sub(r'</p\s*>', '<br>', text)
        if self.config.get('unescape'):
            text = html.unescape(text)
        if self.config.get('rm_crap'):
            text = text.replace('_x000D_', '')
            text = text.replace('\r', '')
            text = re.sub(r'<!--.*?-->', '', text)
        if self.config.get('collapse_br'):
            text = re.sub(r'(<br\s*/?\s*>\s*){2,}', r'\1', text)
        if self.config.get('trim_br'):
            text = re.sub(r'^\s*<br\s*/?\s*>', '', text)
            text = re.sub(r'<br\s*/?\s*>\s*$', '', text)
            text = re.sub(r'(<div\b[^>]*>)\s*<br\s*/?\s*>', r'\1', text)
            text = re.sub(r'<br\s*/?\s*>\s*</div\s*>', '</div>', text)
        if self.config.get('table_border'):
            if re.search(r'<table\b', text) and not re.search(r'<table\b[^>]*\bborder\s*=', text):
                text = re.sub(r'<table\b', '<table border="1" style="border-collapse: collapse"', text)
        if self.config.get('rm_cjk_space'):
            cjk = r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]'
            text = re.sub(f'({cjk})\\s+({cjk})', r'\1\2', text)
        if self.config.get('add_cjk_space'):
            cjk = r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]'
            text = re.sub(f'({cjk})([a-zA-Z])', r'\1 \2', text)
            text = re.sub(f'([a-zA-Z])({cjk})', r'\1 \2', text)
            text = re.sub(f'({cjk})(\\d)', r'\1 \2', text)
            text = re.sub(f'(\\d)({cjk})', r'\1 \2', text)
        for find, replace in self.config.get('custom_regex', []):
            try:
                text = re.sub(find, replace, text)
            except:
                pass
        text = re.sub(r'  +', ' ', text)
        return text.strip()


# ── Apkg 处理器（仅旧版：zip → *.anki2 → sqlite） ──

class ApkgProcessor:
    def __init__(self):
        self.temp_dir = None
        self.db_path = None       # 原始数据库路径
        self.cleaned_db = None    # 清理后的数据库路径
        self.media_files = []     # apkg 中的媒体文件列表
        self.note_count = 0
        self.notetypes = []       # [(id, name, [字段名])]
        self.original_apkg = None

    def extract(self, apkg_path, log_callback=None):
        """解压 apkg（zip），支持旧版 anki2 和新版 zstd 压缩的 anki21b"""
        self.original_apkg = apkg_path
        self.temp_dir = tempfile.mkdtemp(prefix='anki_')

        # 1. 解压 zip
        with zipfile.ZipFile(apkg_path, 'r') as zf:
            names = zf.namelist()
            db_candidates = [n for n in names if n.startswith('collection.anki') and not n.endswith('.bak')]
            if not db_candidates:
                raise RuntimeError('未找到 collection.anki* 文件')
            self.media_files = [n for n in names if not n.startswith('collection.anki')]
            zf.extractall(self.temp_dir)

        db_name = db_candidates[0]
        db_path = os.path.join(self.temp_dir, db_name)

        # 2. 检查是否 zstd 压缩（魔数 0x28b52ffd）
        is_zstd = False
        with open(db_path, 'rb') as f:
            magic = f.read(4)
        if magic == b'\x28\xb5\x2f\xfd':
            is_zstd = True

        if is_zstd:
            if not ZSTD_AVAILABLE:
                raise RuntimeError(
                    '新版 apkg（zstd 压缩）需要安装 zstandard 包\n'
                    '请运行: pip install zstandard')

            with open(db_path, 'rb') as f:
                compressed = f.read()
            dctx = _zstd.ZstdDecompressor()
            decompressed = dctx.decompress(compressed, max_output_size=100 * 1024 * 1024)
            self.db_path = os.path.join(self.temp_dir, 'decompressed.sqlite')
            with open(self.db_path, 'wb') as f:
                f.write(decompressed)
            if log_callback:
                log_callback(f'   zstd 解压: {len(compressed)/1024:.0f} KB → {len(decompressed)/1024:.0f} KB')
        else:
            self.db_path = db_path

        # 3. 读取笔记信息
        self._load_info()

        if log_callback:
            log_callback(f'✅ 已解压: {os.path.basename(apkg_path)}')
            log_callback(f'   数据库: {db_name}')
            log_callback(f'   媒体文件: {len(self.media_files)} 个')
            log_callback(f'   笔记: {self.note_count} 条')
            for _, name, fields in self.notetypes:
                log_callback(f'   📝 {name}: {fields}')

    def _load_info(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        self.note_count = cur.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        try:
            cur.execute("SELECT id, name FROM notetypes")
            for nid, name in cur.fetchall():
                cur.execute("SELECT name FROM fields WHERE ntid = ? ORDER BY ord", (nid,))
                self.notetypes.append((nid, name, [r[0] for r in cur.fetchall()]))
        except:
            pass
        conn.close()

    def clean(self, engine, log_callback=None):
        """对数据库执行清理，生成 cleaned_db"""
        if not self.db_path:
            raise RuntimeError('请先解压 apkg')

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        rows = cur.execute("SELECT id, mid, flds FROM notes").fetchall()
        total = len(rows)

        for idx, (note_id, mid, flds) in enumerate(rows):
            if log_callback and idx % 200 == 0:
                log_callback(f'⏳ 清理中... {idx}/{total}')

            fields = flds.split('\x1f')
            changed = False
            for fi in range(len(fields)):
                cleaned = engine.clean(fields[fi])
                if cleaned != fields[fi]:
                    fields[fi] = cleaned
                    changed = True
            if changed:
                cur.execute("UPDATE notes SET flds = ? WHERE id = ?", ('\x1f'.join(fields), note_id))

        conn.commit()
        conn.close()

        # 生成清理版副本
        self.cleaned_db = os.path.join(self.temp_dir, 'collection.cleaned.anki2')
        shutil.copy2(self.db_path, self.cleaned_db)

        if log_callback:
            log_callback(f'✅ 清理完成: {total} 条笔记')

    def repack(self, output_path, log_callback=None):
        """打包清理后的数据库 + 媒体文件 → apkg（自动匹配原格式）"""
        if not self.cleaned_db:
            raise RuntimeError('请先执行清理')

        # 读取清理后的数据库
        with open(self.cleaned_db, 'rb') as f:
            db_data = f.read()

        # 根据原文件决定是否 zstd 压缩
        orig_name = os.path.basename(self.db_path)
        if orig_name.endswith('anki21b') and ZSTD_AVAILABLE:
            cctx = _zstd.ZstdCompressor(level=3)
            db_data = cctx.compress(db_data)
            out_name = 'collection.anki21b'
            if log_callback:
                log_callback(f'   zstd 压缩: {len(db_data)/1024:.0f} KB')
        else:
            out_name = orig_name or 'collection.anki2'

        # 写入临时文件
        tmp_db = os.path.join(self.temp_dir, 'out_' + out_name)
        with open(tmp_db, 'wb') as f:
            f.write(db_data)

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, out_name)
            for fname in self.media_files:
                fpath = os.path.join(self.temp_dir, fname)
                if os.path.exists(fpath):
                    zf.write(fpath, fname)
        os.remove(tmp_db)

        if log_callback:
            size = os.path.getsize(output_path) / 1024
            log_callback(f'✅ 已打包: {os.path.basename(output_path)} ({size:.0f} KB)')

    def export_db(self, src_path, dst_path):
        """导出中间数据库"""
        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
            return os.path.getsize(dst_path)
        return 0

    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None


# ── GUI ─────────────────────────────────────────────────────

class AnkiCleanerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Anki Apkg 清理工具')
        self.root.geometry('760x700')
        self.root.minsize(640, 600)

        self.processor = ApkgProcessor()
        self.config = {}  # 当前清理配置

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill='both', expand=True)

        # 标题
        ttk.Label(main, text='Anki Apkg 清理工具', font=('', 15, 'bold')).pack(anchor='w')
        ttk.Label(main, text='解压 → 清理 → 打包，三步完成', foreground='gray').pack(anchor='w', pady=(0, 8))

        # 笔记本（三标签）
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill='both', expand=True)

        self._build_tab1()  # 解压
        self._build_tab2()  # 清理
        self._build_tab3()  # 打包

        # 状态栏
        self.status = ttk.Label(main, text='就绪', relief='sunken', anchor='w')
        self.status.pack(fill='x', pady=(6, 0))

    # ── Tab 1: 解压 ──

    def _build_tab1(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='① 解压')

        # 文件选择
        ttk.Label(tab, text='选择 apkg 文件：').pack(anchor='w')
        row = ttk.Frame(tab)
        row.pack(fill='x', pady=(4, 8))
        self.file_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.file_var).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='浏览', command=self._browse_apkg, width=8).pack(side='right', padx=(4, 0))

        # 按钮行
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill='x')
        self.btn_extract = ttk.Button(btn_row, text='解压', command=self._do_extract)
        self.btn_extract.pack(side='left')
        self.btn_export1 = ttk.Button(btn_row, text='导出 SQLite', command=self._export_raw_db, state='disabled')
        self.btn_export1.pack(side='left', padx=(8, 0))

        # 信息展示
        self.info1 = tk.Text(tab, height=8, state='disabled', wrap='word', bg='#f5f5f5')
        self.info1.pack(fill='both', expand=True, pady=(8, 0))

        # 切换到下一步的提示
        self.tab1_status = ttk.Label(tab, text='', foreground='gray')
        self.tab1_status.pack(anchor='w', pady=(4, 0))

    def _browse_apkg(self):
        path = filedialog.askopenfilename(
            title='选择 apkg 文件',
            filetypes=[('Anki 牌组', '*.apkg'), ('所有文件', '*.*')])
        if path:
            self.file_var.set(path)

    def _log_info(self, widget, msg):
        widget.configure(state='normal')
        widget.insert('end', msg + '\n')
        widget.see('end')
        widget.configure(state='disabled')
        self.root.update()

    def _do_extract(self):
        path = self.file_var.get()
        if not path:
            messagebox.showwarning('提示', '请先选择 apkg 文件')
            return

        self.btn_extract.configure(state='disabled')
        self._log_info(self.info1, '⏳ 正在解压...')

        def task():
            try:
                self.processor = ApkgProcessor()
                self.processor.extract(path, lambda m: self._log_info(self.info1, m))
                self.btn_export1.configure(state='normal')
                self.tab1_status.configure(
                    text=f'✅ 已解压 {self.processor.note_count} 条笔记，可进入下一步',
                    foreground='green')
            except Exception as e:
                self._log_info(self.info1, f'❌ 失败: {e}')
                self.tab1_status.configure(text=f'❌ 解压失败', foreground='red')
            finally:
                self.btn_extract.configure(state='normal')

        threading.Thread(target=task, daemon=True).start()

    def _export_raw_db(self):
        if not self.processor or not self.processor.db_path:
            return
        path = filedialog.asksaveasfilename(
            title='导出原始 SQLite',
            initialdir='output',
            defaultextension='.anki2',
            filetypes=[('SQLite 数据库', '*.anki2;*.sqlite'), ('所有文件', '*.*')])
        if path:
            size = self.processor.export_db(self.processor.db_path, path)
            self._log_info(self.info1, f'📦 已导出: {os.path.basename(path)} ({size/1024:.0f} KB)')

    # ── Tab 2: 清理 ──

    def _build_tab2(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='② 清理')

        # 可滚动区域
        canvas = tk.Canvas(tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
        frame = ttk.Frame(canvas)

        canvas.bind('<Configure>', lambda e: canvas.itemconfig(1, width=e.width))
        frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)

        # 清理选项
        self.checks = {}
        options = [
            ('rm_style',      '删除 style 属性',         '清除所有标签上的 style="..."'),
            ('rm_class',      '删除 class 属性',         '清除所有标签上的 class="..."'),
            ('rm_span',       '删除 <span> 标签',        '无显示效果，仅保留内容'),
            ('rm_tbody',      '删除 <tbody> 标签',       '浏览器会自动插入'),
            ('p_to_br',       '<p> 转 <br>',             '<p>段落</p> → 段落<br>'),
            ('unescape',      'HTML 实体转字符',         '&times; → ×, &divide; → ÷'),
            ('rm_crap',       '清除 _x000D_ 和注释',     'Windows 换行残留和 HTML 注释'),
            ('collapse_br',   '多个 <br> 缩成一个',      '<br><br> → <br>'),
            ('trim_br',       '去掉首尾无意义 <br>',      '段首段尾及 <div> 前后的 <br>'),
            ('table_border',  '表格加默认黑边框',        '<table> → <table border="1">'),
            ('rm_cjk_space',  '删中文间多余空格',        '增值税 一般 → 增值税一般'),
            ('add_cjk_space', '中文与英/数间加空格',      '2025年 → 2025 年'),
        ]
        for key, label, desc in options:
            var = tk.BooleanVar(value=True)
            f = ttk.Frame(frame)
            f.pack(fill='x', pady=1)
            cb = ttk.Checkbutton(f, text=label, variable=var)
            cb.pack(side='left')
            ttk.Label(f, text=desc, foreground='gray', font=('', 9)).pack(side='left', padx=(8, 0))
            self.checks[key] = var

        # 自定义正则
        sep = ttk.Separator(frame, orient='horizontal')
        sep.pack(fill='x', pady=6)
        ttk.Label(frame, text='自定义查找替换（可选）', font=('', 9, 'bold')).pack(anchor='w')

        self.custom_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text='启用自定义正则', variable=self.custom_var).pack(anchor='w')

        reg_f = ttk.Frame(frame)
        reg_f.pack(fill='x', pady=(4, 0))
        ttk.Label(reg_f, text='查找:').grid(row=0, column=0, sticky='w')
        self.re_find = tk.StringVar()
        ttk.Entry(reg_f, textvariable=self.re_find).grid(row=0, column=1, sticky='ew', padx=(4, 0))
        ttk.Label(reg_f, text='替换:').grid(row=1, column=0, sticky='w', pady=(4, 0))
        self.re_repl = tk.StringVar()
        ttk.Entry(reg_f, textvariable=self.re_repl).grid(row=1, column=1, sticky='ew', padx=(4, 0), pady=(4, 0))
        reg_f.columnconfigure(1, weight=1)

        # 按钮
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill='x', pady=(6, 0))
        self.btn_clean = ttk.Button(btn_row, text='▶ 开始清理', command=self._do_clean)
        self.btn_clean.pack(side='left')
        self.btn_export2 = ttk.Button(btn_row, text='导出已清理 SQLite', command=self._export_cleaned_db, state='disabled')
        self.btn_export2.pack(side='left', padx=(8, 0))

        self.info2 = tk.Text(tab, height=5, state='disabled', wrap='word', bg='#f5f5f5')
        self.info2.pack(fill='x', pady=(6, 0))

    def _do_clean(self):
        if not self.processor or not self.processor.db_path:
            messagebox.showwarning('提示', '请先在 "① 解压" 中解压 apkg')
            return

        # 收集配置
        self.config = {k: v.get() for k, v in self.checks.items()}
        self.config['custom_regex'] = []
        if self.custom_var.get() and self.re_find.get():
            self.config['custom_regex'].append((self.re_find.get(), self.re_repl.get()))

        engine = CleanEngine(self.config)
        self.btn_clean.configure(state='disabled')
        self._log_info(self.info2, '⏳ 正在清理...')

        def task():
            try:
                self.processor.clean(engine, lambda m: self._log_info(self.info2, m))
                self.btn_export2.configure(state='normal')
                self._log_info(self.info2, '💡 可进入 "③ 打包" 生成 apkg，或点击导出按钮保存中间文件')
            except Exception as e:
                self._log_info(self.info2, f'❌ 失败: {e}')
            finally:
                self.btn_clean.configure(state='normal')

        threading.Thread(target=task, daemon=True).start()

    def _export_cleaned_db(self):
        if not self.processor or not self.processor.cleaned_db:
            return
        path = filedialog.asksaveasfilename(
            title='导出清理后的 SQLite',
            initialdir='output',
            defaultextension='.anki2',
            filetypes=[('SQLite 数据库', '*.anki2;*.sqlite'), ('所有文件', '*.*')])
        if path:
            size = self.processor.export_db(self.processor.cleaned_db, path)
            self._log_info(self.info2, f'📦 已导出: {os.path.basename(path)} ({size/1024:.0f} KB)')

    # ── Tab 3: 打包 ──

    def _build_tab3(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='③ 打包')

        ttk.Label(tab, text='输出文件：').pack(anchor='w')
        row = ttk.Frame(tab)
        row.pack(fill='x', pady=(4, 8))
        self.out_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.out_var).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='选择位置', command=self._browse_output, width=8).pack(side='right', padx=(4, 0))

        self.btn_pack = ttk.Button(tab, text='📦 打包为 apkg', command=self._do_pack)
        self.btn_pack.pack(anchor='w')

        self.info3 = tk.Text(tab, height=6, state='disabled', wrap='word', bg='#f5f5f5')
        self.info3.pack(fill='both', expand=True, pady=(8, 0))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title='保存为 apkg',
            initialdir='output',
            defaultextension='.apkg',
            filetypes=[('Anki 牌组', '*.apkg')])
        if path:
            self.out_var.set(path)

    def _do_pack(self):
        if not self.processor or not self.processor.cleaned_db:
            messagebox.showwarning('提示', '请先在 "② 清理" 中执行清理')
            return
        out = self.out_var.get()
        if not out:
            messagebox.showwarning('提示', '请选择输出位置')
            return

        self.btn_pack.configure(state='disabled')
        self._log_info(self.info3, '⏳ 正在打包...')

        def task():
            try:
                self.processor.repack(out, lambda m: self._log_info(self.info3, m))
            except Exception as e:
                self._log_info(self.info3, f'❌ 失败: {e}')
            finally:
                self.btn_pack.configure(state='normal')

        threading.Thread(target=task, daemon=True).start()


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    app = AnkiCleanerApp()
    app.root.mainloop()


if __name__ == '__main__':
    main()
