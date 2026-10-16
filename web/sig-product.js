/* Sig's portable preferences and same-origin web version maintenance. */
(function (root) {
  'use strict';
  const DEFAULTS = Object.freeze({ink:'black', inkCustom:'#1a3a8f', scale:4, bias:0,
    deline:false, denoise:true, shortcuts:true, autoCheckUpdates:false});
  const STORAGE_KEY = 'sig-preferences-v1';
  function validate(input) {
    if (!input || input.schema_version !== 1 || input.product !== 'sig' ||
        !input.settings || Array.isArray(input.settings)) throw new Error('不是 Sig 的配置文件');
    const s = input.settings;
    if (Object.keys(s).length !== Object.keys(DEFAULTS).length ||
        Object.keys(s).some(k => !(k in DEFAULTS)) ||
        !['black','blue','darkblue','auto','custom'].includes(s.ink) ||
        typeof s.inkCustom !== 'string' || !/^#[0-9a-f]{6}$/i.test(s.inkCustom) ||
        !Number.isInteger(s.scale) || s.scale < 1 || s.scale > 6 ||
        !Number.isInteger(s.bias) || s.bias < -30 || s.bias > 30 || s.bias % 2 ||
        ['deline','denoise','shortcuts','autoCheckUpdates'].some(k => typeof s[k] !== 'boolean'))
      throw new Error('配置字段或取值无效；原配置未修改');
    return {schema_version:1, product:'sig', settings:{...s}};
  }
  const envelope = settings => validate({schema_version:1, product:'sig', settings});
  function configuration(storage) {
    let current = {...DEFAULTS}, error = null;
    try { const saved = storage.getItem(STORAGE_KEY); if (saved) current = validate(JSON.parse(saved)).settings; }
    catch (e) { error = '本地配置无法读取，使用默认值；原记录保留。' + e.message; }
    return {
      status: () => ({...envelope(current), error}),
      export: () => JSON.stringify(envelope(current), null, 2),
      save(settings) {
        const value = envelope(settings); // Validate before writing; failed writes retain current state.
        storage.setItem(STORAGE_KEY, JSON.stringify(value));
        current = value.settings; error = null; return this.status();
      },
      import(text) { return this.save(validate(JSON.parse(text)).settings); }
    };
  }
  function manifest(input) {
    if (!input || input.schema_version !== 1 || input.product !== 'sig' ||
        typeof input.version !== 'string' || !/^\d+\.\d+\.\d+$/.test(input.version) ||
        input.entry !== './') throw new Error('版本信息无效；请稍后重试');
    return {schema_version:1, product:'sig', version:input.version, entry:input.entry};
  }
  function compare(a, b) {
    const aa = a.split('.').map(Number), bb = b.split('.').map(Number);
    for (let i=0;i<3;i++) if (aa[i] !== bb[i]) return Math.sign(aa[i]-bb[i]);
    return 0;
  }
  async function checkUpdate(current, read) {
    const latest = manifest(await read());
    return {current:manifest(current).version, latest:latest.version,
      state:compare(latest.version,current.version)>0?'available':'current', entry:latest.entry};
  }
  function shortcutMatches(event, enabled) {
    const target = event.target;
    return enabled && event.altKey === true && event.shiftKey === true &&
      !event.ctrlKey && !event.metaKey && !event.repeat && !event.isComposing &&
      typeof event.key === 'string' && event.key.toLowerCase() === 's' &&
      !(target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)));
  }
  const api = {DEFAULTS, STORAGE_KEY, validate, envelope, configuration, manifest, checkUpdate, shortcutMatches};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SigProduct = api;
})(typeof window !== 'undefined' ? window : globalThis);
