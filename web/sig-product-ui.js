(function () {
  'use strict';
  const P = window.SigProduct, el = id => document.getElementById(id);
  const storage = {getItem:key=>window.localStorage.getItem(key), setItem:(key,value)=>window.localStorage.setItem(key,value)};
  const config = P.configuration(storage), dialog = el('settingsDialog');
  let running = null;
  function message(text, failed=false) {
    el('settingsStatus').textContent = text;
    el('settingsStatus').classList.toggle('warn', failed);
  }
  function apply() {
    const s = config.status().settings;
    for (const k of Object.keys(P.DEFAULTS)) {
      if (typeof s[k] === 'boolean') el(k).checked = s[k]; else el(k).value = s[k];
    }
    el('inkCustom').classList.toggle('hidden', s.ink !== 'custom');
    el('scaleV').textContent = s.scale + '×'; el('biasV').textContent = s.bias;
    window.render();
  }
  function save() {
    const s = {};
    for (const k of Object.keys(P.DEFAULTS)) s[k] = typeof P.DEFAULTS[k] === 'boolean' ? el(k).checked :
      typeof P.DEFAULTS[k] === 'number' ? Number(el(k).value) : el(k).value;
    try { config.save(s); message('设置已保存到这个浏览器。'); }
    catch(e) { apply(); message('保存失败，原配置保留。' + e.message, true); }
  }
  function openSettings() { if (!dialog.open) dialog.showModal(); }
  function closeSettings() { dialog.close(); }
  function handleShortcut(event) {
    if (!P.shortcutMatches(event,config.status().settings.shortcuts)) return false;
    event.preventDefault(); openSettings(); return true;
  }
  async function readVersion() {
    const response = await fetch('version.json', {cache:'no-store', credentials:'omit'});
    if (!response.ok) throw new Error('版本信息读取失败（' + response.status + '）');
    return P.manifest(await response.json());
  }
  async function checkUpdates() {
    const label = el('updateStatus'), link = el('getUpdate');
    el('checkUpdates').disabled = true; link.hidden = true;
    try {
      // Without a known running version, retry discovery without falsely declaring latest.
      if (!running) {
        const found = await readVersion();
        label.textContent = '已读到版本 ' + found.version + '；重新载入工作台以确认运行版本';
        link.href = found.entry; link.hidden = false;
        return {state:'reload_required', latest:found.version, entry:found.entry};
      }
      const result = await P.checkUpdate(running, readVersion);
      label.textContent = result.state === 'available' ? '可更新：' + result.current + ' → ' + result.latest : '当前版本 ' + result.current;
      link.hidden = result.state !== 'available';
      link.href = result.entry;
      label.classList.remove('warn');
      return result;
    } catch(e) {
      label.textContent = '检查失败：' + e.message; label.classList.add('warn');
      return {state:'error', error:e.message};
    } finally { el('checkUpdates').disabled = false; }
  }
  el('openSettings').addEventListener('click', openSettings);
  el('closeSettings').addEventListener('click', closeSettings);
  for (const k of Object.keys(P.DEFAULTS)) el(k).addEventListener('change', save);
  el('exportSettings').addEventListener('click', () => { el('settingsJson').value = config.export(); message('配置已导出到下方；只含偏好，不含签名图片。'); });
  el('importSettings').addEventListener('click', () => {
    try { config.import(el('settingsJson').value); apply(); message('配置已导入并保存。'); }
    catch(e) { message('导入失败，原配置保留。' + e.message, true); }
  });
  el('checkUpdates').addEventListener('click', checkUpdates);
  document.addEventListener('keydown', handleShortcut);
  apply();
  if (config.status().error) message(config.status().error, true);
  const ready = readVersion().then(value => {
    running = value; el('currentVersion').textContent = value.version;
    if (config.status().settings.autoCheckUpdates) return checkUpdates();
  }).catch(e => { el('updateStatus').textContent = '版本未知：' + e.message; });
  // Agent/API readback shares the exact same configuration and action routes as the visible UI.
  window.SigWorkbench = {config, ready, saveSettings:save, openSettings, closeSettings, handleShortcut, checkUpdates};
})();
