"""
打包 .sqlite + 媒体文件 → .apkg

用法：
    python core/pack.py input.sqlite output.apkg [--media dir] [--dbname collection.anki2]
    python core/pack.py input.sqlite output.apkg --zstd
"""

import os
import sys
import zipfile
import json

# zstd 支持
try:
    import zstandard as _zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


class ApkgPacker:
    def pack(self, sqlite_path, output_path, media_dir=None,
             use_zstd=None, db_name=None, progress_callback=None):
        """
        打包 SQLite + 媒体文件 → .apkg

        use_zstd:
            True  → 强制 zstd 压缩（新版）
            False → 不压缩（旧版）
            None  → 根据文件名自动判断
        """
        # 1. 确定数据库文件名和压缩方式
        if db_name:
            out_db_name = db_name
        elif use_zstd is True:
            out_db_name = 'collection.anki21b'
        elif use_zstd is False:
            out_db_name = 'collection.anki2'
        else:
            out_db_name = 'collection.anki2'

        with open(sqlite_path, 'rb') as f:
            db_data = f.read()

        # 2. 判断是否需要 zstd 压缩
        should_zstd = use_zstd
        if should_zstd is None:
            should_zstd = (out_db_name.endswith('anki21b'))
        if should_zstd and not ZSTD_AVAILABLE:
            if progress_callback:
                progress_callback('⚠️  zstandard 未安装，跳过 zstd 压缩')
            should_zstd = False
            out_db_name = 'collection.anki2'

        if should_zstd:
            cctx = _zstd.ZstdCompressor(level=3)
            db_data = cctx.compress(db_data)
            out_db_name = 'collection.anki21b'

        # 3. 收集媒体文件
        media_files = {}
        if media_dir and os.path.isdir(media_dir):
            manifest_path = os.path.join(media_dir, 'media_manifest.json')
            if os.path.exists(manifest_path):
                with open(manifest_path) as f:
                    media_map = json.load(f)
                    for val in media_map.values():
                        fpath = os.path.join(media_dir, val)
                        if os.path.exists(fpath):
                            media_files[val] = fpath
            else:
                for fname in sorted(os.listdir(media_dir)):
                    if fname == 'media_manifest.json':
                        continue
                    fpath = os.path.join(media_dir, fname)
                    if os.path.isfile(fpath):
                        media_files[fname] = fpath

        # 4. 打包
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(out_db_name, db_data)
            for arcname, fpath in media_files.items():
                zf.write(fpath, arcname)

        return {
            'output': output_path,
            'db_name': out_db_name,
            'media_count': len(media_files),
            'zstd': should_zstd,
        }


def main():
    if len(sys.argv) < 3:
        print('用法: python core/pack.py <input.sqlite> <output.apkg> [选项]')
        print()
        print('选项:')
        print('  --media dir          媒体文件目录')
        print('  --dbname name        数据库文件名（默认自动）')
        print('  --zstd               强制 zstd 压缩（新版）')
        print('  --no-zstd            强制不压缩（旧版）')
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.exists(input_path):
        print(f'❌ 文件不存在: {input_path}')
        sys.exit(1)

    media_dir = None
    use_zstd = None
    db_name = None

    if '--media' in sys.argv:
        idx = sys.argv.index('--media')
        media_dir = sys.argv[idx + 1]
    if '--dbname' in sys.argv:
        idx = sys.argv.index('--dbname')
        db_name = sys.argv[idx + 1]
    if '--zstd' in sys.argv:
        use_zstd = True
    if '--no-zstd' in sys.argv:
        use_zstd = False

    packer = ApkgPacker()
    result = packer.pack(input_path, output_path, media_dir, use_zstd, db_name)

    print(f'✅ 打包完成')
    print(f'   输出: {result["output"]} ({os.path.getsize(output_path)/1024:.0f} KB)')
    zstd_label = 'zstd' if result['zstd'] else '直接存储'
    print(f'   数据库: {result["db_name"]} ({zstd_label})')
    print(f'   媒体文件: {result["media_count"]} 个')


if __name__ == '__main__':
    main()
