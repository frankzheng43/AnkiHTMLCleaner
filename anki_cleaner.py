"""
Anki Apkg 清理工具 — 图形界面版
调用 core/ 下的独立模块完成三步操作
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import tempfile
import shutil
import json

from core.engine import CleanEngine, DEFAULT_CONFIG
from core.extract import ApkgExtractor
from core.clean import SqliteCleaner
from core.pack import ApkgPacker


class AnkiCleanerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('🧹 Anki Apkg 清理工具')
        self.root.geometry('780x700')
        self.root.minsize(640, 600)

        # 状态
        self.sqlite_path = None       # 原始 SQLite 路径
        self.cleaned_path = None      # 清理后的 SQLite 路径
        self.media_dir = None         # 媒体文件目录
        self.media_files = []         # 媒体文件列表
        self.note_count = 0
        self.original_db_name = None  # 原数据库文件名
        self.config = {}

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill='both', expand=True)

        # 标题
        title_f = ttk.Frame(main)
        title_f.pack(anchor='w', pady=(0, 8))
        ttk.Label(title_f, text='🧹 Anki Apkg 清理工具',
                  font=('', 16, 'bold')).pack(side='left')
        ttk.Label(title_f, text='  🗂️解压 → 🧼清理 → 📦打包',
                  foreground='gray').pack(side='left', padx=(12, 0))

        # 笔记本
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill='both', expand=True)

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()

        self.status = ttk.Label(main, text='就绪', relief='sunken', anchor='w')
        self.status.pack(fill='x', pady=(6, 0))

    # ── 工具方法 ──

    def _log(self, widget, msg):
        widget.configure(state='normal')
        widget.insert('end', msg + '\n')
        widget.see('end')
        widget.configure(state='disabled')
        self.root.update()

    def _set_status(self, text, color='black'):
        self.status.configure(text=text, foreground=color)

    # ── Tab 1: 解压 ──

    def _build_tab1(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='① 📂 解压')

        ttk.Label(tab, text='📁 选择 apkg 文件：').pack(anchor='w')
        row = ttk.Frame(tab)
        row.pack(fill='x', pady=(4, 8))
        self.file_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.file_var).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='📂 浏览', command=self._browse_apkg, width=8).pack(side='right', padx=(4, 0))

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill='x')
        self.btn_extract = ttk.Button(btn_row, text='🔓 解压', command=self._do_extract)
        self.btn_extract.pack(side='left')
        self.btn_export1 = ttk.Button(btn_row, text='💾 导出 SQLite', command=self._export_raw, state='disabled')
        self.btn_export1.pack(side='left', padx=(8, 0))

        self.info1 = tk.Text(tab, height=8, state='disabled', wrap='word', bg='#fafafa', font=('Consolas', 10))
        self.info1.pack(fill='both', expand=True, pady=(8, 0))

        self.tab1_status = ttk.Label(tab, text='', foreground='gray')
        self.tab1_status.pack(anchor='w', pady=(4, 0))

    def _browse_apkg(self):
        path = filedialog.askopenfilename(title='选择 apkg 文件', filetypes=[('Anki 牌组', '*.apkg'), ('所有文件', '*.*')])
        if path:
            self.file_var.set(path)

    def _do_extract(self):
        path = self.file_var.get()
        if not path:
            messagebox.showwarning('提示', '请先选择 apkg 文件')
            return

        self.btn_extract.configure(state='disabled')
        self._log(self.info1, '⏳ 正在解压...')

        def task():
            try:
                # 输出路径：临时目录 + 文件名
                out_dir = tempfile.mkdtemp(prefix='anki_')
                sqlite_out = os.path.join(out_dir, 'collection.sqlite')
                media_out = os.path.join(out_dir, 'media')

                ext = ApkgExtractor()
                result = ext.extract(path, sqlite_out, media_out)

                self.sqlite_path = sqlite_out
                self.media_dir = result['media_dir']
                self.media_files = result['media_files']
                self.note_count = result['note_count']
                self.original_db_name = result['original_db_name']

                self._log(self.info1, f'✅ 解压完成')
                self._log(self.info1, f'   数据库: {sqlite_out} ({os.path.getsize(sqlite_out)/1024:.0f} KB)')
                self._log(self.info1, f'   笔记: {self.note_count} 条')
                self._log(self.info1, f'   媒体文件: {len(self.media_files)} 个')

                self.btn_export1.configure(state='normal')
                self.tab1_status.configure(
                    text=f'✅ 已解压 {self.note_count} 条笔记，可进入下一步 🧼',
                    foreground='green')
            except Exception as e:
                self._log(self.info1, f'❌ 失败: {e}')
                self.tab1_status.configure(text='❌ 解压失败', foreground='red')
            finally:
                self.btn_extract.configure(state='normal')

        threading.Thread(target=task, daemon=True).start()

    def _export_raw(self):
        if not self.sqlite_path:
            return
        path = filedialog.asksaveasfilename(
            title='导出原始 SQLite',
            initialdir='output',
            defaultextension='.sqlite',
            filetypes=[('SQLite 数据库', '*.sqlite;*.anki2'), ('所有文件', '*.*')])
        if path:
            shutil.copy2(self.sqlite_path, path)
            self._log(self.info1, f'💾 已导出: {os.path.basename(path)} ({os.path.getsize(path)/1024:.0f} KB)')

    # ── Tab 2: 清理 ──

    def _build_tab2(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='② 🧼 清理')

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

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill='x', pady=(6, 0))
        self.btn_clean = ttk.Button(btn_row, text='🧼 开始清理', command=self._do_clean)
        self.btn_clean.pack(side='left')
        self.btn_export2 = ttk.Button(btn_row, text='💾 导出已清理 SQLite', command=self._export_cleaned, state='disabled')
        self.btn_export2.pack(side='left', padx=(8, 0))

        self.info2 = tk.Text(tab, height=5, state='disabled', wrap='word', bg='#fafafa', font=('Consolas', 10))
        self.info2.pack(fill='x', pady=(6, 0))

    def _do_clean(self):
        if not self.sqlite_path:
            messagebox.showwarning('提示', '请先在 "① 解压" 中解压 apkg')
            return

        # 构建配置
        config = DEFAULT_CONFIG.copy()
        for k, v in self.checks.items():
            config[k] = v.get()
        config['custom_regex'] = []
        if self.custom_var.get() and self.re_find.get():
            config['custom_regex'].append((self.re_find.get(), self.re_repl.get()))

        self.btn_clean.configure(state='disabled')
        self._log(self.info2, '⏳ 正在清理...')

        def task():
            try:
                # 输出到临时文件
                out_dir = os.path.dirname(self.sqlite_path)
                self.cleaned_path = os.path.join(out_dir, 'collection.cleaned.sqlite')

                cleaner = SqliteCleaner()
                result = cleaner.clean(self.sqlite_path, self.cleaned_path, config,
                                      progress_callback=lambda i, t: None)

                self._log(self.info2, f'✅ 清理完成: {result["total"]} 条笔记')
                self.btn_export2.configure(state='normal')
                self._log(self.info2, '💡 可进入 "③ 打包" 生成 apkg，或点击导出按钮保存中间文件')
            except Exception as e:
                self._log(self.info2, f'❌ 失败: {e}')
            finally:
                self.btn_clean.configure(state='normal')

        threading.Thread(target=task, daemon=True).start()

    def _export_cleaned(self):
        if not self.cleaned_path:
            return
        path = filedialog.asksaveasfilename(
            title='导出已清理的 SQLite',
            initialdir='output',
            defaultextension='.sqlite',
            filetypes=[('SQLite 数据库', '*.sqlite;*.anki2'), ('所有文件', '*.*')])
        if path:
            shutil.copy2(self.cleaned_path, path)
            self._log(self.info2, f'💾 已导出: {os.path.basename(path)} ({os.path.getsize(path)/1024:.0f} KB)')

    # ── Tab 3: 打包 ──

    def _build_tab3(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='③ 📦 打包')

        ttk.Label(tab, text='📥 输出文件：').pack(anchor='w')
        row = ttk.Frame(tab)
        row.pack(fill='x', pady=(4, 8))
        self.out_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.out_var).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='📁 选择位置', command=self._browse_output, width=8).pack(side='right', padx=(4, 0))

        self.btn_pack = ttk.Button(tab, text='📦 打包为 .apkg', command=self._do_pack)
        self.btn_pack.pack(anchor='w')

        self.info3 = tk.Text(tab, height=6, state='disabled', wrap='word', bg='#fafafa', font=('Consolas', 10))
        self.info3.pack(fill='both', expand=True, pady=(8, 0))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(title='保存为 apkg', defaultextension='.apkg', filetypes=[('Anki 牌组', '*.apkg')])
        if path:
            self.out_var.set(path)

    def _do_pack(self):
        if not self.cleaned_path:
            messagebox.showwarning('提示', '请先在 "② 清理" 中执行清理')
            return
        out = self.out_var.get()
        if not out:
            messagebox.showwarning('提示', '请选择输出位置')
            return

        self.btn_pack.configure(state='disabled')
        self._log(self.info3, '⏳ 正在打包...')

        def task():
            try:
                packer = ApkgPacker()
                use_zstd = self.original_db_name and self.original_db_name.endswith('anki21b')
                result = packer.pack(
                    self.cleaned_path, out,
                    media_dir=self.media_dir,
                    use_zstd=use_zstd,
                    db_name=self.original_db_name)
                self._log(self.info3, f'✅ 打包完成: {result["output"]}')
                self._log(self.info3, f'   数据库: {result["db_name"]} ({"zstd" if result["zstd"] else "直接存储"})')
                self._log(self.info3, f'   媒体文件: {result["media_count"]} 个')
            except Exception as e:
                self._log(self.info3, f'❌ 失败: {e}')
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
