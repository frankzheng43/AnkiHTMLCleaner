"""
清理 Anki apkg 中的冗余 HTML 包装标签
用法: python clean_anki_html.py
"""

import re
import subprocess
import ctypes
import zipfile
import os
import shutil
import json
import struct
import html
from ctypes import c_char_p, c_int, c_void_p, c_size_t, c_uint64, POINTER, byref, create_string_buffer

# ============================================================
# 配置
# ============================================================
APKG_PATH = r'税务师.apkg'
WORK_DIR = r'C:\Users\Frank\anki_work'
DB_NAME = 'collection.anki21b'
DB_PATH = os.path.join(WORK_DIR, DB_NAME)
DECOMPRESSED_DB = os.path.join(WORK_DIR, 'decompressed_anki21b.sqlite')
OUTPUT_APKG = r'税务师_cleaned_puretext.apkg'
ZSTD_DLL = r'C:\Users\Frank\AppData\Local\Logseq\app-0.10.9\resources\app\node_modules\dugite\git\mingw64\bin\libzstd.dll'
SQLITE3_EXE = r'F:\Software\Anaconda\Library\bin\sqlite3.exe'

# ============================================================
# 工具函数
# ============================================================

def zstd_decompress(src_path, dst_path):
    """用 zstd DLL 解压文件"""
    zstd = ctypes.CDLL(ZSTD_DLL)
    with open(src_path, 'rb') as f:
        compressed = f.read()
    
    dst_size = 100 * 1024 * 1024  # 100 MB max
    dst = ctypes.create_string_buffer(dst_size)
    zstd.ZSTD_decompress.restype = ctypes.c_size_t
    result = zstd.ZSTD_decompress(dst, dst_size, compressed, len(compressed))
    
    if zstd.ZSTD_isError(result):
        err_name = zstd.ZSTD_getErrorName(result)
        raise RuntimeError(f'zstd decompress error: {err_name}')
    
    with open(dst_path, 'wb') as f:
        f.write(dst.raw[:result])
    print(f'  Decompressed {result} bytes -> {dst_path}')
    return result

def zstd_compress(src_path, dst_path):
    """用 zstd DLL 压缩文件 (默认级别 3)"""
    zstd = ctypes.CDLL(ZSTD_DLL)
    with open(src_path, 'rb') as f:
        uncompressed = f.read()
    
    # 准备输出缓冲区 (zstd 压缩后最大可能略大于源)
    dst_size = len(uncompressed) + 1024 * 1024
    dst = ctypes.create_string_buffer(dst_size)
    
    zstd.ZSTD_compress.restype = ctypes.c_size_t
    zstd.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, 
                                   ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    
    compression_level = 3
    result = zstd.ZSTD_compress(dst, dst_size, uncompressed, len(uncompressed), compression_level)
    
    if zstd.ZSTD_isError(result):
        err_name = zstd.ZSTD_getErrorName(result)
        raise RuntimeError(f'zstd compress error: {err_name}')
    
    with open(dst_path, 'wb') as f:
        f.write(dst.raw[:result])
    print(f'  Compressed {len(uncompressed)} bytes -> {result} bytes -> {dst_path}')
    return result

def clean_html_text(text):
    """
    最简清理：只去冗余属性，不动结构。
    
    规则：
    - 保留 <div>、<br>、<p>、<table> 等所有标签
    - 只清除 style、class 等不影响含义的属性
    - 移除无显示效果的 <span>、<tbody>
    - 清理 &nbsp;、_x000D_、HTML 注释
    - 表格加单线黑框
    """
    if not text:
        return text
    
    # 清除所有标签上的 style 属性
    text = re.sub(r'\s+style\s*=\s*"[^"]*"', '', text)
    text = re.sub(r"\s+style\s*=\s*'[^']*'", '', text)
    
    # 清除 class 属性（如 class="question-analysis-wrap"）
    text = re.sub(r'\s+class\s*=\s*"[^"]*"', '', text)
    text = re.sub(r"\s+class\s*=\s*'[^']*'", '', text)
    
    # 移除无显示效果的标签
    text = re.sub(r'</?span\b[^>]*>', '', text)     # <span> 纯容器
    text = re.sub(r'</?tbody\b[^>]*>', '', text)    # <tbody> 浏览器自动插入
    
    # <p> → <br> 转换（保留换行效果）
    text = re.sub(r'<p\b[^>]*>', '', text)           # <p ...> 去掉开标签
    text = re.sub(r'</p\s*>', '<br>', text)           # </p> → <br>
    
    # 所有 HTML 实体转真实字符（&times; → ×, &radic; → √, &ldquo; → " 等）
    text = html.unescape(text)
    text = text.replace('_x000D_', '')
    text = text.replace('\r', '')
    text = re.sub(r'<!--.*?-->', '', text)           # HTML 注释
    
    # 多个连续 <br> 缩成一个（不空行）
    text = re.sub(r'(<br\s*/?\s*>\s*){2,}', r'\1', text)
    # 去掉段首段尾及容器标签前后的无意义 <br>
    text = re.sub(r'^\s*<br\s*/?\s*>', '', text)
    text = re.sub(r'<br\s*/?\s*>\s*$', '', text)
    text = re.sub(r'(<div\b[^>]*>)\s*<br\s*/?\s*>', r'\1', text)
    text = re.sub(r'<br\s*/?\s*>\s*</div\s*>', '</div>', text)
    
    # 删除中文字符之间的多余空格（不影响英文单词间空格）
    text = re.sub(r'([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])\s+([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])', r'\1\2', text)
    
    # 中文与英文之间加空格  如 "增值税general纳税人" → "增值税 general 纳税人"
    text = re.sub(r'([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])', r'\1 \2', text)
    # 中文与数字之间加空格  如 "2025年3月" → "2025 年 3 月"
    text = re.sub(r'([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])', r'\1 \2', text)
    
    # 多个空格缩成一个
    text = re.sub(r'  +', ' ', text)
    
    # 表格添加单线黑框
    if re.search(r'<table\b', text, re.IGNORECASE) and not re.search(r'<table\b[^>]*\bborder\s*=', text, re.IGNORECASE):
        text = re.sub(r'<table\b', '<table border="1" style="border-collapse: collapse"', text)
    
    return text.strip()


def clean_flds(flds, mid):
    """
    处理 flds 字段（以 \x1f 分隔的各字段内容），
    仅对特定字段做 HTML 清理。
    
    根据笔记类型确定要清理的字段索引。
    """
    fields = flds.split('\x1f')
    
    # 根据笔记类型 (mid) 确定要清理哪些字段
    # 注意：mid 是整数
    if mid == 1750954064656:  # MN3-通用选择题-240129 @Dayday不觉晓
        # fields: id(0), question(1), options(2), answer(3), notes(4), addnote(5), num(6)
        # 需要清理的字段: question(1), options(2), notes(4), addnote(5)
        clean_indices = [1, 2, 4, 5]
    elif mid == 1437128454804:  # Analysis-Basic
        # fields: 问题(0), 答案(1), 笔记(2), 相关知识(3)
        # 需要清理的字段: 问题(0), 答案(1)
        clean_indices = [0, 1]
    else:
        clean_indices = []
    
    for idx in clean_indices:
        if idx < len(fields):
            fields[idx] = clean_html_text(fields[idx])
    
    return '\x1f'.join(fields)


# ============================================================
# ctypes-based SQLite 封装
# ============================================================

SQLITE3_DLL = r'F:\Software\Anaconda\Library\bin\sqlite3.dll'

class SQLiteDB:
    """用 ctypes 直接操作 SQLite"""
    
    def __init__(self, db_path):
        self.dll = ctypes.CDLL(SQLITE3_DLL)
        self.db = c_void_p()
        # sqlite3_open
        self.dll.sqlite3_open.argtypes = [c_char_p, POINTER(c_void_p)]
        self.dll.sqlite3_open.restype = c_int
        
        rc = self.dll.sqlite3_open(db_path.encode('utf-8'), byref(self.db))
        if rc != 0:
            err = self.dll.sqlite3_errmsg(self.db)
            raise RuntimeError(f'Cannot open DB: {err}')
    
    def close(self):
        if self.db:
            self.dll.sqlite3_close(self.db)
            self.db = None
    
    def execute(self, sql):
        """执行 SQL 并返回所有行 (列表 of 元组)"""
        stmt = c_void_p()
        tail = c_char_p()
        
        self.dll.sqlite3_prepare_v2.argtypes = [c_void_p, c_char_p, c_int, POINTER(c_void_p), POINTER(c_char_p)]
        self.dll.sqlite3_prepare_v2.restype = c_int
        
        self.dll.sqlite3_step.argtypes = [c_void_p]
        self.dll.sqlite3_step.restype = c_int
        
        self.dll.sqlite3_column_count.argtypes = [c_void_p]
        self.dll.sqlite3_column_count.restype = c_int
        
        self.dll.sqlite3_column_type.argtypes = [c_void_p, c_int]
        self.dll.sqlite3_column_type.restype = c_int
        
        self.dll.sqlite3_column_text.argtypes = [c_void_p, c_int]
        self.dll.sqlite3_column_text.restype = c_char_p
        
        self.dll.sqlite3_column_int64.argtypes = [c_void_p, c_int]
        self.dll.sqlite3_column_int64.restype = c_uint64
        
        self.dll.sqlite3_finalize.argtypes = [c_void_p]
        self.dll.sqlite3_finalize.restype = c_int
        
        SQLITE_OK = 0
        SQLITE_ROW = 100
        SQLITE_DONE = 101
        SQLITE_INTEGER = 1
        SQLITE_FLOAT = 2
        SQLITE_TEXT = 3
        SQLITE_BLOB = 4
        SQLITE_NULL = 5
        
        rows = []
        
        rc = self.dll.sqlite3_prepare_v2(self.db, sql.encode('utf-8'), -1, byref(stmt), byref(tail))
        if rc != SQLITE_OK:
            err = self.dll.sqlite3_errmsg(self.db)
            raise RuntimeError(f'SQL prepare error: {err} (SQL: {sql[:100]}...)')
        
        while True:
            rc = self.dll.sqlite3_step(stmt)
            if rc == SQLITE_DONE:
                break
            if rc == SQLITE_ROW:
                col_count = self.dll.sqlite3_column_count(stmt)
                row = []
                for i in range(col_count):
                    col_type = self.dll.sqlite3_column_type(stmt, i)
                    if col_type == SQLITE_NULL:
                        row.append(None)
                    elif col_type == SQLITE_INTEGER:
                        row.append(self.dll.sqlite3_column_int64(stmt, i))
                    elif col_type == SQLITE_TEXT:
                        val = self.dll.sqlite3_column_text(stmt, i)
                        row.append(val.decode('utf-8') if val else '')
                    else:
                        val = self.dll.sqlite3_column_text(stmt, i)
                        row.append(val.decode('utf-8') if val else '')
                rows.append(tuple(row))
            else:
                break
        
        self.dll.sqlite3_finalize(stmt)
        return rows
    
    def execute_many(self, statements):
        """执行多条 SQL (用 ; 连接)"""
        full_sql = '; '.join(statements)
        return self.execute(full_sql)


def run_sql_file(db_path, sql_file):
    """通过 sqlite3.exe 执行 SQL 文件"""
    result = subprocess.run(
        [SQLITE3_EXE, db_path],
        stdin=open(sql_file, 'r', encoding='utf-8'),
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        print(f'  SQL Error: {result.stderr[:500]}')
    return result.stdout


# ============================================================
# 主流程
# ============================================================

def main():
    print('=== 步骤1: 解压 apkg (ZIP) ===')
    os.makedirs(WORK_DIR, exist_ok=True)
    with zipfile.ZipFile(APKG_PATH, 'r') as zf:
        for info in zf.infolist():
            outpath = os.path.join(WORK_DIR, info.filename)
            os.makedirs(os.path.dirname(outpath), exist_ok=True)
            with open(outpath, 'wb') as f:
                f.write(zf.read(info.filename))
        print(f'  Extracted {len(zf.infolist())} files from apkg')
    
    print('\n=== 步骤2: zstd 解压 collection.anki21b ===')
    decompressed_path = os.path.join(WORK_DIR, 'decompressed_anki21b.sqlite')
    zstd_decompress(DB_PATH, decompressed_path)
    
    print('\n=== 步骤3: 连接数据库并处理 notes ===')
    db = SQLiteDB(decompressed_path)
    
    rows = db.execute('SELECT id, mid, flds FROM notes ORDER BY id')
    print(f'  Total notes to process: {len(rows)}')
    
    updated_count = 0
    total_changes = 0
    
    for row in rows:
        note_id, mid, flds = row
        original_len = len(flds)
        cleaned = clean_flds(flds, mid)
        
        if cleaned != flds:
            # 转义单引号
            cleaned_escaped = cleaned.replace("'", "''")
            sql = f"UPDATE notes SET flds = '{cleaned_escaped}' WHERE id = {note_id}"
            db.execute(sql)
            updated_count += 1
            total_changes += (original_len - len(cleaned))
            
            if updated_count % 500 == 0:
                print(f'  Processed {updated_count}/{len(rows)}...')
    
    db.close()
    
    print(f'  Notes with cleaned HTML: {updated_count}')
    print(f'  Total bytes removed: {total_changes}')
    
    if updated_count == 0:
        print('  No changes needed!')
        return
    
    # 验证
    result = subprocess.run(
        [SQLITE3_EXE, '-noheader', decompressed_path,
         'SELECT COUNT(*) FROM notes'],
        capture_output=True, text=True, timeout=10
    )
    print(f'  Database verification: {result.stdout.strip()} notes in DB')
    
    print('\n=== 步骤5: zstd 重新压缩 ===')
    new_db_zstd = os.path.join(WORK_DIR, 'new_' + DB_NAME)
    # 清理旧的中间文件
    if os.path.exists(new_db_zstd):
        os.remove(new_db_zstd)
    zstd_compress(decompressed_path, new_db_zstd)
    
    print('\n=== 步骤6: 重新打包 apkg ===')
    if os.path.exists(OUTPUT_APKG):
        os.remove(OUTPUT_APKG)
    
    with zipfile.ZipFile(OUTPUT_APKG, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 添加 meta
        meta_path = os.path.join(WORK_DIR, 'meta')
        if os.path.exists(meta_path):
            zf.write(meta_path, 'meta')
        
        # 添加压缩后的 collection.anki21b
        zf.write(new_db_zstd, DB_NAME)
        
        # 添加 collection.anki2 (兼容旧版)
        anki2_path = os.path.join(WORK_DIR, 'collection.anki2')
        if os.path.exists(anki2_path):
            zf.write(anki2_path, 'collection.anki2')
        
        # 添加 media 文件（protobuf）
        media_path = os.path.join(WORK_DIR, 'media')
        if os.path.exists(media_path):
            zf.write(media_path, 'media')
        
        # 添加媒体文件 (0-7)
        for i in range(8):
            media_file = os.path.join(WORK_DIR, str(i))
            if os.path.exists(media_file):
                zf.write(media_file, str(i))
    
    print(f'  Created: {OUTPUT_APKG}')
    
    # 检查文件大小
    size_mb = os.path.getsize(OUTPUT_APKG) / (1024 * 1024)
    original_mb = os.path.getsize(APKG_PATH) / (1024 * 1024)
    print(f'  Original: {original_mb:.1f} MB')
    print(f'  Cleaned:  {size_mb:.1f} MB')
    
    print('\n✅ 完成!')
    print(f'   清理了 {updated_count} 条笔记中的冗余 HTML 标签')
    print(f'   输出文件: {OUTPUT_APKG}')


if __name__ == '__main__':
    main()
