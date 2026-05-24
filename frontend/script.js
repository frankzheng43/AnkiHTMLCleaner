// ── 清理选项 ──
const OPTIONS = [
  ['rm_style',      '删除 style 属性',         '清除所有标签上的 style="..."'],
  ['rm_class',      '删除 class 属性',         '清除所有标签上的 class="..."'],
  ['rm_span',       '删除 <span> 标签',        '无显示效果，仅保留内容'],
  ['rm_tbody',      '删除 <tbody> 标签',       '浏览器会自动插入'],
  ['p_to_br',       '<p> 转 <br>',             '<p>段落</p> → 段落<br>'],
  ['unescape',      'HTML 实体转字符',         '&times; → ×, &divide; → ÷'],
  ['rm_crap',       '清除 _x000D_ 和注释',     'Windows 换行残留和 HTML 注释'],
  ['collapse_br',   '多个 <br> 缩成一个',      '<br><br> → <br>'],
  ['trim_br',       '去掉首尾无意义 <br>',      '段首段尾及 <div> 前后的 <br>'],
  ['table_border',  '表格加默认黑边框',        '<table> → <table border="1">'],
  ['rm_cjk_space',  '删中文间多余空格',        '增值税 一般 → 增值税一般'],
  ['add_cjk_space', '中文与英/数间加空格',      '2025年 → 2025 年'],
];

// ── 状态 ──
let state = {
  sqlitePath: null,
  cleanedPath: null,
  mediaDir: null,
  originalDbName: null,
  noteCount: 0,
};

// ── DOM ──
const $ = id => document.getElementById(id);

// ── 渲染选项 ──
const optsList = document.getElementById('options-list');
OPTIONS.forEach(([key, label, desc]) => {
  const div = document.createElement('div');
  div.className = 'option-item';
  div.innerHTML = `
    <input type="checkbox" id="chk-${key}" checked>
    <label for="chk-${key}">${label}</label>
    <span class="option-desc">${desc}</span>
  `;
  optsList.appendChild(div);
});

// ── 标签切换 ──
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

// ── 日志 ──
function log(el, msg, cls = '') {
  const p = document.createElement('p');
  p.textContent = msg;
  if (cls) p.className = cls;
  el.appendChild(p);
  el.scrollTop = el.scrollHeight;
}

// ── 文件对话框 (Tauri) ──
async function openFileDialog(filters) {
  if (window.__TAURI__) {
    const { open } = window.__TAURI__.dialog;
    return await open({ filters, multiple: false });
  }
  return null;
}

async function saveFileDialog(filters) {
  if (window.__TAURI__) {
    const { save } = window.__TAURI__.dialog;
    return await save({ filters });
  }
  return null;
}

// ── Tab 1: 解压 ──
$('browse-btn').addEventListener('click', async () => {
  const path = await openFileDialog([{ name: 'Anki 牌组', extensions: ['apkg'] }]);
  if (path) $('apkg-path').value = path;
});

$('extract-btn').addEventListener('click', async () => {
  const apkgPath = $('apkg-path').value;
  if (!apkgPath) return alert('请先选择 apkg 文件');

  $('extract-btn').disabled = true;
  const logEl = $('extract-log');
  logEl.innerHTML = '';
  log(logEl, '⏳ 正在解压...');

  try {
    const sqliteOut = `${apkgPath}.sqlite`;
    const mediaOut = `${apkgPath}_media`;

    const result = await invoke('extract_apkg', {
      apkgPath, sqliteOut, mediaOut
    });

    state.sqlitePath = sqliteOut;
    state.mediaDir = mediaOut;
    state.originalDbName = result.original_db_name;
    state.noteCount = result.note_count;

    log(logEl, `✅ 解压完成`, 'ok');
    log(logEl, `   数据库: ${sqliteOut}`, 'info');
    log(logEl, `   笔记: ${result.note_count} 条`, 'info');
    log(logEl, `   媒体文件: ${result.media_files.length} 个`, 'info');

    $('export-sqlite-btn').disabled = false;
    $('tab1-status').innerHTML = `✅ 已解压 ${result.note_count} 条笔记，可进入下一步 🧼`;
  } catch (e) {
    log(logEl, `❌ 失败: ${e}`, 'err');
  }
  $('extract-btn').disabled = false;
});

$('export-sqlite-btn').addEventListener('click', async () => {
  const dst = await saveFileDialog([{ name: 'SQLite', extensions: ['sqlite', 'anki2'] }]);
  if (dst && state.sqlitePath) {
    const msg = await invoke('export_db', { src: state.sqlitePath, dst });
    log($('extract-log'), msg, 'ok');
  }
});

// ── Tab 2: 清理 ──
$('clean-btn').addEventListener('click', async () => {
  if (!state.sqlitePath) return alert('请先在 "① 解压" 中解压 apkg');

  // 收集配置
  const config = {};
  OPTIONS.forEach(([key]) => { config[key] = document.getElementById(`chk-${key}`).checked; });
  config.custom_regex = [];
  if (document.getElementById('custom-enable').checked) {
    const find = document.getElementById('custom-find').value;
    const repl = document.getElementById('custom-replace').value;
    if (find) config.custom_regex.push([find, repl]);
  }

  $('clean-btn').disabled = true;
  const logEl = $('clean-log');
  logEl.innerHTML = '';
  log(logEl, '⏳ 正在清理...');

  try {
    const cleanedPath = `${state.sqlitePath}.cleaned`;
    const total = await invoke('clean_sqlite', {
      sqlitePath: state.sqlitePath,
      outputPath: cleanedPath,
      config
    });

    state.cleanedPath = cleanedPath;
    log(logEl, `✅ 清理完成: ${total} 条笔记`, 'ok');
    $('export-cleaned-btn').disabled = false;
  } catch (e) {
    log(logEl, `❌ 失败: ${e}`, 'err');
  }
  $('clean-btn').disabled = false;
});

$('export-cleaned-btn').addEventListener('click', async () => {
  const dst = await saveFileDialog([{ name: 'SQLite', extensions: ['sqlite', 'anki2'] }]);
  if (dst && state.cleanedPath) {
    const msg = await invoke('export_db', { src: state.cleanedPath, dst });
    log($('clean-log'), msg, 'ok');
  }
});

// ── Tab 3: 打包 ──
$('output-browse-btn').addEventListener('click', async () => {
  const path = await saveFileDialog([
    { name: 'Anki 牌组', extensions: ['apkg'] }
  ]);
  if (path) $('output-path').value = path;
});

$('pack-btn').addEventListener('click', async () => {
  if (!state.cleanedPath) return alert('请先在 "② 清理" 中执行清理');

  const outputPath = $('output-path').value;
  if (!outputPath) return alert('请选择输出位置');

  $('pack-btn').disabled = true;
  const logEl = $('pack-log');
  logEl.innerHTML = '';
  log(logEl, '⏳ 正在打包...');

  try {
    const useZstd = state.originalDbName && state.originalDbName.endsWith('anki21b');
    const result = await invoke('pack_apkg', {
      sqlitePath: state.cleanedPath,
      outputPath,
      mediaDir: state.mediaDir || '',
      useZstd
    });
    log(logEl, `✅ 打包完成`, 'ok');
    log(logEl, `   数据库: ${result.db_name} (${result.zstd ? 'zstd' : '直接存储'})`, 'info');
    log(logEl, `   媒体文件: ${result.media_count} 个`, 'info');
  } catch (e) {
    log(logEl, `❌ 失败: ${e}`, 'err');
  }
  $('pack-btn').disabled = false;
});
