const $=id=>document.getElementById(id);
const chat=$('chat'),inp=$('inp'),send=$('send'),muteBtn=$('mute'),voiceSel=$('voice'),modelSel=$('model'),docsBtn=$('docs'),taskSel=$('task');
function readSaved(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}}
let transcript=readSaved('soshyant-chat',[]);if(!Array.isArray(transcript))transcript=[];
let session=readSaved('soshyant-session',null)||crypto.randomUUID();
let muted=readSaved('soshyant-muted',true),ac=null,playing=false,currentAudio=null,audioEpoch=0;
const queue=[];let audioJobs=Promise.resolve();
function saveChat(){transcript=transcript.slice(-80);try{localStorage.setItem('soshyant-chat',JSON.stringify(transcript.slice(-80)));localStorage.setItem('soshyant-session',JSON.stringify(session));}catch{}}
function docsOn(){return docsBtn.classList.contains('on')||taskSel.value!=='chat';}
const savedM=localStorage.getItem('soshyant-model');if(savedM)modelSel.value=savedM;
modelSel.onchange=()=>localStorage.setItem('soshyant-model',modelSel.value);
if(localStorage.getItem('soshyant-docs')!=='0')docsBtn.classList.add('on');
docsBtn.onclick=()=>{if(taskSel.value!=='chat')return;docsBtn.classList.toggle('on');localStorage.setItem('soshyant-docs',docsOn()?'1':'0');};
const hints={chat:'Ask a question about your documents.',troubleshoot:'Describe the equipment, symptoms, and error codes.',checklist:'Name the equipment and the service work to prepare for.',ticket:'Describe the incident, impact, site visits, and actions already taken.'};
taskSel.onchange=()=>{localStorage.setItem('soshyant-task',taskSel.value);docsBtn.disabled=taskSel.value!=='chat';$('taskHint').textContent=hints[taskSel.value]+(taskSel.value!=='chat'?' This task always uses company documents.':'');inp.placeholder=hints[taskSel.value];};
const savedTask=localStorage.getItem('soshyant-task');if(savedTask&&hints[savedTask])taskSel.value=savedTask;taskSel.onchange();
function stopAudio(){audioEpoch++;queue.length=0;if(currentAudio){currentAudio.onended=null;try{currentAudio.stop();}catch{}currentAudio=null;}playing=false;}
function drawMute(){muteBtn.classList.toggle('off',muted);muteBtn.textContent=muted?'🔇 voice off':'🔊 voice on';}
drawMute();
muteBtn.onclick=()=>{muted=!muted;localStorage.setItem('soshyant-muted',JSON.stringify(muted));drawMute();if(muted)stopAudio();};
function scrollBottom(){window.scrollTo({top:document.body.scrollHeight});}
function add(cls,text){const d=document.createElement('div');d.className=cls;d.textContent=text;chat.appendChild(d);scrollBottom();return d;}
function ensureAudio(){if(!ac)ac=new(window.AudioContext||window.webkitAudioContext)();return ac.resume();}
function pump(){if(muted||playing||!queue.length)return;playing=true;const s=ac.createBufferSource();currentAudio=s;s.buffer=queue.shift();s.connect(ac.destination);s.onended=()=>{currentAudio=null;playing=false;pump();};s.start();}
function speak(id){const epoch=audioEpoch;audioJobs=audioJobs.then(async()=>{if(muted||epoch!==audioEpoch)return;const r=await fetch('/audio/'+encodeURIComponent(id));if(!r.ok)return;const ab=await ac.decodeAudioData(await r.arrayBuffer());if(muted||epoch!==audioEpoch)return;queue.push(ab);pump();}).catch(()=>{});}
function sourceCards(items,reply){const ids=new Map();for(const item of items){const d=document.createElement('details');d.className='source';d.id='source-'+crypto.randomUUID();const summary=document.createElement('summary');summary.textContent=`[${item.n}] ${item.source}${item.loc?' · '+item.loc:''}`;const p=document.createElement('pre');p.textContent=item.snippet;d.append(summary,p);chat.appendChild(d);ids.set(String(item.n),d);}
return ids;}
function finishReply(reply,entry,ids){const text=entry.content;reply.replaceChildren();let last=0;for(const match of text.matchAll(/\[(\d+)\]/g)){reply.append(document.createTextNode(text.slice(last,match.index)));const source=ids.get(match[1]);if(source){const a=document.createElement('a');a.href='#'+source.id;a.textContent=match[0];a.style.color='#a7d4b4';a.onclick=e=>{e.preventDefault();source.open=true;source.scrollIntoView({behavior:'smooth',block:'center'});};reply.append(a);}else reply.append(document.createTextNode(match[0]));last=match.index+match[0].length;}reply.append(document.createTextNode(text.slice(last)));
const copy=add('copy','Copy answer');copy.role='button';copy.tabIndex=0;const copyText=async()=>{try{await navigator.clipboard.writeText(text+'\n\n'+(entry.sources||[]).map(s=>`[${s.n}] ${s.source} ${s.loc||''}\n${s.snippet}`).join('\n\n'));copy.textContent='Copied';}catch{copy.textContent='Select the answer to copy';}};copy.onclick=copyText;copy.onkeydown=e=>{if(e.key==='Enter'||e.key===' ')copyText();};}
function restoreChat(){if(!transcript.length)return;chat.replaceChildren();for(const entry of transcript){if(typeof entry.content!=='string')continue;const reply=add('msg '+(entry.role==='user'?'user':'ai'),entry.content);if(entry.role==='assistant'){const ids=sourceCards(entry.sources||[],reply);finishReply(reply,entry,ids);}}}
restoreChat();
$('newchat').onclick=()=>{if(send.disabled)return;stopAudio();transcript=[];session=crypto.randomUUID();saveChat();chat.replaceChildren();add('msg ai','New conversation. Ask about your documents or choose a task.');inp.focus();};
$('export').onclick=()=>{const text=transcript.map(e=>(e.role==='user'?'You':'Soshyant')+': '+e.content+'\n'+(e.sources||[]).map(s=>`[${s.n}] ${s.source} ${s.loc||''}\n${s.snippet}`).join('\n\n')).join('\n\n');const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='soshyant-chat.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
const ragFolder=$('ragfolder'),syncBtn=$('syncbtn'),ragFill=$('ragfill'),ragProg=$('ragprog'),ragStat=$('ragstat');
let ragTimer=null;
function drawRag(st){if(document.activeElement!==ragFolder)ragFolder.value=st.folder||ragFolder.value;syncBtn.disabled=!!st.running;ragProg.style.display=st.running?'block':'none';ragFill.style.width=(st.files_total?Math.min(95,5+90*st.files_done/st.files_total):8)+'%';ragStat.textContent=st.error?'Sync failed: '+st.error:st.running?`${st.phase} ${st.files_done}/${st.files_total} ${st.current||''}`:`${st.files} files · ${st.chunks} passages`;
$('libraryCount').textContent=`(${(st.documents||[]).length})`;$('lastSync').textContent=st.updated_at?'Last sync: '+new Date(st.updated_at*1000).toLocaleString()+'. Failed or empty files may need attention.':(st.files?'Index available. Sync to refresh file status.':'Sync a folder to start. Scanned documents need readable text.');
$('documentList').replaceChildren();for(const doc of st.documents||[]){const d=document.createElement('div');d.className='document'+(doc.status==='indexed'?'':' issue');const badge=document.createElement('span');badge.className='status';badge.textContent=doc.status;d.append(badge,document.createTextNode(doc.source+' — '+doc.detail));$('documentList').appendChild(d);}}
async function pollRag(){try{const r=await fetch('/knowledge');if(!r.ok)throw Error('Document status unavailable');drawRag(await r.json());}catch(e){ragStat.textContent=e.message;syncBtn.disabled=false;}}
syncBtn.onclick=async()=>{const folder=ragFolder.value.trim();if(!folder){ragStat.textContent='Enter a document folder first.';return;}syncBtn.disabled=true;try{const r=await fetch('/knowledge/ingest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder})});const j=await r.json();if(!r.ok)throw Error(j.error||'Sync failed');await pollRag();}catch(e){ragStat.textContent=e.message;syncBtn.disabled=false;}};
pollRag();ragTimer=setInterval(pollRag,4000);
async function capabilities(){try{const r=await fetch('/capabilities'),j=await r.json();for(const model of j.models){const o=[...modelSel.options].find(o=>o.value===model.id);if(o){o.disabled=!model.installed;o.textContent=model.label+(model.installed?'':' · not installed');}}if(modelSel.selectedOptions[0]?.disabled){const first=[...modelSel.options].find(o=>!o.disabled);if(first)modelSel.value=first.value;}
$('mic').disabled=j.voice.stt!=='ready';$('mic').title=j.voice.stt==='ready'?'Click to record':'Speech input '+j.voice.stt;muteBtn.disabled=j.voice.tts!=='ready';muteBtn.title='Speech output '+j.voice.tts;if(j.voice.tts==='ready'&&!voiceSel.options.length){const vs=await(await fetch('/voices')).json();for(const v of vs){const o=document.createElement('option');o.value=v.id;o.textContent=v.label;voiceSel.appendChild(o);}voiceSel.value=localStorage.getItem('soshyant-voice')||'af_heart';}
if(j.voice.tts==='loading'||j.voice.stt==='loading')setTimeout(capabilities,2500);}catch{setTimeout(capabilities,5000);}}
voiceSel.onchange=()=>localStorage.setItem('soshyant-voice',voiceSel.value);capabilities();
async function ask(){const text=inp.value.trim();if(!text||send.disabled)return;if(!muted){try{await ensureAudio();}catch{muted=true;drawMute();}}stopAudio();inp.value='';send.disabled=true;$('newchat').disabled=true;
const mode=docsOn(),task=taskSel.value,model=modelSel.value,prior=transcript.filter(e=>e.task===task&&e.docs===mode&&e.model===model).slice(-30).map(e=>({role:e.role,content:e.content}));
const question={role:'user',content:text,task,docs:mode,model};transcript.push(question);add('msg user',text);const reply=add('msg ai',mode?'Checking company documents…':'Loading model…');const entry={role:'assistant',content:'',sources:[],task,docs:mode,model};let ids=new Map(),completed=false;
try{const res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({msg:text,session,voice:voiceSel.value,model,use_docs:mode,task,speech:!muted,history:prior})});if(!res.ok){const j=await res.json();throw Error(j.error||'Unable to answer. Please retry.');}
const reader=res.body.getReader(),decoder=new TextDecoder();let buf='';while(true){const {done,value}=await reader.read();if(done)break;buf+=decoder.decode(value,{stream:true});let i;while((i=buf.indexOf('\n\n'))>=0){const line=buf.slice(0,i).trim();buf=buf.slice(i+2);if(!line.startsWith('data: '))continue;const ev=JSON.parse(line.slice(6));if(ev.t==='delta'){entry.content+=ev.v;reply.textContent=entry.content;scrollBottom();}else if(ev.t==='sources'){entry.sources=ev.items;ids=sourceCards(ev.items,reply);}else if(ev.t==='speech'){if(!muted)speak(ev.id);}else if(ev.t==='error')throw Error(ev.v);else if(ev.t==='done')completed=true;}}
if(!completed)throw Error('The connection ended before the answer finished. Please retry.');transcript.push(entry);finishReply(reply,entry,ids);
}catch(e){stopAudio();reply.classList.add('error');reply.textContent=(entry.content?entry.content+'\n\n':'')+e.message;const retry=document.createElement('button');retry.className='retry';retry.textContent='Retry';retry.onclick=()=>{if(send.disabled)return;transcript=transcript.filter(item=>item!==question);taskSel.value=task;taskSel.onchange();modelSel.value=model;docsBtn.classList.toggle('on',mode);inp.value=text;retry.remove();ask();};chat.appendChild(retry);
}finally{saveChat();send.disabled=false;$('newchat').disabled=false;inp.focus();}}
send.onclick=ask;inp.addEventListener('keydown',e=>{if(e.key==='Enter')ask();});inp.focus();
// ---- speech to text ----
const micBtn=document.getElementById('mic');
let recOn=false,recCtx=null,recNode=null,recStream=null,recBuf=[];
micBtn.onclick=async()=>{
 if(send.disabled)return;
 if(recOn){stopRec();return;}
 try{
  recStream=await navigator.mediaDevices.getUserMedia({audio:true});
  recCtx=new AudioContext({sampleRate:16000});
  const src=recCtx.createMediaStreamSource(recStream);
  recNode=recCtx.createScriptProcessor(4096,1,1);
  recBuf=[];
  recNode.onaudioprocess=e=>{if(recOn)recBuf.push(new Float32Array(e.inputBuffer.getChannelData(0)));};
  const mute=recCtx.createGain();mute.gain.value=0;   // keep graph alive without echo
  src.connect(recNode);recNode.connect(mute);mute.connect(recCtx.destination);
  recOn=true;micBtn.classList.add('rec');micBtn.title='click to stop & send';
 }catch(err){alert('Microphone unavailable: '+err.message);}
};
async function stopRec(){
 recOn=false;micBtn.classList.remove('rec');micBtn.title='click to record';
 try{recNode&&recNode.disconnect();recStream&&recStream.getTracks().forEach(t=>t.stop());recCtx&&await recCtx.close();}catch(e){}
 const len=recBuf.reduce((a,b)=>a+b.length,0);if(!len)return;
 const pcm=new Float32Array(len);let o=0;for(const b of recBuf){pcm.set(b,o);o+=b.length;}
 recBuf=[];
 micBtn.disabled=true;inp.value='… transcribing';
 try{
  const r=await fetch('/stt',{method:'POST',headers:{'Content-Type':'audio/wav'},body:encodeWav(pcm,16000)});
  const j=await r.json();
  if(!r.ok)throw Error(j.error||'Transcription failed');
  inp.value=j.text||'';
  if(j.text)ask();
 }catch(e){inp.value='';alert('Transcription failed: '+e);}
 micBtn.disabled=false;
}
function encodeWav(f32,sr){
 const n=f32.length,buf=new ArrayBuffer(44+n*2),v=new DataView(buf);
 const ws=(o,s)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i));};
 ws(0,'RIFF');v.setUint32(4,36+n*2,true);ws(8,'WAVE');ws(12,'fmt ');
 v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
 v.setUint32(24,sr,true);v.setUint32(28,sr*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);
 ws(36,'data');v.setUint32(40,n*2,true);
 for(let i=0;i<n;i++){const s=Math.max(-1,Math.min(1,f32[i]));v.setInt16(44+i*2,s<0?s*32768:s*32767,true);}
 return buf;
}
