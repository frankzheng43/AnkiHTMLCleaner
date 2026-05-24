use std::io::{Read, Write};

#[derive(serde::Serialize)]
pub struct PackResult {
    pub output: String,
    pub db_name: String,
    pub media_count: usize,
    pub zstd: bool,
}

/// 打包 SQLite + 媒体文件 → .apkg
pub fn pack(
    sqlite_path: &str,
    output_path: &str,
    media_dir: &str,
    use_zstd: bool,
    db_name: Option<&str>,
) -> Result<PackResult, String> {
    let out_name = match db_name {
        Some(n) => n.to_string(),
        None if use_zstd => "collection.anki21b".to_string(),
        None => "collection.anki2".to_string(),
    };

    // 读取 SQLite
    let sqlite_data = std::fs::read(sqlite_path)
        .map_err(|e| format!("读取数据库失败: {}", e))?;

    // 压缩
    let db_data: Vec<u8> = if use_zstd {
        zstd::encode_all(std::io::Cursor::new(&sqlite_data), 3)
            .map_err(|e| format!("zstd 压缩失败: {}", e))?
    } else {
        sqlite_data
    };

    let out_name = if use_zstd {
        "collection.anki21b".to_string()
    } else {
        out_name
    };

    // 收集媒体文件
    let mut media_files: Vec<(String, String)> = Vec::new();
    let media_path = std::path::Path::new(media_dir);
    if media_path.exists() {
        if let Ok(entries) = std::fs::read_dir(media_path) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_file() {
                    if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                        if name != "media_manifest.json" {
                            media_files.push((name.to_string(), path.to_string_lossy().to_string()));
                        }
                    }
                }
            }
        }
    }

    // 打包 ZIP
    let out_file = std::fs::File::create(output_path)
        .map_err(|e| format!("创建文件失败: {}", e))?;
    let mut zip = zip::ZipWriter::new(out_file);
    let options = zip::write::FileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);

    zip.start_file(&out_name, options)
        .map_err(|e| format!("写入数据库失败: {}", e))?;
    zip.write_all(&db_data)
        .map_err(|e| format!("写入数据失败: {}", e))?;

    for (arc_name, fs_path) in &media_files {
        zip.start_file(arc_name, options)
            .map_err(|e| format!("写入媒体文件失败: {}", e))?;
        let content = std::fs::read(fs_path)
            .map_err(|e| format!("读取媒体文件失败: {}", e))?;
        zip.write_all(&content)
            .map_err(|e| format!("写入媒体数据失败: {}", e))?;
    }

    zip.finish()
        .map_err(|e| format!("关闭 ZIP 失败: {}", e))?;

    Ok(PackResult {
        output: output_path.to_string(),
        db_name: out_name,
        media_count: media_files.len(),
        zstd: use_zstd,
    })
}
