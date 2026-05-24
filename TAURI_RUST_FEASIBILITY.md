# Tauri + Rust 重构可行性分析

## 现状

当前是 Python tkinter 单文件 exe（~14 MB），三步流程：解压 → 清理 → 打包。

## Tauri + Rust 方案

```
┌─────────────────────────────────────┐
│            Tauri App                 │
│  ┌───────────────────────────────┐  │
│  │    Webview (HTML/CSS/JS)      │  │  ← 前端（任意框架）
│  │    - 三个标签页               │  │
│  │    - 清理选项多选框           │  │
│  │    - 进度/日志展示            │  │
│  └───────────┬───────────────────┘  │
│              │ invoke commands       │
│  ┌───────────▼───────────────────┐  │
│  │     Rust Backend              │  │  ← 后端
│  │  ┌─────────────────────────┐  │  │
│  │  │ extract.rs 解压模块     │  │  │
│  │  │ clean.rs   清理引擎     │  │  │
│  │  │ pack.rs    打包模块     │  │  │
│  │  │ lib.rs     主入口       │  │  │
│  │  └─────────────────────────┘  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## 对比

| 项目 | Python (当前) | Tauri + Rust |
|------|-------------|-------------|
| exe 大小 | ~14 MB | **~3-5 MB** |
| 安装依赖 | Python + pip | Rust 工具链 + Node.js |
| 开发速度 | 快 | 慢（需要熟悉 Rust） |
| UI 美观度 | tkinter（简陋） | **HTML/CSS 任意设计** |
| 跨平台 | 仅 Windows | **Windows / Mac / Linux** |
| 正则处理 | 现成 | 需要重写 |
| SQLite | sqlite3 内置 | rusqlite crate |
| zstd | zstandard 包 | zstd crate |
| 打包 apkg | zipfile 内置 | zip crate |

## Rust 后端模块设计

### extract.rs — 解压

```rust
pub fn extract(apkg_path: &str, output_dir: &str) -> Result<ExtractResult>

// 输入: input.apkg（ZIP）
// 输出:
//   - output_dir/collection.sqlite
//   - output_dir/media/（媒体文件）
// 处理:
//   1. zip::read 打开 apkg
//   2. 找到 collection.anki2 或 .anki21b
//   3. 如果是 anki21b，用 zstd::stream::copy_decode 解压
//   4. 写入 .sqlite 文件
//   5. 提取媒体文件
```

### clean.rs — 清理引擎

```rust
pub struct CleanConfig {
    pub rm_style: bool,
    pub rm_class: bool,
    pub rm_span: bool,
    pub rm_tbody: bool,
    pub p_to_br: bool,
    pub unescape: bool,
    pub rm_crap: bool,
    pub collapse_br: bool,
    pub trim_br: bool,
    pub table_border: bool,
    pub rm_cjk_space: bool,
    pub add_cjk_space: bool,
    pub custom_regex: Vec<(String, String)>,
}

// 核心逻辑: 逐个字段应用正则替换
// Rust 的 regex crate 性能比 Python re 快 10-20x
// html_escape crate 处理实体解码
```

### pack.rs — 打包

```rust
pub fn pack(sqlite_path: &str, media_dir: &str,
            output_path: &str, use_zstd: bool) -> Result<()>

// 1. 读取 .sqlite
// 2. 如果需要 zstd，用 zstd crate 压缩
// 3. zip::write 打包 .apkg
```

## Tauri 命令注册

```rust
// Tauri 通过 #[tauri::command] 暴露接口给前端

#[tauri::command]
fn extract(apkg_path: String) -> Result<ExtractResult, String>

#[tauri::command]
fn clean(sqlite_path: String, config: CleanConfig) -> Result<CleanResult, String>

#[tauri::command]
fn pack(sqlite_path: String, media_dir: String,
        output_path: String, use_zstd: bool) -> Result<(), String>

#[tauri::command]
fn get_notetypes(sqlite_path: String) -> Result<Vec<NoteType>, String>

#[tauri::command]
fn export_db(src: String, dst: String) -> Result<(), String>
```

## 前端选型

| 方案 | 大小 | 学习成本 | 推荐度 |
|------|------|---------|-------|
| 原生 HTML + CSS + JS | 零依赖 | 低 | 🌟 推荐 |
| Svelte | 极轻 | 低 | 🌟 推荐 |
| Vue | 轻 | 中 | 可选 |
| React | 重 | 高 | 不推荐 |

推荐用 **原生 HTML/CSS/JS** 或 **Svelte**，保持 exe 最小。

## 可行性结论

| 维度 | 结论 |
|------|------|
| **技术可行性** | ✅ 完全可行，核心逻辑清晰可移植 |
| **exe 体积** | ✅ 14 MB → ~4 MB，优势明显 |
| **UI 美观度** | ✅ HTML/CSS 自由度高，远优于 tkinter |
| **开发成本** | ⚠️ 需要学习 Rust + Tauri 命令系统 |
| **维护成本** | ⚠️ Rust 类型系统严格，编译通过后 bug 极少 |
| **跨平台** | ✅ 一次编写，三平台发布 |
| **性能** | ✅ Rust 正则比 Python 快 10-20x，大数据量优势明显 |

### 进度

✅ 已编写完整 Rust 后端 + HTML/CSS 前端
- `src-tauri/src/extract.rs` — 解压模块
- `src-tauri/src/clean.rs` — 清理引擎（含单元测试）
- `src-tauri/src/pack.rs` — 打包模块
- `src-tauri/src/lib.rs` — Tauri 命令注册
- `src-tauri/src/main.rs` — 入口
- `frontend/index.html` / `style.css` / `script.js` — 三标签页前端

### 本地编译

```bash
# 需要 Rust + Node.js
git checkout feat/tauri-rust-rewrite
./build-tauri.bat
```

或手动：

```bash
cargo install tauri-cli
cargo tauri build
```

## 建议

如果会 Rust → **值得做**，Tauri 生态已成熟（v2 稳定）。
如果不会 Rust → 先学基础（所有权、trait、错误处理），预计 **1-2 周** 可完成移植。
