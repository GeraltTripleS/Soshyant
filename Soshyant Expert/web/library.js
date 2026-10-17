'use strict';
let localModelCatalog, modelActivationPending=false, folderRunning=false, folderStopRequested=false, folderOutcome, modelBrowser, modelScanning=false;
window.loadLocalModels=async function(){
  if(modelActivationPending)return;
  try {localModelCatalog=await api('/api/models');renderLocalModels();}
  catch(error){$('modelPhase').textContent=error.message;}
};
function renderLocalModels(){
  if(!localModelCatalog)return;
  const prior=$('localModelSelect').value;
  $('localModelSelect').replaceChildren(...localModelCatalog.models.map(model=>{
    const option=element('option','',model.name+' · '+t(model.kind==='cloud'?'API':'Local')+(model.active?' · '+t('Active'):''));
    option.value=model.id;option.disabled=!model.available;return option;
  }));
  const active=localModelCatalog.models.find(model=>model.active);
  $('localModelSelect').value=localModelCatalog.models.some(model=>model.id===prior)?prior:active?.id || '';
  $('modelActiveInfo').textContent=(active?.name || '—')+' · '+t(statusNames[localModelCatalog.state] || localModelCatalog.state);
  if(document.activeElement!==$('modelFolderPath'))$('modelFolderPath').value=localModelCatalog.folder.path;
  $('modelRecursive').checked=localModelCatalog.folder.recursive;
  renderModelScanResult();
  modelChoiceInfo();
}
function modelChoiceInfo(){
  const model=localModelCatalog?.models.find(model=>model.id===$('localModelSelect').value);
  const cloud=model?.kind==='cloud';
  $('modelChoiceInfo').textContent=model?(cloud?model.model+' · '+model.base_url:model.path+' · '+(model.bytes/1024**3).toFixed(2)+' GiB'):'';
  $('cloudConsentBox').hidden=!cloud;
  $('cloudDestination').textContent=cloud?t('Selected API destination')+': '+model.base_url:'';
}
$('localModelSelect').onchange=()=>{$('cloudConsent').checked=false;modelChoiceInfo();};
$('cloudProvider').onchange=()=>{$('cloudEndpointLabel').hidden=$('cloudProvider').value==='openai';};
$('cloudConnectionFields').addEventListener('keydown',event=>{if(event.key==='Enter' && event.target.tagName==='INPUT')event.preventDefault();});
$('cloudSave').onclick=async()=>{
  $('cloudSave').disabled=true;$('cloudSaveResult').classList.remove('error');
  $('cloudSaveResult').textContent=t('Saving the API connection on this server…');
  try{
    const result=await api('/api/models/cloud',{method:'POST',data:{name:$('cloudName').value,provider:$('cloudProvider').value,
      base_url:$('cloudEndpoint').value,model:$('cloudModel').value,api_key:$('cloudKey').value,response_mode:$('cloudFormat').value}});
    $('cloudKey').value='';localModelCatalog=result.catalog;renderLocalModels();
    $('localModelSelect').value=result.profile.id;$('cloudConsent').checked=false;modelChoiceInfo();
    $('cloudSaveResult').textContent=t('API model saved. Select and activate it below when ready.');
  }catch(error){$('cloudSaveResult').classList.add('error');$('cloudSaveResult').textContent=t(error.message);}
  finally{$('cloudSave').disabled=false;}
};
function renderModelScanResult(){
  if(!localModelCatalog)return;
  const folder=localModelCatalog.folder, scan=localModelCatalog.scan;
  const count=scan?.found ?? folder.files.length;
  $('modelScanResult').textContent=count+' '+t('models discovered in this folder')+
    ((scan?.invalid ?? folder.invalid.length)?' · '+(scan?.invalid ?? folder.invalid.length)+' '+t('invalid GGUF files skipped'):'')+
    ((scan?.unreadable ?? folder.unreadable?.length)?' · '+(scan?.unreadable ?? folder.unreadable.length)+' '+t('unreadable folders skipped'):'')+
    ((scan?.truncated ?? folder.truncated)?' · '+t('Scan limit reached. Choose a smaller folder.'):'')+
    (count===0?' · '+t('No GGUF models found. Check the folder and subfolder option.'):'');
}
function modelControlsDisabled(disabled){
  for(const id of ['modelActivate','modelBrowse','modelScan','localModelSelect','modelRecursive','modelFolderPath','cloudSave'])$(id).disabled=disabled;
}
async function scanModelFolder(){
  if(modelScanning || modelActivationPending)return;
  modelScanning=true;modelControlsDisabled(true);
  $('modelPhase').classList.remove('error');$('modelPhase').textContent=t('Scanning the local folder…');
  try{
    localModelCatalog=await api('/api/models/scan',{method:'POST',data:{path:$('modelFolderPath').value,recursive:$('modelRecursive').checked}});
    renderLocalModels();
    const discovered=new Set(localModelCatalog.folder.files);
    const first=localModelCatalog.models.find(model=>discovered.has(model.path));
    if(first){$('localModelSelect').value=first.id;modelChoiceInfo();}
    $('modelPhase').textContent=t('Folder scan finished. Choose a model below, then activate it.');
  }catch(error){$('modelPhase').classList.add('error');$('modelPhase').textContent=t(error.message);toast(t(error.message));}
  finally{modelScanning=false;modelControlsDisabled(false);}
}
$('modelScan').onclick=scanModelFolder;
$('modelFolderPath').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();scanModelFolder();}});
async function browseModelFolder(path){
  $('modelFolderError').textContent='';
  $('modelFolderChoose').disabled=true;
  try{
    const result=await api('/api/models/folders'+(path?'?path='+encodeURIComponent(path):''));
    modelBrowser=result;
    $('modelBrowserPath').textContent=result.path;
    $('modelFolderDrive').replaceChildren(...result.roots.map(root=>{const option=element('option','',root);option.value=root;return option;}));
    const drive=result.roots.find(root=>result.path.toLowerCase().startsWith(root.toLowerCase()));
    if(drive)$('modelFolderDrive').value=drive;
    $('modelFolderList').replaceChildren(...result.directories.map(row=>button('▸ '+row.name,()=>browseModelFolder(row.path),'folder-browser-item')));
    if(!result.directories.length)$('modelFolderList').append(element('p','',t('No subfolders. You can select this folder.')));
    if(result.limited)$('modelFolderError').textContent=t('Folder list limited to 1,000 entries. Enter a more specific path if needed.');
    $('modelFolderUp').disabled=result.parent===result.path;
    $('modelFolderChoose').disabled=false;
  }catch(error){$('modelFolderError').textContent=t(error.message);}
}
$('modelBrowse').onclick=async()=>{
  $('modelFolderDialog').showModal();$('modelFolderChoose').disabled=true;
  await browseModelFolder();
};
$('modelFolderDrive').onchange=()=>browseModelFolder($('modelFolderDrive').value);
$('modelFolderUp').onclick=()=>{if(modelBrowser)browseModelFolder(modelBrowser.parent);};
$('modelFolderCancel').onclick=()=>$('modelFolderDialog').close();
$('modelFolderChoose').onclick=async()=>{
  if(!modelBrowser)return;
  $('modelFolderPath').value=modelBrowser.path;$('modelFolderDialog').close();await scanModelFolder();
};
$('modelActivateForm').onsubmit=async event=>{
  event.preventDefault();
  const chosen=localModelCatalog?.models.find(model=>model.id===$('localModelSelect').value);
  if(chosen?.kind==='cloud' && !$('cloudConsent').checked){
    $('modelPhase').textContent=t('Confirm sending answer context to the selected API provider before activation.');return;
  }
  modelActivationPending=true;
  modelControlsDisabled(true);
  $('modelPhase').classList.remove('error');
  $('modelPhase').textContent=t('Loading and checking the model. Keep this page open; this can take up to three minutes.');
  try{
    localModelCatalog=await api('/api/models/activate',{method:'POST',data:{model_id:$('localModelSelect').value,confirm_cloud:$('cloudConsent').checked}});
    renderLocalModels();$('modelPhase').textContent=t('The selected model is active and saved. New answers use this model.');
    await refreshStatus();
  }catch(error){$('modelPhase').classList.add('error');$('modelPhase').textContent=t(error.message);}
  finally{
    modelActivationPending=false;
    modelControlsDisabled(false);
    await loadLocalModels();
  }
};
function folderCandidates(){
  return Array.from($('folderFiles').files).filter(file=>$('folderRecursive').checked || (file.webkitRelativePath || file.name).split('/').length<=2);
}
function folderSummary(){
  if(folderRunning)return;
  const files=folderCandidates();
  const supported=files.filter(file=>/\.(pdf|docx|xlsx|txt|md|html|htm)$/i.test(file.name));
  $('folderSummary').textContent=files.length+' '+t('selected files')+' · '+supported.length+' '+t('supported documents');
}
$('folderFiles').onchange=folderSummary;
$('folderRecursive').onchange=folderSummary;
$('folderStop').onclick=()=>{folderStopRequested=true;$('folderStop').disabled=true;};
$('folderForm').onsubmit=async event=>{
  event.preventDefault();if(folderRunning)return;
  const files=folderCandidates();
  if(files.length>1000){$('folderPhase').textContent=t('Select a smaller folder: at most 1,000 files per import.');return;}
  folderRunning=true;folderStopRequested=false;
  folderOutcome=null;
  for(const id of ['folderStart','folderFiles','folderRecursive','folderAccess'])$(id).disabled=true;
  $('folderStop').hidden=false;$('folderStop').disabled=false;
  const report=$('folderReport');report.replaceChildren();
  let completed=0,skipped=0,failed=0,processed=0;
  try{
    for(const file of files){
      if(folderStopRequested)break;
      const name=file.webkitRelativePath || file.name;
      const row=element('div','folder-result');row.append(element('span','',name));report.append(row);
      try{
        if(!/\.(pdf|docx|xlsx|txt|md|html|htm)$/i.test(file.name)){
          skipped++;row.append(element('small','',t('Skipped: unsupported file type')));continue;
        }
        if(!file.size || file.size>(state.status?.upload_limit_mb || 20)*1024**2)throw Error(t('Empty file or per-file size limit exceeded.'));
        $('folderPhase').textContent=t('Importing file')+' '+(processed+1)+' / '+files.length+' · '+name;
        const query=new URLSearchParams({restricted:$('folderAccess').value,filename:file.name,title:name});
        const result=await api('/api/documents/import?'+query,{method:'POST',raw:file});
        if(result.skipped){skipped++;row.append(element('small','',t('Skipped: identical indexed content')));}
        else{
          await watchJob(result.job_id,phase=>{$('folderPhase').textContent=name+' · '+phase;});
          completed++;row.append(element('small','',t('Indexed')));
        }
      }catch(error){failed++;row.classList.add('error');row.append(element('small','error',error.message));}
      finally{processed++;}
    }
  }finally{
    folderRunning=false;
    for(const id of ['folderStart','folderFiles','folderRecursive','folderAccess'])$(id).disabled=false;
    $('folderStop').hidden=true;
    folderOutcome={stopped:folderStopRequested,completed,skipped,failed,remaining:files.length-processed};
    renderFolderOutcome();
    await loadDocuments().catch(error=>toast(error.message));await refreshStatus().catch(()=>{});
  }
};
function renderFolderOutcome(){
  if(!folderOutcome)return;
  const r=folderOutcome;
  $('folderPhase').textContent=t(r.stopped?'Import stopped. Completed documents are retained.':'Folder import finished.')+' '+r.completed+' '+t('indexed')+' · '+r.skipped+' '+t('skipped')+' · '+r.failed+' '+t('failed')+' · '+r.remaining+' '+t('not processed');
}
window.addEventListener('expert-language-change',()=>{
  const folderPath=$('modelFolderPath').value, recursive=$('modelRecursive').checked;
  renderLocalModels();$('modelFolderPath').value=folderPath;$('modelRecursive').checked=recursive;
  folderSummary();renderFolderOutcome();
  for(const node of document.querySelectorAll('#folderReport small, #modelPhase, #cloudSaveResult'))node.textContent=t(node.textContent);
});
