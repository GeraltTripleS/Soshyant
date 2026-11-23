// Browser-independent interaction tests; no real microphone or browser state is accessed.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/speech.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(options={}) {
  const nodes={}, calls=[], recorders=[], tracks=[{stopped:false,stop(){this.stopped=true;}}];
  const node=id=>nodes[id] ||= {value:'',hidden:false,disabled:false,readOnly:false,textContent:'',
    classList:{toggle(){}},setAttribute(){},contains(){return false;},focus(){},setCustomValidity(value){this.validity=value;},
    addEventListener(name,fn){this['on'+name]=fn;},dispatchEvent(event){this['on'+event.type]?.(event);}};
  node('question').value=options.draft || '';
  const state={account:{},csrf:'test',conversation:'chat-one',view:'chat',job:null};
  class Recorder {
    constructor(){recorders.push(this);this.state='inactive';}
    start(){this.state='recording';}
    stop(){this.state='inactive';queueMicrotask(()=>{this.ondataavailable?.({data:new Blob(['sample'])});this.onstop?.();});}
  }
  class AudioContext {async decodeAudioData(){return {duration:1};} async close(){}}
  class OfflineAudioContext {
    createBufferSource(){return {connect(){},start(){}};}
    async startRendering(){return {getChannelData:()=>new Float32Array(16000)};}
  }
  const window={isSecureContext:true,AudioContext,MediaRecorder:Recorder,addEventListener(){}};
  const api=async(url,args)=>{
    calls.push([url,args]);
    if(url==='/api/speech')return {enabled:true,installed:true,device:'cpu'};
    if(url==='/api/speech/transcribe')return options.submit?options.submit():{job_id:'test-job'};
    if(url==='/api/speech/jobs/test-job')return {status:'completed',text:options.text || 'How long is the warranty?'};
    return {ok:true};
  };
  const context={window,navigator:{mediaDevices:{getUserMedia:()=>options.permission?options.permission():Promise.resolve({getTracks:()=>tracks})}},
    MediaRecorder:Recorder,OfflineAudioContext,Float32Array,ArrayBuffer,DataView,Blob,Event,Date,Math,Promise,
    setTimeout,clearTimeout,setInterval,clearInterval,$:node,state,api,t:value=>value,toast(){}};
  vm.runInNewContext(source,context);
  return {nodes,node,calls,recorders,tracks,state,voice:window.expertSpeech};
}

test('mic records inline; stop puts transcript in the existing composer without submitting',async t=>{
  const f=fixture({draft:'Existing draft.'});t.after(()=>f.voice.cancel());await settle();
  await f.node('voiceInput').onclick();
  assert.equal(f.node('speechInline').hidden,false);
  assert.equal(f.node('speechStop').hidden,false);
  assert.equal(f.node('askButton').disabled,true);
  assert.equal(f.node('question').readOnly,true);
  f.node('speechStop').onclick();await settle();await settle();
  assert.equal(f.node('question').value,'Existing draft.\nHow long is the warranty?');
  assert.equal(f.node('question').readOnly,false);
  assert.equal(f.node('speechInline').hidden,true);
  assert.equal(f.node('askButton').disabled,false);
  assert.ok(f.tracks[0].stopped);
  assert.ok(!f.calls.some(([url])=>url==='/api/ask'));
});

test('cancel during permission request releases late microphone access without transcribing',async t=>{
  let grant;const pending=new Promise(resolve=>grant=resolve);
  const f=fixture({draft:'Keep this.',permission:()=>pending});t.after(()=>f.voice.cancel());await settle();
  const action=f.node('voiceInput').onclick();f.voice.cancel();
  grant({getTracks:()=>f.tracks});await action;await settle();
  assert.ok(f.tracks[0].stopped);assert.equal(f.recorders.length,0);
  assert.equal(f.node('question').value,'Keep this.');
  assert.ok(!f.calls.some(([url])=>url==='/api/speech/transcribe'));
});

test('cancel discards late transcription jobs and leaves the draft unchanged',async t=>{
  let finish;const pending=new Promise(resolve=>finish=resolve);
  const f=fixture({draft:'Keep this.',submit:()=>pending});t.after(()=>f.voice.cancel());await settle();
  await f.node('voiceInput').onclick();f.node('speechStop').onclick();await settle();
  f.voice.cancel();finish({job_id:'test-job'});await settle();await settle();
  assert.equal(f.node('question').value,'Keep this.');
  assert.ok(f.calls.some(([url])=>url==='/api/speech/jobs/test-job/cancel'));
});

test('long combined transcripts are preserved with a validation error rather than truncated',async t=>{
  const f=fixture({draft:'x'.repeat(3990)});t.after(()=>f.voice.cancel());await settle();
  await f.node('voiceInput').onclick();f.node('speechStop').onclick();await settle();await settle();
  assert.ok(f.node('question').value.length>4000);
  assert.match(f.node('question').validity,/4,000/);
  assert.equal(f.node('speechError').hidden,false);
});
