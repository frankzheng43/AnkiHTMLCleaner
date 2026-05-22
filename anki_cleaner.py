"""
Anki Apkg 清理工具 — 图形界面版
纯 tkinter + sqlite3 + zipfile，零额外 Python 依赖
zstd 解压依赖 libzstd.dll（300 KB，同目录或系统 PATH）
"""

import os
import sys

# 修复 sqlite3 DLL 搜索路径（打包 exe 后不需要，仅源码运行时）
if hasattr(os, 'add_dll_directory'):
    for _p in [
        os.path.join(os.path.dirname(sys.executable), 'Library', 'bin'),
        os.path.join(os.path.dirname(sys.executable), 'DLLs'),
        r'F:\Software\Anaconda\Library\bin',
    ]:
        if os.path.isdir(_p):
            try:
                os.add_dll_directory(_p)
            except:
                pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import zipfile
import re
import html
import shutil
import struct
import ctypes
import threading
import tempfile
from ctypes import c_char_p, c_int, c_void_p, c_size_t, c_uint64, POINTER, byref, create_string_buffer

# sqlite3 延迟导入（因为 DLL 路径修复后才能加载）
_sqlite3 = None
def _get_sqlite3():
    global _sqlite3
    if _sqlite3 is None:
        import sqlite3
        _sqlite3 = sqlite3
    return _sqlite3

# ── zstd ──────────────────────────────────────────────

def load_zstd():
    """尝试加载 zstd（优先用 zstandard 包，回退到 ctypes+DLL）"""
    try:
        import zstandard as _zs
        # 验证可用
        _zs.decompress(b'')
        return _zs, 'python'
    except:
        pass
    
    # 回退：ctypes + libzstd.dll
    dll_name = 'libzstd.dll'
    base = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    for p in [
        os.path.join(base, dll_name),
        os.path.join(os.getcwd(), dll_name),
    ]:
        if os.path.exists(p):
            try:
                dll = ctypes.CDLL(p)
                return dll, p
            except:
                continue
    return None, None


def zstd_decompress(zstd_obj, data):
    """zstd 解压"""
    import zstandard as _zs
    if hasattr(zstd_obj, 'decompress'):
        # Python 包
        return zstd_obj.decompress(data)
    else:
        # ctypes DLL
        _dll = zstd_obj
        dst_size = max(len(data) * 50, 100 * 1024 * 1024)
        dst = create_string_buffer(dst_size)
        _dll.ZSTD_decompress.restype = c_size_t
        result = _dll.ZSTD_decompress(dst, dst_size, data, len(data))
        if _dll.ZSTD_isError(result):
            err = _dll.ZSTD_getErrorName(result)
            raise RuntimeError(f'zstd 解压失败: {err.decode()}')
        return dst.raw[:result]


def zstd_compress(zstd_obj, data, level=3):
    """zstd 压缩"""
    import zstandard as _zs
    if hasattr(zstd_obj, 'compress'):
        # Python 包
        return zstd_obj.compress(data, level)
    else:
        # ctypes DLL
        _dll = zstd_obj
        dst_size = len(data) + 1024 * 1024
        dst = create_string_buffer(dst_size)
        _dll.ZSTD_compress.restype = c_size_t
        result = _dll.ZSTD_compress(dst, dst_size, data, len(data), level)
        if _dll.ZSTD_isError(result):
            err = _dll.ZSTD_getErrorName(result)
            raise RuntimeError(f'zstd 压缩失败: {err.decode()}')
        return dst.raw[:result]


# ── 清理引擎 ──────────────────────────────────────────────

class CleanEngine:
    def __init__(self, config):
        """
        config: dict
            rm_style        - 删除 style 属性
            rm_class        - 删除 class 属性
            rm_span         - 删除 <span>
            rm_tbody        - 删除 <tbody>
            p_to_br         - <p> 转 <br>
            unescape        - HTML 实体转字符
            rm_crap         - 清除 _x000D_ 和注释
            collapse_br     - 多个 <br> 缩成一个
            trim_br         - 去掉首尾无意义 <br>
            table_border    - 表格加黑框
            rm_cjk_space    - 删中文间多余空格
            add_cjk_space   - 中文与英文/数字间加空格
            custom_regex    - [(查找, 替换), ...]
        """
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

        # 自定义正则
        for find, replace in self.config.get('custom_regex', []):
            try:
                text = re.sub(find, replace, text)
            except:
                pass

        # 收尾：多个空格缩成一个
        text = re.sub(r'  +', ' ', text)
        return text.strip()


# ── Apkg 处理 ──────────────────────────────────────────────

class ApkgProcessor:
    def __init__(self, zstd_dll):
        self.zstd = zstd_dll
        self.temp_dir = None
        self.db_path = None
        self._field_cache = {}

    def open(self, apkg_path, progress_callback=None):
        """解压 apkg + zstd 解压数据库，返回 True/False"""
        self.temp_dir = tempfile.mkdtemp(prefix='anki_clean_')
        
        try:
            # 1. 解压 zip
            with zipfile.ZipFile(apkg_path, 'r') as zf:
                zf.extractall(self.temp_dir)
            if progress_callback:
                progress_callback('✓ 已解压 apkg (ZIP)')

            # 2. 找到数据库文件
            db_files = [f for f in os.listdir(self.temp_dir) if f.startswith('collection.anki2')]
            if not db_files:
                raise RuntimeError('未找到 collection.anki2* 数据库文件')
            
            db_file = db_files[0]  # 优先用 anki21b
            
            if db_file.endswith('anki21b') and self.zstd:
                # zstd 解压
                with open(os.path.join(self.temp_dir, db_file), 'rb') as f:
                    compressed = f.read()
                
                # 检查魔数
                if compressed[:4] == b'\x28\xb5\x2f\xfd':
                    decompressed = zstd_decompress(self.zstd, compressed)
                    self.db_path = os.path.join(self.temp_dir, 'decompressed.sqlite')
                    with open(self.db_path, 'wb') as f:
                        f.write(decompressed)
                    if progress_callback:
                        progress_callback(f'✓ zstd 解压完成 ({len(decompressed)/1024:.0f} KB)')
                else:
                    # 不是 zstd 格式，直接当 SQLite 用
                    self.db_path = os.path.join(self.temp_dir, db_file)
                    if progress_callback:
                        progress_callback('✓ 数据库无需 zstd 解压')
            else:
                # 普通 SQLite
                self.db_path = os.path.join(self.temp_dir, db_file)
                if progress_callback:
                    progress_callback('✓ 数据库文件已就绪')

            # 3. 读取笔记类型信息
            self._load_notetypes()
            return True

        except Exception as e:
            self.cleanup()
            raise

    def _load_notetypes(self):
        conn = _get_sqlite3().connect(self.db_path)
        cur = conn.cursor()
        
        # 获取笔记类型和字段名
        try:
            cur.execute("SELECT id, name FROM notetypes")
            ntypes = cur.fetchall()
            for nid, name in ntypes:
                cur.execute("SELECT name FROM fields WHERE ntid = ? ORDER BY ord", (nid,))
                fields = [r[0] for r in cur.fetchall()]
                self._field_cache[nid] = {'name': name, 'fields': fields}
        except:
            # 兼容旧版 schema
            pass
        
        conn.close()

    def get_notetypes(self):
        """返回 [(id, name, [field_names]), ...]"""
        result = []
        for nid, info in self._field_cache.items():
            result.append((nid, info['name'], info['fields']))
        return result

    def get_note_count(self):
        conn = _get_sqlite3().connect(self.db_path)
        cnt = conn.execute('SELECT COUNT(*) FROM notes').fetchone()[0]
        conn.close()
        return cnt

    def process(self, engine, target_fields=None, progress_callback=None):
        conn = _get_sqlite3().connect(self.db_path)
        cur = conn.cursor()
        
        rows = cur.execute("SELECT id, mid, flds FROM notes").fetchall()
        total = len(rows)
        
        for idx, (note_id, mid, flds) in enumerate(rows):
            if progress_callback and idx % 100 == 0:
                progress_callback(f'⏳ 清理中... {idx}/{total}')
            
            fields = flds.split('\x1f')
            changed = False
            
            for fi in range(len(fields)):
                if target_fields and (mid, fi) not in target_fields:
                    continue
                
                cleaned = engine.clean(fields[fi])
                if cleaned != fields[fi]:
                    fields[fi] = cleaned
                    changed = True
            
            if changed:
                new_flds = '\x1f'.join(fields)
                cur.execute("UPDATE notes SET flds = ? WHERE id = ?", (new_flds, note_id))
        
        conn.commit()
        conn.close()
        
        if progress_callback:
            progress_callback(f'✓ 清理完成，共处理 {total} 条笔记')

    def repack(self, output_path, progress_callback=None):
        """压缩数据库 + 重新打包 apkg"""
        # 1. 重新压缩数据库 (zstd)
        db_data = open(self.db_path, 'rb').read()
        
        if self.zstd:
            compressed = zstd_compress(self.zstd, db_data)
            db_out_name = 'collection.anki21b'
        else:
            compressed = db_data
            db_out_name = 'collection.anki2'
        
        # 2. 打包 zip
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(self.temp_dir):
                fpath = os.path.join(self.temp_dir, fname)
                if fname == 'decompressed.sqlite' or fname.startswith('collection.anki'):
                    continue
                zf.write(fpath, fname)
            
            # 写入处理后的数据库
            tmp_db = os.path.join(self.temp_dir, db_out_name)
            with open(tmp_db, 'wb') as f:
                f.write(compressed)
            zf.write(tmp_db, db_out_name)
            os.remove(tmp_db)
        
        if progress_callback:
            size = os.path.getsize(output_path) / (1024 * 1024)
            progress_callback(f'✓ 已输出: {os.path.basename(output_path)} ({size:.1f} MB)')

    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None


# ── GUI ─────────────────────────────────────────────────────

class AnkiCleanerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Anki Apkg 清理工具')
        self.root.geometry('720x760')
        self.root.minsize(640, 680)
        
        # 加载 zstd
        self.zstd_dll, self.zstd_path = load_zstd()
        
        # 处理器
        self.processor = None
        
        self._build_ui()
        
        # 默认勾选
        self._set_defaults()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill='both', expand=True)

        # ── 标题 ──
        ttk.Label(main, text='Anki Apkg 清理工具', font=('', 16, 'bold')).pack(anchor='w')
        ttk.Label(main, text='解包 → 清理 → 打包，三步完成', foreground='gray').pack(anchor='w', pady=(0, 12))

        # ── 步骤 1: 文件选择 ──
        frame1 = ttk.LabelFrame(main, text='步骤 1：选择 apkg 文件', padding=8)
        frame1.pack(fill='x', pady=(0, 8))
        
        row1 = ttk.Frame(frame1)
        row1.pack(fill='x')
        self.file_path = tk.StringVar()
        ttk.Entry(row1, textvariable=self.file_path).pack(side='left', fill='x', expand=True)
        ttk.Button(row1, text='浏览', command=self._browse_file, width=8).pack(side='right', padx=(4, 0))
        
        row1b = ttk.Frame(frame1)
        row1b.pack(fill='x', pady=(4, 0))
        ttk.Button(row1b, text='① 提取 apkg', command=self._do_extract).pack(side='left')
        self.extract_status = ttk.Label(row1b, text='', foreground='gray')
        self.extract_status.pack(side='left', padx=(8, 0))

        # zstd 状态
        if self.zstd_dll:
            if self.zstd_path == 'python':
                zstd_text = 'zstandard: ✅ Python 包'
            else:
                zstd_text = f'libzstd.dll: ✅ {os.path.basename(self.zstd_path)}'
        else:
            zstd_text = '⚠️ zstd 不可用（仅支持旧版 apkg）'
        ttk.Label(frame1, text=zstd_text, foreground='gray', font=('', 9)).pack(anchor='w', pady=(4, 0))

        # ── 步骤 2: 清理选项 ──
        frame2 = ttk.LabelFrame(main, text='步骤 2：选择清理项目', padding=8)
        frame2.pack(fill='both', expand=True, pady=(0, 8))

        canvas = tk.Canvas(frame2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame2, orient='vertical', command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        canvas.bind('<Configure>', lambda e: canvas.itemconfig(1, width=e.width))
        scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=scroll_frame, anchor='nw', width=canvas.winfo_reqwidth())
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)

        self.checks = {}

        # 清理选项定义
        options = [
            ('rm_style',      '删除 style 属性',         '清除所有标签上的 style="..."'),
            ('rm_class',      '删除 class 属性',         '清除所有标签上的 class="..."'),
            ('rm_span',       '删除 <span> 标签',        '无显示效果，仅保留内容'),
            ('rm_tbody',      '删除 <tbody> 标签',       '浏览器会自动插入'),
            ('p_to_br',       '<p> 转 <br>',             '<p>段落</p> → 段落<br>'),
            ('unescape',      'HTML 实体转字符',         '&times; → ×, &divide; → ÷, &nbsp; → 空格'),
            ('rm_crap',       '清除 _x000D_ 和注释',     'Windows 换行残留和 HTML 注释'),
            ('collapse_br',   '多个 <br> 缩成一个',      '<br><br> → <br>'),
            ('trim_br',       '去掉首尾无意义 <br>',      '段首段尾及 <div> 前后的 <br>'),
            ('table_border',  '表格加默认黑边框',        '<table> → <table border="1">'),
            ('rm_cjk_space',  '删中文间多余空格',        '增值税 一般 → 增值税一般'),
            ('add_cjk_space', '中文与英/数间加空格',      '2025年 → 2025 年, A股 → A 股'),
        ]

        for key, label, desc in options:
            var = tk.BooleanVar(value=True)
            f = ttk.Frame(scroll_frame)
            f.pack(fill='x', pady=1)
            cb = ttk.Checkbutton(f, text=label, variable=var)
            cb.pack(side='left')
            ttk.Label(f, text=desc, foreground='gray', font=('', 9)).pack(side='left', padx=(8, 0))
            self.checks[key] = var

        # ── 自定义正则 ──
        sep = ttk.Separator(scroll_frame, orient='horizontal')
        sep.pack(fill='x', pady=6)

        ttk.Label(scroll_frame, text='☐ 自定义查找替换（可选）', font=('', 9, 'bold')).pack(anchor='w')
        
        self.custom_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(scroll_frame, text='启用自定义正则', variable=self.custom_var).pack(anchor='w')

        reg_frame = ttk.Frame(scroll_frame)
        reg_frame.pack(fill='x', pady=(4, 0))
        ttk.Label(reg_frame, text='查找:').grid(row=0, column=0, sticky='w')
        self.regex_find = tk.StringVar()
        ttk.Entry(reg_frame, textvariable=self.regex_find).grid(row=0, column=1, sticky='ew', padx=(4, 0))
        
        ttk.Label(reg_frame, text='替换:').grid(row=1, column=0, sticky='w', pady=(4, 0))
        self.regex_replace = tk.StringVar()
        ttk.Entry(reg_frame, textvariable=self.regex_replace).grid(row=1, column=1, sticky='ew', padx=(4, 0), pady=(4, 0))
        reg_frame.columnconfigure(1, weight=1)

        # ── 步骤 3: 输出 ──
        frame3 = ttk.LabelFrame(main, text='步骤 3：输出', padding=8)
        frame3.pack(fill='x', pady=(0, 8))

        row3 = ttk.Frame(frame3)
        row3.pack(fill='x')
        self.output_path = tk.StringVar()
        ttk.Entry(row3, textvariable=self.output_path).pack(side='left', fill='x', expand=True)
        ttk.Button(row3, text='浏览', command=self._browse_output, width=8).pack(side='right', padx=(4, 0))

        # ── 开始按钮 ──
        self.run_btn = ttk.Button(main, text='▶ 开始处理', command=self._run, style='Accent.TButton')
        self.run_btn.pack(pady=(0, 8))

        # ── 日志 ──
        self.log_text = tk.Text(main, height=10, state='disabled', wrap='word')
        self.log_text.pack(fill='both', expand=True)
        
        scroll_log = ttk.Scrollbar(main, orient='vertical', command=self.log_text.yview)
        scroll_log.pack(side='right', fill='y')
        self.log_text.configure(yscrollcommand=scroll_log.set)

    def _set_defaults(self):
        for key in ['rm_style', 'rm_class', 'rm_span', 'rm_tbody', 'p_to_br',
                     'unescape', 'rm_crap', 'collapse_br', 'trim_br',
                     'table_border', 'rm_cjk_space', 'add_cjk_space']:
            if key in self.checks:
                self.checks[key].set(True)

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title='选择 apkg 文件',
            filetypes=[('Anki 牌组', '*.apkg'), ('所有文件', '*.*')]
        )
        if path:
            self.file_path.set(path)
            # 自动设置输出路径
            base = os.path.splitext(path)[0]
            self.output_path.set(f'{base}_cleaned.apkg')

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title='保存为',
            defaultextension='.apkg',
            filetypes=[('Anki 牌组', '*.apkg')]
        )
        if path:
            self.output_path.set(path)

    def _log(self, msg):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', msg + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')
        self.root.update()

    def _do_extract(self):
        """仅提取 apkg，展示信息"""
        path = self.file_path.get()
        if not path:
            messagebox.showwarning('提示', '请先选择 apkg 文件')
            return
        
        self.extract_status.configure(text='⏳ 正在提取...')
        self.root.update()
        
        try:
            # 创建处理器并提取
            self.processor = ApkgProcessor(self.zstd_dll)
            self.processor.open(path, self._log)
            
            ntypes = self.processor.get_notetypes()
            note_count = self.processor.get_note_count()
            
            info = f'✅ 已提取: {note_count} 条笔记'
            if ntypes:
                info += f', {len(ntypes)} 种笔记类型'
            self.extract_status.configure(text=info, foreground='green')
            
            self._log(f'✓ 数据库就绪')
            for nid, name, fields in ntypes:
                self._log(f'  📝 {name}: {len(fields)} 个字段 {fields}')
            
        except Exception as e:
            self.extract_status.configure(text=f'❌ 提取失败', foreground='red')
            self._log(f'❌ 错误: {e}')

    def _run(self):
        if not self.processor:
            messagebox.showwarning('提示', '请先点击 "① 提取 apkg"')
            return
        
        if not self.output_path.get():
            messagebox.showwarning('提示', '请选择输出路径')
            return

        # 构建配置
        config = {}
        for key, var in self.checks.items():
            config[key] = var.get()
        
        config['custom_regex'] = []
        if self.custom_var.get() and self.regex_find.get():
            config['custom_regex'].append((self.regex_find.get(), self.regex_replace.get()))
        
        engine = CleanEngine(config)
        
        # 禁用按钮
        self.run_btn.configure(state='disabled')
        
        # 在后台线程运行
        def _task():
            try:
                self._log('\n🚀 开始清理...')
                
                # 构建目标字段 (清理所有可清理字段)
                self.processor.process(engine, target_fields=None, progress_callback=self._log)
                
                # 重新打包
                self._log('⏳ 正在打包...')
                output = self.output_path.get()
                if not output.endswith('.apkg'):
                    output += '.apkg'
                self.processor.repack(output, self._log)
                
                self._log('✅ 全部完成！')
                
            except Exception as e:
                self._log(f'❌ 出错: {e}')
            finally:
                self.processor.cleanup()
                self.processor = None
                self.run_btn.configure(state='normal')
                self.extract_status.configure(text='')
        
        threading.Thread(target=_task, daemon=True).start()


# ── 启动 ──────────────────────────────────────────────────

def main():
    # Windows 主题
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    app = AnkiCleanerApp()
    app.root.mainloop()


if __name__ == '__main__':
    main()
