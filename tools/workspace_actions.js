(async()=>{
  const request=__SIG_REQUEST__, W=window.SigWorkbench;
  const encode=async blob=>{
    const bytes=new Uint8Array(await blob.arrayBuffer());let s='';
    for(const b of bytes)s+=String.fromCharCode(b);return btoa(s);
  };
  let response;
  try {
    await W.ready;
    const records=()=>libAll();
    switch(request.action){
      case 'status': response={configuration:W.config.status(),library:(await records()).map(({blob,...rest})=>rest)};break;
      case 'config-import':
        document.getElementById('settingsJson').value=JSON.stringify(request.value);
        document.getElementById('importSettings').click();
        if(document.getElementById('settingsStatus').textContent.includes('导入失败'))throw Error('Invalid configuration; original preserved');
        // Chromium batches localStorage disk commits for five seconds. Let that real
        // commit finish before this one-shot CLI's browser process is collected.
        await new Promise(resolve=>setTimeout(resolve,6500));
        response=W.config.status();break;
      case 'config-export':response=JSON.parse(W.config.export());break;
      case 'add': {
        const bytes=Uint8Array.from(atob(request.data),c=>c.charCodeAt(0));
        await loadFiles([new File([bytes],request.name,{type:'image/png'})]);
        const r=document.querySelector('.card')?._result;
        if(!r||r.error)throw Error(r?.error||'Image could not be decoded');
        const id=await libAdd({name:request.name,blob:await png300(r.canvas),w:r.canvas.width,h:r.canvas.height,cm:r.cm,ts:Date.now()});
        response={id,ratio:r.ratio,threshold:r.thr};break;
      }
      case 'list': response={items:(await records()).map(({blob,...rest})=>rest)};break;
      case 'rename': {
        const item=await libGet(request.id);if(!item)throw Error('Signature id not found');
        const name=String(request.name||'').trim();if(!name)throw Error('Name is empty');
        item.name=name.slice(0,60);await libPut(item);response={id:item.id,name:item.name};break;
      }
      case 'export': {
        const items=await records();const selected=request.id===null?items:items.filter(x=>x.id===request.id);
        if(request.id!==null&&!selected.length)throw Error('Signature id not found');
        response={items:await Promise.all(selected.map(async({blob,...rest})=>({...rest,data:await encode(blob)})))};break;
      }
      case 'remove': if(!(await libGet(request.id)))throw Error('Signature id not found');await libDel(request.id);response={removed:request.id};break;
      case 'clear':await libClear();response={remaining:(await records()).length};break;
      case 'update':response=await W.checkUpdates();if(response.state==='error')throw Error(response.error);break;
      default:throw Error('Unknown workspace action');
    }
    // Confirm IndexedDB transaction completion before the controlling process exits.
    if(_db)await new Promise((resolve,reject)=>{const tx=_db.transaction(DB_STORE,'readonly');tx.objectStore(DB_STORE).count();tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
    response={ok:true,...response,network:performance.getEntriesByType('resource').map(x=>({url:x.name,initiator:x.initiatorType}))};
  }catch(e){response={ok:false,error:{code:'workspace_failed',message:String(e.message||e)}};}
  await fetch('/__sig_result',{method:'POST',body:JSON.stringify(response)});
})();
