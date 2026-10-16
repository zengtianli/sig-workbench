#!/usr/bin/env node
/* File-based agent adapter for the very same portable Web settings schema. */
'use strict';
const fs = require('node:fs'), path = require('node:path');
const P = require('../web/sig-product.js');
async function main() {
  const words = process.argv.slice(2);
  if (!words.length || words.includes('--help')) {
    console.log('Sig portable configuration and Web version maintenance\n' +
      '  node tools/sig_config.cjs config status --config FILE --json\n' +
      '  node tools/sig_config.cjs config import --config FILE --input JSON_FILE --json\n' +
      '  node tools/sig_config.cjs config export --config FILE --output NEW_FILE --json\n' +
      '  node tools/sig_config.cjs update check [--source VERSION_JSON] --json\n' +
      'Browser settings use localStorage; export them in Settings before CLI readback.\n' +
      'FILE is an explicit portable profile; this command never reads a real browser profile.\n' +
      'Web updates reload the same-origin page; no desktop installer or iCloud container.');
    return;
  }
  const [verb, action] = words.splice(0, 2), flags = {};
  while (words.length) {
    const flag = words.shift();
    if (flag === '--json') continue;
    if (!['--config','--input','--output','--source'].includes(flag) || !words.length || flags[flag])
      throw new Error('未知、重复或缺值的参数：' + flag);
    flags[flag] = words.shift();
  }
  let result;
  if (verb === 'config') {
    if (!flags['--config']) throw new Error('必须指定 --config；不会默认读写用户配置');
    const file = path.resolve(flags['--config']);
    const storage = {
      getItem() { return fs.existsSync(file) ? fs.readFileSync(file,'utf8') : null; },
      setItem(key, text) {
        const temp = file + '.tmp-' + process.pid;
        try { fs.writeFileSync(temp,text,{flag:'wx',mode:0o600}); fs.renameSync(temp,file); }
        finally { if (fs.existsSync(temp)) fs.unlinkSync(temp); }
      }
    };
    const config = P.configuration(storage);
    if (action === 'status') {
      result = config.status();
      if (result.error) throw new Error(result.error);
    } else if (action === 'import' && flags['--input']) {
      result = config.import(fs.readFileSync(flags['--input'],'utf8'));
    } else if (action === 'export' && flags['--output']) {
      fs.writeFileSync(flags['--output'],config.export()+'\n',{flag:'wx',mode:0o600});
      result = config.status();
    } else throw new Error('配置命令或参数无效；参见 --help');
  } else if (verb === 'update' && action === 'check') {
    const current = P.manifest(JSON.parse(fs.readFileSync(path.join(__dirname,'../web/version.json'),'utf8')));
    result = await P.checkUpdate(current,async()=>JSON.parse(fs.readFileSync(flags['--source'] || path.join(__dirname,'../web/version.json'),'utf8')));
  } else throw new Error('未知命令；参见 --help');
  console.log(JSON.stringify(result));
}
main().catch(e=>{console.log(JSON.stringify({error:e.message})); process.exitCode=1;});
