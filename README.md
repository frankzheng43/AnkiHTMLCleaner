# 税务师 Anki 牌组 HTML 清理工具

清理 Anki 导出的 `.apkg` 文件中从 Word/网页复制粘贴带来的冗余 HTML 标签和属性。

## 背景

税务师考试 Anki 牌组（`税务师.apkg`）是从某个平台导出的，卡片内容里塞满了大量多余的 HTML：

```html
<!-- 清理前 -->
<div class="question-analysis-wrap" style="margin: 0; padding: 0;">
  <p style="text-align: left; color: #000000;">
    ①纳税人&nbsp;&nbsp;自办理&nbsp;税务登记…<br><br>
  </p>
</div>

<!-- 清理后 -->
<div>
①纳税人自办理税务登记…<br>
</div>
```

## 清理内容

| 项目 | 操作 |
|------|------|
| `style="..."` | 全部删除 |
| `class="..."` | 全部删除 |
| `<span>` | 标签删除，内容保留 |
| `<tbody>` | 标签删除，内容保留 |
| `<p>` | 转成 `<br>` |
| `&times;` `&divide;` `&radic;` 等 | 转成真实字符 × ÷ √ |
| `&nbsp;` `&ensp;` `&emsp;` | 转成普通空格 |
| `_x000D_` | 删除（Windows 换行残留） |
| HTML 注释 `<!-- ... -->` | 删除 |
| 多个连续 `<br>` | 缩成一个 |
| 段首段尾无意义 `<br>` | 删除 |
| `<div>` 前后无意义 `<br>` | 删除 |
| 中文字符间多余空格 | 删除 |
| 中文与英文/数字间 | 加一个空格 |
| 表格 | 加 `border="1" style="border-collapse: collapse"` |

## 保留的标签

`<div>` `<br>` `<b>` `<strong>` `<u>` `<table>` `<tr>` `<td>` `<ul>` `<ol>` `<li>` `<h3>` `<h5>` `<hr>` `<img>` `<blockquote>` 等有实际显示效果的标签。

## 文件说明

```
税务师.apkg                        原始文件（未修改）
税务师_cleaned_puretext.apkg       清理后的文件，可直接导入 Anki
clean_anki_html.py                 清理脚本
```

## 使用方法

### 清理其他 apkg 文件

编辑 `clean_anki_html.py` 顶部配置：

```python
APKG_PATH = r'你的文件.apkg'        # 改输入文件
OUTPUT_APKG = r'输出文件.apkg'      # 改输出文件
```

然后运行：

```bash
python clean_anki_html.py
```

### 依赖

- Python 3.8+
- `libzstd.dll`（脚本会自动从 Logseq 自带的 Git 中加载，或手动指定路径）

## 技术细节

Apkg 格式（Anki 2.1.50+）：
1. 本质是 ZIP 压缩包
2. 内部数据库 `collection.anki21b` 使用 **zstd** 压缩（非普通 zip）
3. 解压后是 SQLite 数据库，核心表为 `notes`，字段内容存放在 `flds` 列中
4. 各字段以 `\x1f`（Unit Separator）分隔
