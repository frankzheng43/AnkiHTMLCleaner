use rusqlite::Connection;

/// 提取笔记类型及其字段名
#[derive(Debug, Clone, serde::Serialize)]
pub struct NoteType {
    pub id: i64,
    pub name: String,
    pub fields: Vec<String>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ExtractResult {
    pub note_count: i64,
    pub media_files: Vec<String>,
    pub media_dir: String,
    pub original_db_name: String,
}

/// 解压 apkg → 提取 SQLite + 媒体文件
pub fn extract(apkg_path: &str, sqlite_out: &str, media_out: &str) -> Result<ExtractResult, String> {
    let apkg_file = std::fs::File::open(apkg_path).map_err(|e| format!("打开文件失败: {}", e))?;
    let mut archive = zip::ZipArchive::new(apkg_file).map_err(|e| format!("读取 ZIP 失败: {}", e))?;

    // 找数据库文件
    let db_names: Vec<String> = archive
        .file_names()
        .filter(|n| n.starts_with("collection.anki"))
        .map(|n| n.to_string())
        .collect();

    let db_name = db_names.first().ok_or("未找到 collection.anki* 文件")?;

    // 提取媒体文件列表
    let media_files: Vec<String> = archive
        .file_names()
        .filter(|n| !n.starts_with("collection.anki"))
        .map(|n| n.to_string())
        .collect();

    // 读取数据库文件（先读取数据，释放 archive 的借用后再处理媒体文件）
    let raw_data: Vec<u8> = {
        let mut db_file = archive.by_name(db_name).map_err(|e| format!("读取数据库失败: {}", e))?;
        let mut buf = Vec::new();
        std::io::Read::read_to_end(&mut db_file, &mut buf)
            .map_err(|e| format!("读取数据失败: {}", e))?;
        buf
    };

    // 判断是否 zstd 压缩 (magic: 0x28b52ffd)
    let is_zstd = raw_data.len() >= 4 && raw_data[0..4] == [0x28, 0xb5, 0x2f, 0xfd];

    if is_zstd {
        let decompressed = zstd::decode_all(std::io::Cursor::new(&raw_data))
            .map_err(|e| format!("zstd 解压失败: {}", e))?;
        std::fs::write(sqlite_out, &decompressed)
            .map_err(|e| format!("写入 SQLite 失败: {}", e))?;
    } else {
        std::fs::write(sqlite_out, &raw_data)
            .map_err(|e| format!("写入 SQLite 失败: {}", e))?;
    }

    // 提取媒体文件（archive 的借用已在上面释放）
    for name in &media_files {
        if let Ok(mut f) = archive.by_name(name) {
            let path = format!("{}/{}", media_out, name);
            if let Some(parent) = std::path::Path::new(&path).parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            if let Ok(mut out) = std::fs::File::create(&path) {
                let _ = std::io::copy(&mut f, &mut out);
            }
        }
    }

    // 统计笔记数
    let conn = Connection::open(sqlite_out).map_err(|e| format!("打开 SQLite 失败: {}", e))?;
    let note_count: i64 = conn
        .query_row("SELECT COUNT(*) FROM notes", [], |r| r.get(0))
        .map_err(|e| format!("查询笔记数失败: {}", e))?;

    Ok(ExtractResult {
        note_count,
        media_files,
        media_dir: media_out.to_string(),
        original_db_name: db_name.clone(),
    })
}
