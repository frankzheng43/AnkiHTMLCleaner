"""
解压 .apkg → .sqlite

用法：
    python core/extract.py input.apkg output.sqlite
    python core/extract.py input.apkg output.sqlite --mediadir media
"""

import os
import sys
import zipfile
import tempfile
import shutil
import json

# zstd 支持
try:
    import zstandard as _zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


class ApkgExtractor:
    def extract(self, apkg_path, output_path, media_dir=None):
        """
        解压 apkg，输出 SQLite 数据库和媒体文件目录。
        
        返回 dict:
            note_count: 笔记数
            media_files: 媒体文件列表
            media_dir: 媒体文件存放目录
            original_db_name: 原数据库文件名
        """
        # 1. 解压到临时目录
        tmp = tempfile.mkdtemp(prefix='anki_extract_')

        with zipfile.ZipFile(apkg_path, 'r') as zf:
            names = zf.namelist()
            db_candidates = [n for n in names
                            if n.startswith('collection.anki') and not n.endswith('.bak')]
            if not db_candidates:
                raise RuntimeError('未找到 collection.anki* 文件')

            media_files = [n for n in names if not n.startswith('collection.anki')]
            zf.extractall(tmp)

        db_name = db_candidates[0]
        db_path = os.path.join(tmp, db_name)

        # 2. zstd 解压（新版 apkg）
        with open(db_path, 'rb') as f:
            magic = f.read(4)
        if magic == b'\x28\xb5\x2f\xfd':
            if not ZSTD_AVAILABLE:
                shutil.rmtree(tmp, ignore_errors=True)
                raise RuntimeError('需要 zstandard 包：pip install zstandard')
            with open(db_path, 'rb') as f:
                compressed = f.read()
            dctx = _zstd.ZstdDecompressor()
            decompressed = dctx.decompress(compressed, max_output_size=100 * 1024 * 1024)
            # 写出到目标路径
            with open(output_path, 'wb') as f:
                f.write(decompressed)
        else:
            # 旧版：直接复制
            shutil.copy2(db_path, output_path)

        # 3. 媒体文件
        if media_files:
            md = media_dir or (os.path.splitext(output_path)[0] + '_media')
            os.makedirs(md, exist_ok=True)
            for fname in media_files:
                src = os.path.join(tmp, fname)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(md, fname))

            # 写入媒体文件清单
            manifest = os.path.join(md, 'media_manifest.json')
            if os.path.exists(manifest):
                with open(manifest) as f:
                    media_map = json.load(f)
            else:
                media_map = {str(i): fname for i, fname in enumerate(media_files)}
                with open(manifest, 'w') as f:
                    json.dump(media_map, f)
        else:
            md = None

        # 4. 统计笔记数
        import sqlite3
        conn = sqlite3.connect(output_path)
        note_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()

        shutil.rmtree(tmp, ignore_errors=True)

        return {
            'note_count': note_count,
            'media_files': media_files,
            'media_dir': md,
            'original_db_name': db_name,
        }


def main():
    if len(sys.argv) < 3:
        print('用法: python core/extract.py <input.apkg> <output.sqlite> [--mediadir dir]')
        sys.exit(1)

    apkg_path = sys.argv[1]
    output_path = sys.argv[2]
    media_dir = None
    if '--mediadir' in sys.argv:
        idx = sys.argv.index('--mediadir')
        media_dir = sys.argv[idx + 1]

    if not os.path.exists(apkg_path):
        print(f'❌ 文件不存在: {apkg_path}')
        sys.exit(1)

    ext = ApkgExtractor()
    result = ext.extract(apkg_path, output_path, media_dir)

    print(f'✅ 解压完成')
    print(f'   数据库: {output_path} ({os.path.getsize(output_path)/1024:.0f} KB)')
    print(f'   笔记: {result["note_count"]} 条')
    print(f'   媒体文件: {len(result["media_files"])} 个')
    if result['media_dir']:
        print(f'   媒体目录: {result["media_dir"]}')


if __name__ == '__main__':
    main()
