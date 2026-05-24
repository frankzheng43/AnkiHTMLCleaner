/// 清理引擎 — HTML 标签/属性/实体清理
use regex::Regex;
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
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

impl Default for CleanConfig {
    fn default() -> Self {
        Self {
            rm_style: true,
            rm_class: true,
            rm_span: true,
            rm_tbody: true,
            p_to_br: true,
            unescape: true,
            rm_crap: true,
            collapse_br: true,
            trim_br: true,
            table_border: true,
            rm_cjk_space: true,
            add_cjk_space: true,
            custom_regex: vec![],
        }
    }
}

lazy_static::lazy_static! {
    static ref RE_STYLE: Regex = Regex::new(r#"\s+style\s*=\s*"[^"]*""#).unwrap();
    static ref RE_STYLE_S: Regex = Regex::new(r#"\s+style\s*=\s*'[^']*'"#).unwrap();
    static ref RE_CLASS: Regex = Regex::new(r#"\s+class\s*=\s*"[^"]*""#).unwrap();
    static ref RE_CLASS_S: Regex = Regex::new(r#"\s+class\s*=\s*'[^']*'"#).unwrap();
    static ref RE_SPAN: Regex = Regex::new(r#"</?span\b[^>]*>"#).unwrap();
    static ref RE_TBODY: Regex = Regex::new(r#"</?tbody\b[^>]*>"#).unwrap();
    static ref RE_P_OPEN: Regex = Regex::new(r#"<p\b[^>]*>"#).unwrap();
    static ref RE_P_CLOSE: Regex = Regex::new(r#"</p\s*>"#).unwrap();
    static ref RE_CRAP: Regex = Regex::new(r#"<!--.*?-->"#).unwrap();
    static ref RE_COLLAPSE_BR: Regex = Regex::new(r#"(<br\s*/?\s*>\s*){2,}"#).unwrap();
    static ref RE_LEAD_BR: Regex = Regex::new(r#"^\s*<br\s*/?\s*>"#).unwrap();
    static ref RE_TAIL_BR: Regex = Regex::new(r#"<br\s*/?\s*>\s*$"#).unwrap();
    static ref RE_DIV_BR_AFTER: Regex = Regex::new(r#"(<div\b[^>]*>)\s*<br\s*/?\s*>"#).unwrap();
    static ref RE_DIV_BR_BEFORE: Regex = Regex::new(r#"<br\s*/?\s*>\s*</div\s*>"#).unwrap();
    static ref RE_TABLE_BORDER: Regex = Regex::new(r#"(<table\b)((?:[^>]*)?>)"#).unwrap();
    static ref RE_TABLE_HAS_BORDER: Regex = Regex::new(r#"<table\b[^>]*\bborder\s*="[^"]*""#).unwrap();
    static ref RE_CJK: Regex = Regex::new(r#"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]"#).unwrap();
    static ref RE_SPACES: Regex = Regex::new(r#"  +"#).unwrap();
}

fn clean_text(text: &str, config: &CleanConfig) -> String {
    let mut s = text.to_string();

    if config.rm_style {
        s = RE_STYLE.replace_all(&s, "").to_string();
        s = RE_STYLE_S.replace_all(&s, "").to_string();
    }
    if config.rm_class {
        s = RE_CLASS.replace_all(&s, "").to_string();
        s = RE_CLASS_S.replace_all(&s, "").to_string();
    }
    if config.rm_span {
        s = RE_SPAN.replace_all(&s, "").to_string();
    }
    if config.rm_tbody {
        s = RE_TBODY.replace_all(&s, "").to_string();
    }
    if config.p_to_br {
        s = RE_P_OPEN.replace_all(&s, "").to_string();
        s = RE_P_CLOSE.replace_all(&s, "<br>").to_string();
    }
    if config.unescape {
        s = html_escape::decode_html_entities(&s).to_string();
    }
    if config.rm_crap {
        s = s.replace("_x000D_", "");
        s = s.replace('\r', "");
        s = RE_CRAP.replace_all(&s, "").to_string();
    }
    if config.collapse_br {
        s = RE_COLLAPSE_BR.replace_all(&s, "${1}").to_string();
    }
    if config.trim_br {
        s = RE_LEAD_BR.replace(&s, "").to_string();
        s = RE_TAIL_BR.replace(&s, "").to_string();
        s = RE_DIV_BR_AFTER.replace_all(&s, "${1}").to_string();
        s = RE_DIV_BR_BEFORE.replace_all(&s, "</div>").to_string();
    }
    if config.table_border {
        if !RE_TABLE_HAS_BORDER.is_match(&s) {
            s = RE_TABLE_BORDER.replace_all(&s, "${1} border=\"1\" style=\"border-collapse: collapse\"${2}").to_string();
        }
    }
    if config.rm_cjk_space {
        let re = Regex::new(&format!(r"({})\s+({})", RE_CJK.as_str(), RE_CJK.as_str())).unwrap();
        s = re.replace_all(&s, "${1}${2}").to_string();
    }
    if config.add_cjk_space {
        let re1 = Regex::new(&format!(r"({})([a-zA-Z])", RE_CJK.as_str())).unwrap();
        let re2 = Regex::new(&format!(r"([a-zA-Z])({})", RE_CJK.as_str())).unwrap();
        let re3 = Regex::new(&format!(r"({})(\d)", RE_CJK.as_str())).unwrap();
        let re4 = Regex::new(&format!(r"(\d)({})", RE_CJK.as_str())).unwrap();
        s = re1.replace_all(&s, "${1} ${2}").to_string();
        s = re2.replace_all(&s, "${1} ${2}").to_string();
        s = re3.replace_all(&s, "${1} ${2}").to_string();
        s = re4.replace_all(&s, "${1} ${2}").to_string();
    }
    for (find, replace) in &config.custom_regex {
        if let Ok(re) = Regex::new(find) {
            s = re.replace_all(&s, replace.as_str()).to_string();
        }
    }
    s = RE_SPACES.replace_all(&s, " ").to_string();
    s.trim().to_string()
}

/// 清理 SQLite 数据库
pub fn clean_db(sqlite_path: &str, output_path: &str, config: &CleanConfig) -> Result<usize, String> {
    // 复制原始数据库
    std::fs::copy(sqlite_path, output_path)
        .map_err(|e| format!("复制数据库失败: {}", e))?;

    let conn = rusqlite::Connection::open(output_path)
        .map_err(|e| format!("打开 SQLite 失败: {}", e))?;

    let mut stmt = conn
        .prepare("SELECT id, mid, flds FROM notes")
        .map_err(|e| format!("查询失败: {}", e))?;

    let rows: Vec<(i64, i64, String)> = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .map_err(|e| format!("读取笔记失败: {}", e))?
        .filter_map(|r| r.ok())
        .collect();

    let total = rows.len();

    for (note_id, _mid, flds) in &rows {
        let fields: Vec<&str> = flds.split('\x1f').collect();
        let mut changed = false;
        let mut new_fields: Vec<String> = Vec::with_capacity(fields.len());

        for field in &fields {
            let cleaned = clean_text(field, config);
            if &cleaned != *field {
                changed = true;
            }
            new_fields.push(cleaned);
        }

        if changed {
            let new_flds = new_fields.join("\x1f");
            conn.execute("UPDATE notes SET flds = ?1 WHERE id = ?2", 
                rusqlite::params![new_flds, note_id])
                .map_err(|e| format!("更新失败: {}", e))?;
        }
    }

    Ok(total)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_clean_style() {
        let cfg = CleanConfig { rm_style: true, ..Default::default() };
        assert_eq!(clean_text(r#"<p style="color:red">text</p>"#, &cfg), "<p>text</p>");
    }

    #[test]
    fn test_clean_span() {
        let cfg = CleanConfig { rm_span: true, ..Default::default() };
        assert_eq!(clean_text("<span>text</span>", &cfg), "text");
    }

    #[test]
    fn test_p_to_br() {
        let cfg = CleanConfig { p_to_br: true, ..Default::default() };
        assert_eq!(clean_text("<p>a</p><p>b</p>", &cfg), "a<br>b<br>");
    }

    #[test]
    fn test_unescape() {
        let cfg = CleanConfig { unescape: true, ..Default::default() };
        assert_eq!(clean_text("&times;&divide;", &cfg), "×÷");
    }

    #[test]
    fn test_collapse_br() {
        let cfg = CleanConfig { collapse_br: true, ..Default::default() };
        assert_eq!(clean_text("a<br><br>b", &cfg), "a<br>b");
    }

    #[test]
    fn test_cjk_space() {
        let cfg = CleanConfig { rm_cjk_space: true, ..Default::default() };
        assert_eq!(clean_text("增 值 税", &cfg), "增值税");
    }
}
