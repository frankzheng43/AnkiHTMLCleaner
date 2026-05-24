"""
清理 .sqlite → .sqlite

用法：
    python core/clean.py input.sqlite output.sqlite
    python core/clean.py input.sqlite output.sqlite --config config.json
    python core/clean.py input.sqlite output.sqlite --rm-style --no-rm-class
"""

import os
import sys
import json
import sqlite3
import shutil
import re
from core.engine import CleanEngine, DEFAULT_CONFIG


class SqliteCleaner:
    def clean(self, input_path, output_path, config=None, progress_callback=None):
        """清理 SQLite 数据库中的笔记"""
        if config is None:
            config = DEFAULT_CONFIG.copy()

        # 复制数据库（避免改原文件）
        shutil.copy2(input_path, output_path)

        conn = sqlite3.connect(output_path)
        cur = conn.cursor()
        rows = cur.execute("SELECT id, mid, flds FROM notes").fetchall()
        total = len(rows)

        engine = CleanEngine(config)

        for idx, (note_id, mid, flds) in enumerate(rows):
            if progress_callback and idx % 200 == 0:
                progress_callback(idx, total)

            fields = flds.split('\x1f')
            changed = False
            for fi in range(len(fields)):
                cleaned = engine.clean(fields[fi])
                if cleaned != fields[fi]:
                    fields[fi] = cleaned
                    changed = True
            if changed:
                cur.execute("UPDATE notes SET flds = ? WHERE id = ?",
                           ('\x1f'.join(fields), note_id))

        conn.commit()
        conn.close()

        return {'total': total, 'output': output_path}


def parse_cli_config():
    """从命令行参数解析配置"""
    config = DEFAULT_CONFIG.copy()
    config['custom_regex'] = []

    # 从 JSON 文件读取
    if '--config' in sys.argv:
        idx = sys.argv.index('--config')
        with open(sys.argv[idx + 1]) as f:
            file_cfg = json.load(f)
            config.update(file_cfg)
        del sys.argv[idx:idx + 2]

    # 命令行开关覆盖：--rm-style / --no-rm-style
    cli_keys = {k: k for k in config if not k.startswith('custom')}
    for key in cli_keys:
        if f'--{key}' in sys.argv:
            config[key] = True
        elif f'--no-{key}' in sys.argv:
            config[key] = False

    # 自定义正则
    if '--regex' in sys.argv:
        idx = sys.argv.index('--regex')
        if idx + 2 < len(sys.argv):
            config['custom_regex'].append((sys.argv[idx + 1], sys.argv[idx + 2]))

    return config


def main():
    if len(sys.argv) < 3:
        print('用法: python core/clean.py <input.sqlite> <output.sqlite> [选项]')
        print()
        print('选项:')
        print('  --config file.json      从 JSON 文件读取配置')
        print('  --rm-xxx / --no-rm-xxx  开关单项清理（如 --rm-style --no-rm-class）')
        print('  --regex <查找> <替换>    自定义正则替换')
        print()
        print('可用开关:')
        for k in DEFAULT_CONFIG:
            if k == 'custom_regex':
                continue
            print(f'  --{k} / --no-{k}')
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.exists(input_path):
        print(f'❌ 文件不存在: {input_path}')
        sys.exit(1)

    config = parse_cli_config()

    cleaner = SqliteCleaner()
    result = cleaner.clean(input_path, output_path, config,
                          progress_callback=lambda i, t: None)

    print(f'✅ 清理完成: {result["total"]} 条笔记')
    print(f'   输出: {result["output"]}')


if __name__ == '__main__':
    main()
