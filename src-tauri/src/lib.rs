mod extract;
mod clean;
mod pack;

use extract::ExtractResult;
use clean::CleanConfig;
use pack::PackResult;
use std::sync::Mutex;

struct AppState {
    sqlite_path: Mutex<Option<String>>,
    cleaned_path: Mutex<Option<String>>,
    media_dir: Mutex<Option<String>>,
    original_db_name: Mutex<Option<String>>,
}

#[tauri::command]
fn extract_apkg(
    apkg_path: String,
    sqlite_out: String,
    media_out: String,
    state: tauri::State<AppState>,
) -> Result<ExtractResult, String> {
    let result = extract::extract(&apkg_path, &sqlite_out, &media_out)?;

    *state.sqlite_path.lock().unwrap() = Some(sqlite_out);
    *state.media_dir.lock().unwrap() = Some(media_out);
    *state.original_db_name.lock().unwrap() = Some(result.original_db_name.clone());

    Ok(result)
}

#[tauri::command]
fn clean_sqlite(
    sqlite_path: String,
    output_path: String,
    config: CleanConfig,
    state: tauri::State<AppState>,
) -> Result<usize, String> {
    let total = clean::clean_db(&sqlite_path, &output_path, &config)?;
    *state.cleaned_path.lock().unwrap() = Some(output_path);
    Ok(total)
}

#[tauri::command]
fn pack_apkg(
    sqlite_path: String,
    output_path: String,
    media_dir: String,
    use_zstd: bool,
    state: tauri::State<AppState>,
) -> Result<PackResult, String> {
    let db_name = state.original_db_name.lock().unwrap().clone();
    pack::pack(&sqlite_path, &output_path, &media_dir, use_zstd, db_name.as_deref())
}

#[tauri::command]
fn get_notetypes(sqlite_path: String) -> Result<Vec<extract::NoteType>, String> {
    let conn = rusqlite::Connection::open(&sqlite_path)
        .map_err(|e| format!("打开 SQLite 失败: {}", e))?;

    let mut stmt = conn
        .prepare("SELECT id, name FROM notetypes")
        .map_err(|e| format!("查询失败: {}", e))?;

    let ntypes: Vec<extract::NoteType> = stmt
        .query_map([], |r| {
            let id: i64 = r.get(0)?;
            let name: String = r.get(1)?;
            Ok((id, name))
        })
        .map_err(|e| format!("读取笔记类型失败: {}", e))?
        .filter_map(|r| r.ok())
        .map(|(id, name)| {
            let conn2 = rusqlite::Connection::open(&sqlite_path).unwrap();
            let mut stmt2 = conn2
                .prepare("SELECT name FROM fields WHERE ntid = ?1 ORDER BY ord")
                .unwrap();
            let fields: Vec<String> = stmt2
                .query_map(rusqlite::params![id], |r| r.get(0))
                .unwrap()
                .filter_map(|r| r.ok())
                .collect();
            extract::NoteType { id, name, fields }
        })
        .collect();

    Ok(ntypes)
}

#[tauri::command]
fn get_note_count(sqlite_path: String) -> Result<i64, String> {
    let conn = rusqlite::Connection::open(&sqlite_path)
        .map_err(|e| format!("打开 SQLite 失败: {}", e))?;
    conn.query_row("SELECT COUNT(*) FROM notes", [], |r| r.get(0))
        .map_err(|e| format!("查询失败: {}", e))
}

#[tauri::command]
fn export_db(src: String, dst: String) -> Result<String, String> {
    std::fs::copy(&src, &dst)
        .map_err(|e| format!("导出失败: {}", e))?;
    let size = std::fs::metadata(&dst).map(|m| m.len()).unwrap_or(0);
    Ok(format!("✅ 已导出: {} KB", size / 1024))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            sqlite_path: Mutex::new(None),
            cleaned_path: Mutex::new(None),
            media_dir: Mutex::new(None),
            original_db_name: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            extract_apkg,
            clean_sqlite,
            pack_apkg,
            get_notetypes,
            get_note_count,
            export_db,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
