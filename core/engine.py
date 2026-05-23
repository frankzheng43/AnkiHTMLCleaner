"""
清理引擎 — 可独立使用，也可被其他脚本导入
"""

import re
import html


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
        for find, replace in self.config.get('custom_regex', []):
            try:
                text = re.sub(find, replace, text)
            except:
                pass
        text = re.sub(r'  +', ' ', text)
        return text.strip()


# 默认配置（全开）
DEFAULT_CONFIG = {
    'rm_style': True,
    'rm_class': True,
    'rm_span': True,
    'rm_tbody': True,
    'p_to_br': True,
    'unescape': True,
    'rm_crap': True,
    'collapse_br': True,
    'trim_br': True,
    'table_border': True,
    'rm_cjk_space': True,
    'add_cjk_space': True,
    'custom_regex': [],
}
