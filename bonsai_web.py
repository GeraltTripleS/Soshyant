#!/usr/bin/env python3
"""Soshyant Assistant — English voice chat web UI (local LLM + Kokoro TTS).

Run:  .venv/Scripts/python bonsai_web.py  ->  http://127.0.0.1:8091
English-only build: Kokoro TTS, faster-whisper STT, local RAG knowledge base.
"""
import io
import json
import os
import re
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
import soundfile as sf

import rag_store
from bonsai_voice import (SERVER_EXE, SYSTEM_PROMPT, SpeechSplitter,
                          speakable)

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT_WEB = 8091

# ------------------------------------------------------- llm model registry

_LMSTUDIO = r"C:\Users\asus\.lmstudio\models"


def _first_existing(*paths):
    """First existing path — lets a fresh install use models/ while a local
    install falls back to an LM Studio copy of the same file."""
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


def _m(name):
    return _first_existing(os.path.join(ROOT, "models", name),
                           os.path.join(_LMSTUDIO, name))


LLM_MODELS = {
    "bonsai": {
        "label": "Bonsai-2-27B",
        "port": 8081,
        "args": ["-m", _m("Ternary-Bonsai-2-27B-Abliterated-PTQ1_0.gguf"),
                 "-ngl", "99", "-fa", "on", "-c", "16384",
                 "--temp", "1.0", "--top-p", "0.95", "--top-k", "20",
                 "--jinja"],
    },
    "ornith": {
        "label": "Ornith-1.5-9B",
        "port": 8082,
        "args": ["-m", _m("Ornith-1.5-9B-Q4_K_M.gguf"),
                 "--mmproj", _m("mmproj-Ornith-1.5-9B-BF16.gguf"),
                 "-ngl", "99", "-fa", "on", "-c", "16384", "--jinja"],
    },
    "gemma4": {
        "label": "Gemma4-26B-A4B",
        "port": 8083,
        "args": ["-m", _m("Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"),
                 "--mmproj", _m("mmproj-Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-f16.gguf"),
                 "--no-mmproj-offload",
                 "-fa", "on", "-c", "8192", "--jinja"],
    },
    "huihui4b": {
        "label": "Huihui-4B · light",
        "port": 8085,
        "args": ["-m", _m("Huihui-Qwen3.5-4B-abliterated.Q4_K_M.gguf"),
                 "-ngl", "99", "-fa", "on", "-c", "8192", "--no-mmap",
                 "--temp", "0.7", "--top-p", "0.95", "--top-k", "40",
                 "--repeat-penalty", "1.12", "--repeat-last-n", "256",
                 "--chat-template-kwargs", '{"enable_thinking": false}',
                 "--jinja"],
    },
}
LLM_LOCK = threading.Lock()

KOKORO = None                      # loaded once at startup
VOICES: list[dict] = []            # [{id, label}] built after Kokoro loads
STT = None                         # faster-whisper model (background load)
STT_LOCK = threading.Lock()
HISTORIES: dict[str, list] = {}    # session -> messages
HIST_LOCK = threading.Lock()
AUDIO_STORE: dict[str, bytes] = {} # speech id -> wav bytes
AUDIO_LOCK = threading.Lock()

# ------------------------------------------------- rag folder + sync state

RAG_STATE = {"running": False, "phase": "idle", "files_done": 0,
             "files_total": 0, "current": "", "error": None,
             "chunks": 0, "files": 0}
RAG_STATE_LOCK = threading.Lock()
RAG_FOLDER = ""


def _rag_folder_get() -> str:
    global RAG_FOLDER
    if not RAG_FOLDER:
        p = os.path.join(ROOT, "rag_db", "folder.txt")
        if os.path.exists(p):
            RAG_FOLDER = open(p, encoding="utf-8").read().strip()
    return RAG_FOLDER


def _rag_folder_set(path: str):
    global RAG_FOLDER
    os.makedirs(os.path.join(ROOT, "rag_db"), exist_ok=True)
    with open(os.path.join(ROOT, "rag_db", "folder.txt"), "w",
              encoding="utf-8") as f:
        f.write(path)
    RAG_FOLDER = path


def _rag_state(**kw):
    with RAG_STATE_LOCK:
        RAG_STATE.update(kw)


def _rag_snapshot() -> dict:
    with RAG_STATE_LOCK:
        return dict(RAG_STATE)


def _rag_progress(d: dict):
    _rag_state(**d)


def _rag_worker(folder: str):
    try:
        import rag_ingest
        _rag_state(running=True, phase="scanning", files_done=0,
                   files_total=0, current="", error=None)
        rag_ingest.sync(folder, progress=_rag_progress)
        s = rag_store.stats()
        _rag_state(running=False, phase="done", chunks=s["chunks"],
                   files=s["files"])
    except Exception as e:
        print(f"[rag] sync failed: {e}")
        _rag_state(running=False, phase="error",
                   error=f"{e.__class__.__name__}: {e}")


def _llm_up(port: int, attempts: int = 2) -> bool:
    """Health-check with retries: a server busy generating can answer slowly,
    and a false negative here must never trigger a model reload."""
    for i in range(attempts):
        try:
            if requests.get(f"http://127.0.0.1:{port}/health",
                            timeout=3).ok:
                return True
        except requests.RequestException:
            pass
        if i + 1 < attempts:
            time.sleep(0.7)
    return False


def _kill_port(port: int):
    """Stop the llama-server listening on one port, then confirm it's down."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True,
                             text=True).stdout
        for line in out.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                break
    except Exception:
        pass
    for _ in range(20):
        if not _llm_up(port, attempts=1):
            return
        time.sleep(0.5)


def _kill_all_llm():
    """Free the GPU: the LLMs cannot share 8 GB of VRAM."""
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if not any(_llm_up(s["port"], attempts=1)
                   for s in LLM_MODELS.values()):
            return
        time.sleep(1)


def ensure_llm(key: str) -> dict:
    """Make sure the requested model's llama-server is the one running.

    If it is already up — whether we started it or another app did — it is
    adopted as-is; a reload happens solely on a real model switch.
    """
    spec = LLM_MODELS.get(key, LLM_MODELS["bonsai"])
    with LLM_LOCK:
        mpath = next((spec["args"][i + 1] for i, a in enumerate(spec["args"])
                      if a == "-m"), None)
        if mpath and not os.path.exists(mpath):
            raise RuntimeError(f"weights not installed yet: "
                               f"{os.path.basename(mpath)}")
        if _llm_up(spec["port"]):
            for k, s in LLM_MODELS.items():
                if k != key and _llm_up(s["port"], attempts=1):
                    _kill_port(s["port"])
            return spec
        _kill_all_llm()
        proc = subprocess.Popen(
            [SERVER_EXE, "--host", "127.0.0.1", "--port", str(spec["port"]),
             *spec["args"]],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(180):
            if _llm_up(spec["port"]):
                return spec
            if proc.poll() is not None:
                raise RuntimeError(f"llama-server for '{key}' exited "
                                   f"during startup")
            time.sleep(1)
        raise RuntimeError(f"llama-server for '{key}' not healthy after 180s")


# ------------------------------------------------------------------ page

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Soshyant Assistant</title>
<style>
 :root{--bg:#14161a;--panel:#1d2026;--me:#2b4a6f;--ai:#23262d;--txt:#e8e6e3;--dim:#8a8f98}
 *{box-sizing:border-box} body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--txt)}
 #head{display:flex;align-items:center;gap:10px;padding:12px 18px;background:var(--panel);border-bottom:1px solid #2c3038}
 #head h1{font-size:16px;margin:0;font-weight:600}
 #head .sub{color:var(--dim);font-size:12px}
 #model{margin-left:auto;background:#2c3038;border:1px solid #3a3f48;color:var(--txt);border-radius:8px;padding:6px 10px;cursor:pointer;font:inherit;max-width:150px}
 #voice{margin-left:8px;background:#2c3038;border:1px solid #3a3f48;color:var(--txt);border-radius:8px;padding:6px 10px;cursor:pointer;font:inherit;max-width:190px}
 #docs{margin-left:8px;background:#2c3038;border:0;color:var(--txt);border-radius:8px;padding:6px 12px;cursor:pointer}
 #docs.on{background:#2f6f4f;color:#fff}
 #ragpanel{display:flex;align-items:center;gap:8px;padding:8px 18px;background:#181b20;border-bottom:1px solid #2c3038}
 #ragfolder{flex:0 1 380px;background:#14161a;color:var(--txt);border:1px solid #2c3038;border-radius:8px;padding:5px 10px;font:12px/1.4 Consolas,monospace;outline:none}
 #syncbtn{background:#2c3038;border:1px solid #3a3f48;color:var(--txt);border-radius:8px;padding:5px 12px;cursor:pointer;font-size:12px;white-space:nowrap}
 #syncbtn:disabled{opacity:.45;cursor:default}
 #ragprog{flex:1;height:8px;background:#2c3038;border-radius:5px;overflow:hidden;display:none}
 #ragfill{height:100%;width:0;background:#2f6f4f;transition:width .4s}
 #ragstat{color:var(--dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:340px}
 #mute{margin-left:8px;background:#2c3038;border:0;color:var(--txt);border-radius:8px;padding:6px 12px;cursor:pointer}
 #mute.off{opacity:.5;text-decoration:line-through}
 .src{color:var(--dim);font-size:12px;align-self:flex-start;padding:0 8px;max-width:86%;cursor:default}
 #chat{display:flex;flex-direction:column;gap:10px;padding:18px 18px 96px;max-width:820px;margin:0 auto}
 .msg{padding:10px 14px;border-radius:12px;white-space:pre-wrap;max-width:86%}
 .msg.user{background:var(--me);align-self:flex-end;border-bottom-right-radius:4px}
 .msg.ai{background:var(--ai);align-self:flex-start;border-bottom-left-radius:4px}
 .think{color:var(--dim);font-size:12px;align-self:flex-start;padding:2px 8px}
 .speaking{color:#7fbf7f;font-size:12px;align-self:flex-start;padding:2px 8px}
 #bar{display:flex;gap:10px;padding:12px 18px;background:var(--panel);border-top:1px solid #2c3038;position:fixed;bottom:0;left:0;right:0}
 #inp{flex:1;background:#14161a;color:var(--txt);border:1px solid #2c3038;border-radius:10px;padding:10px 14px;font:inherit;outline:none}
 #send{background:#2f6f4f;border:0;color:#fff;border-radius:10px;padding:10px 18px;cursor:pointer;font:inherit}
 #send:disabled{opacity:.4}
 #mic{background:#2c3038;border:1px solid #3a3f48;color:var(--txt);border-radius:10px;padding:8px 14px;cursor:pointer;font:inherit}
 #mic.rec{background:#a03d3d;border-color:#c96;animation:pulse 1.2s infinite}
 @keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
 #mic:disabled{opacity:.4}
</style></head><body>
<div id="head"><h1>🌱 Soshyant Assistant</h1><span class="sub">local · spoken answers</span>
 <select id="model" title="AI model">
  <option value="bonsai">🌱 Bonsai-2-27B</option>
  <option value="ornith">🐦 Ornith-1.5-9B</option>
  <option value="gemma4">🧩 Gemma4-26B</option>
  <option value="huihui4b">🐰 Huihui-4B · light</option>
 </select>
 <select id="voice" title="English voice"></select>
 <button id="docs" title="answer from company documents">&#128218; docs</button>
 <button id="mute" title="toggle voice">&#128266; voice on</button></div>
<div id="ragpanel">
 <input id="ragfolder" placeholder="C:\path\to\company documents" spellcheck="false">
 <button id="syncbtn">&#128260; sync</button>
 <div id="ragprog"><div id="ragfill"></div></div>
 <span id="ragstat">checking&hellip;</span>
</div>
<div id="chat"><div class="msg ai">Hi! Ask me anything &mdash; I'll answer on screen and out loud.</div></div>
<div id="bar"><button id="mic" title="hold conversation: click to record">&#127908;</button><input id="inp" placeholder="Ask anything... (or click 🎤 and speak)" autocomplete="off"><button id="send">Send</button></div>
<script>
const chat=document.getElementById('chat'),inp=document.getElementById('inp'),send=document.getElementById('send');
const muteBtn=document.getElementById('mute'),voiceSel=document.getElementById('voice'),modelSel=document.getElementById('model'),docsBtn=document.getElementById('docs');
{const savedM=localStorage.getItem('soshyant-model');
 if(savedM&&[...modelSel.options].some(o=>o.value===savedM))modelSel.value=savedM;
 modelSel.onchange=()=>localStorage.setItem('soshyant-model',modelSel.value);}
{const savedD=localStorage.getItem('soshyant-docs');
 if(savedD==='1')docsBtn.classList.add('on');
 docsBtn.onclick=()=>{docsBtn.classList.toggle('on');localStorage.setItem('soshyant-docs',docsBtn.classList.contains('on')?'1':'0');};}
function docsOn(){return docsBtn.classList.contains('on');}
// ---- rag folder + sync panel ----
const ragFolder=document.getElementById('ragfolder'),syncBtn=document.getElementById('syncbtn'),
      ragFill=document.getElementById('ragfill'),ragProg=document.getElementById('ragprog'),
      ragStat=document.getElementById('ragstat');
let ragTimer=null;
function drawRag(st){
  ragFolder.value = st.folder || ragFolder.value;
  if(st.running){
    ragStat.textContent = st.phase==='scanning' ? 'scanning folder\u2026'
      : st.phase==='saving' ? 'saving index\u2026'
      : st.phase==='indexing' ? `indexing ${st.files_done}/${st.files_total} \u2014 ${st.current||''}`
      : st.phase;
    ragProg.style.display='block';
    let pct = st.phase==='scanning'?8 : st.phase==='saving'?95 :
      (st.files_total? 5+90*st.files_done/Math.max(1,st.files_total) : 5);
    ragFill.style.width=Math.min(100,pct)+'%';
  }else{
    ragProg.style.display='none';ragFill.style.width='100%';
    ragStat.textContent = st.error ? 'error: '+st.error
      : `${st.chunks} chunks \u00B7 ${st.files} files`;
  }
  syncBtn.disabled=!!st.running;
}
async function pollRag(){
  try{const st=await(await fetch('/knowledge')).json();drawRag(st);
    if(st.running&&!ragTimer)ragTimer=setInterval(pollRag,1200);
    if(!st.running&&ragTimer){clearInterval(ragTimer);ragTimer=null;}
  }catch(e){}
}
syncBtn.onclick=async()=>{
  const folder=ragFolder.value.trim();if(!folder)return;
  syncBtn.disabled=true;
  try{const r=await fetch('/knowledge/ingest',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({folder})});
    if(!r.ok){const j=await r.json();alert(j.error||'sync failed');}
  }catch(e){alert('sync failed: '+e);}
  pollRag();
};
pollRag();
let muted=false,ac=null;
const queue=[];let playing=false,session=crypto.randomUUID();
fetch('/voices').then(r=>r.json()).then(vs=>{
 vs.forEach(v=>{const o=document.createElement('option');o.value=v.id;o.textContent=v.label;voiceSel.appendChild(o);});
 const saved=localStorage.getItem('soshyant-voice');
 if(saved&&vs.some(v=>v.id===saved))voiceSel.value=saved;else voiceSel.value='af_heart';
 voiceSel.onchange=()=>localStorage.setItem('soshyant-voice',voiceSel.value);
});
muteBtn.onclick=()=>{muted=!muted;muteBtn.classList.toggle('off',muted);muteBtn.innerHTML=muted?'&#128263; voice off':'&#128266; voice on';if(!muted)pump();};
function add(cls,text){const d=document.createElement('div');d.className=cls;d.textContent=text;chat.appendChild(d);scrollBottom();return d;}
function scrollBottom(){window.scrollTo({top:document.body.scrollHeight});}
function ensureAudio(){if(!ac)ac=new (window.AudioContext||window.webkitAudioContext)();ac.resume();}
async function speak(id,indicator){const buf=await(await fetch('/audio/'+id)).arrayBuffer();const ab=await ac.decodeAudioData(buf);queue.push(ab);pump();indicator.textContent='\u266A speaking...';}
function pump(){if(playing||!queue.length)return;playing=true;const s=ac.createBufferSource();s.buffer=queue.shift();s.connect(ac.destination);s.onended=()=>{playing=false;pump();};s.start();}
async function ask(){const text=inp.value.trim();if(!text||send.disabled)return;ensureAudio();inp.value='';send.disabled=true;
 add('msg user',text);const reply=add('msg ai','loading model...');reply.dataset.ph=1;const think=add('think','');let said=false,voiceInd=null;
 try{const res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({msg:text,session,voice:voiceSel.value,model:modelSel.value,use_docs:docsOn()})});
  const reader=res.body.getReader();let buf='';
  while(true){const{done,value}=await reader.read();if(done)break;buf+=new TextDecoder().decode(value);
   let i;while((i=buf.indexOf('\n\n'))>=0){const line=buf.slice(0,i).trim();buf=buf.slice(i+2);
    if(!line.startsWith('data: '))continue;const ev=JSON.parse(line.slice(6));
    if(ev.t==='delta'){if(reply.dataset.ph){reply.textContent='';delete reply.dataset.ph;}reply.textContent+=ev.v;scrollBottom();}
    else if(ev.t==='think'){think.textContent='\u2026 thinking ('+ev.n+' chars)';}
    else if(ev.t==='sources'){const s=add('src','\uD83D\uDCDA '+ev.items.map(i=>`[${i.n}] ${i.source}${i.loc?' '+i.loc:''}`).join(' \u00B7 '));
      s.title=ev.items.map(i=>`[${i.n}] ${i.source} ${i.loc}\n${i.snippet}`).join('\n\n');
      chat.insertBefore(s,reply);scrollBottom();}
    else if(ev.t==='speech'){if(!muted){said=true;if(!voiceInd)voiceInd=add('speaking','\u266A speaking...');speak(ev.id,voiceInd);}}}}
 }catch(e){reply.textContent+='[error: '+e+']';}
 think.remove();send.disabled=false;inp.focus();
 if(voiceInd){(function wait(){if(playing||queue.length){setTimeout(wait,300)}else{voiceInd.remove();voiceInd=null;}})();}}
send.onclick=ask;inp.addEventListener('keydown',e=>{if(e.key==='Enter')ask();});inp.focus();
// ---- speech to text ----
const micBtn=document.getElementById('mic');
let recOn=false,recCtx=null,recNode=null,recStream=null,recBuf=[];
micBtn.onclick=async()=>{
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
</script></body></html>"""


# ------------------------------------------------------------------ handler

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # keep console quiet; errors still raise

    # ---- GET ----
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode()
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/healthz":
            self._send(200, "application/json", b'{"status":"ok"}')
        elif self.path == "/voices":
            self._send(200, "application/json",
                       json.dumps(VOICES).encode("utf-8"))
        elif self.path == "/knowledge":
            st = _rag_snapshot()
            st.update(rag_store.stats())
            st["folder"] = _rag_folder_get()
            self._send(200, "application/json",
                       json.dumps(st).encode("utf-8"))
        elif self.path.startswith("/audio/"):
            key = self.path[7:]
            with AUDIO_LOCK:
                wav = AUDIO_STORE.get(key)
            if wav is None:
                self._send(404, "text/plain", b"no such audio")
                return
            self._send(200, "audio/wav", wav)
        else:
            self._send(404, "text/plain", b"not found")

    # ---- POST /stt (speech to text, English) ----
    def stt_request(self):
        if STT is None:
            self._send(503, "application/json",
                       b'{"error":"speech model still loading"}')
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            import numpy as np
            data, sr = sf.read(io.BytesIO(body), dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)
            if sr != 16000:  # linear resample is enough for ASR features
                data = np.interp(np.arange(0, len(data), sr / 16000),
                                 np.arange(len(data)), data)
            data = np.ascontiguousarray(data, dtype=np.float32)
            with STT_LOCK:
                segments, info = STT.transcribe(
                    data, language="en", beam_size=1, vad_filter=True)
                text = " ".join(s.text for s in segments).strip()
            self._send(200, "application/json",
                       json.dumps({"text": text, "lang": "en"}).encode())
        except Exception as e:
            self._send(500, "application/json",
                       json.dumps({"error": f"{e.__class__.__name__}: {e}"}
                                  ).encode())

    def do_POST(self):
        if self.path == "/knowledge/ingest":
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            folder = str(req.get("folder") or "").strip()
            if not os.path.isdir(folder):
                self._send(400, "application/json",
                           json.dumps({"error": "folder does not exist"}
                                      ).encode("utf-8"))
                return
            if _rag_snapshot()["running"]:
                self._send(409, "application/json",
                           json.dumps({"error": "a sync is already running"}
                                      ).encode("utf-8"))
                return
            _rag_folder_set(folder)
            threading.Thread(target=_rag_worker, args=(folder,),
                             daemon=True).start()
            self._send(202, "application/json",
                       json.dumps({"started": True}).encode("utf-8"))
            return
        if self.path.startswith("/stt"):
            self.stt_request()
            return
        if self.path != "/chat":
            self._send(404, "text/plain", b"not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        session = str(req.get("session") or uuid.uuid4())
        self._rid = uuid.uuid4().hex[:6]
        user_msg = str(req.get("msg") or "").strip()
        voice = str(req.get("voice") or "af_heart")
        if voice not in {v["id"] for v in VOICES}:
            voice = "af_heart"
        model_key = str(req.get("model") or "bonsai")
        if model_key not in LLM_MODELS:
            model_key = "bonsai"
        if not user_msg:
            self._send(400, "text/plain", b"empty message")
            return
        try:
            spec = ensure_llm(model_key)
        except Exception as e:
            self._send(500, "application/json",
                       json.dumps({"error": f"{e}"}).encode())
            return

        hkey = f"{session}|{model_key}"
        use_docs = bool(req.get("use_docs")) and rag_store.stats()["chunks"] > 0
        with HIST_LOCK:
            history = HISTORIES.setdefault(hkey, [{"role": "system",
                                                   "content": SYSTEM_PROMPT}])
            history.append({"role": "user", "content": user_msg})
            payload_messages = list(history[-32:])

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit(obj):
            self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
            self.wfile.flush()

        counter = 0
        sources = rag_store.search(user_msg, k=6) if use_docs else []
        # lexical gate: embeddings measure topic similarity, so an
        # out-of-corpus question still pulls same-domain chunks. Require the
        # chunk to share query words that are RARE in the corpus — a word
        # appearing in most chunks (like "project" here) is no evidence.
        all_chunks, _ = rag_store.load()
        total = max(1, len(all_chunks))
        STOP = {"tell", "about", "what", "when", "where", "does", "have",
                "with", "that", "this", "from", "will", "would", "could",
                "should", "please", "give", "show", "explain", "describe",
                "more", "some", "there", "their", "much", "many", "also",
                "into", "over", "only", "very", "which", "while", "these",
                "those", "than", "then", "were", "just", "like", "want",
                "need", "know"}
        qtokens = {t for t in re.findall(r"[a-z0-9]{2,}", user_msg.lower())
                   if len(t) >= 4 and t not in STOP}
        df = {}
        for c in all_chunks:
            cl = c["text"].lower()
            for t in qtokens:
                if t in cl:
                    df[t] = df.get(t, 0) + 1
        qtokens = {t for t in qtokens if df.get(t, 0) / total <= 0.4}
        def _related(c):
            # raw match OR compound match ("hallpass" ↔ "hall pass"):
            # squashed text strips everything but letters/digits
            hay = (c["text"] + " " + c["source"]).lower()
            squash = re.sub(r"[^a-z0-9]", "", hay)
            need = 2 if len(qtokens) >= 3 else 1
            hits = 0
            for t in qtokens:
                if t in hay or t in squash:
                    hits += 1
            return hits >= need
        sources = [s for s in sources if _related(s)]
        docs_payload = {"chat_template_kwargs": {"enable_thinking": False}}
        # relevance floor: weak matches mean the corpus doesn't cover the
        # question — force a refusal instead of letting the model improvise
        relevant = [s for s in sources if s["score"] >= 0.45]
        if use_docs and not relevant:
            # deterministic refusal — the server answers itself, no LLM call,
            # so a loose small model can never improvise on absent topics
            refuse = ("I don't find that in the documents I have. Could you "
                      "rephrase, or ask about something the documents cover?")

            emit({"t": "delta", "v": refuse})
            counter += 1
            self._synth_speak(emit, session, counter, refuse, voice)
            emit({"t": "done"})
            return
        elif relevant:
            # merge grounded instructions into the ONE allowed system message
            # (the Qwen template rejects a second system message)
            ctx = "\n\n".join(
                f"[{i + 1}] ({c['source']} {c['loc']})\n{c['text'][:900]}"
                for i, c in enumerate(relevant[:4]))
            payload_messages[0] = {"role": "system", "content":
                payload_messages[0]["content"] + "\n\nAnswer using ONLY the "
                "company document passages below. Cite the passage number in "
                "square brackets after each claim, like [1]. If the passages "
                "do not contain the answer, respond ONLY with: I don't find "
                "that in the documents I have. Never answer from your general "
                "knowledge, even for famous facts.\n\n" + ctx}
            emit({"t": "sources", "items": [
                {"n": i + 1, "source": c["source"], "loc": c["loc"],
                 "snippet": c["text"][:200]} for i, c in enumerate(relevant)]})

        splitter = SpeechSplitter()
        think_chars = 0
        full = []
        try:
            payload = {
                "messages": payload_messages, "stream": True,
                "max_tokens": spec.get("max_tokens", 2048),
                "temperature": 0.7,
            }
            if use_docs:
                # grounded answers shouldn't spend the budget thinking; the
                # request-level knob works even for models whose server flags
                # leave thinking on
                payload.update(docs_payload)
            r = requests.post(
                f"http://127.0.0.1:{spec['port']}/v1/chat/completions",
                json=payload, stream=True, timeout=600)
            r.raise_for_status()
            r.encoding = "utf-8"   # SSE has no charset header; requests
            #                      # would fall back to latin-1 and mojibake
            for raw in r.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data: "):
                    continue
                data = raw[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk["choices"][0].get("delta", {})
                think = delta.get("reasoning_content") or ""
                if think:
                    think_chars += len(think)
                    emit({"t": "think", "n": think_chars})
                piece = delta.get("content") or ""
                if piece:
                    full.append(piece)
                    emit({"t": "delta", "v": piece})
                    for sent in splitter.feed(piece):
                        counter += 1
                        self._synth_speak(emit, session, counter, sent, voice)
            for sent in splitter.flush():
                counter += 1
                self._synth_speak(emit, session, counter, sent, voice)
            emit({"t": "done"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
                OSError):
            pass  # browser closed the tab mid-answer
        finally:
            text = "".join(full).strip()
            if text:
                with HIST_LOCK:
                    HISTORIES.setdefault(hkey, []).append(
                        {"role": "assistant", "content": text})

    def _synth_speak(self, emit, session, counter, sentence, voice):
        """Clean, synthesize, store WAV, tell the browser to fetch."""
        text = speakable(sentence)
        if not text:
            return
        try:
            audio, sr = KOKORO.create(text, voice=voice, speed=1.0,
                                      lang="en-us")
        except Exception as e:
            print(f"[tts] skipped a sentence ({e.__class__.__name__}: {e})")
            return
        self._store_speech(emit, f"{session}-{self._rid}-{counter}", audio, sr)

    def _store_speech(self, emit, key, audio, sr):
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format="WAV", subtype="FLOAT")
        with AUDIO_LOCK:
            AUDIO_STORE[key] = buf.getvalue()
            if len(AUDIO_STORE) > 400:            # bound memory
                for k in list(AUDIO_STORE)[:200]:
                    AUDIO_STORE.pop(k, None)
        emit({"t": "speech", "id": key})

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_voice_list(kokoro) -> list[dict]:
    """English voices with friendly labels (af_heart -> 'Heart · US female')."""
    accent = {"a": "US", "b": "UK"}
    gender = {"f": "female", "m": "male"}
    out = []
    for v in kokoro.get_voices():
        if len(v) > 3 and v[0] in accent and v[1] in gender and v[2] == "_":
            name = v[3:].capitalize()
            out.append({"id": v,
                        "label": f"{name} · {accent[v[0]]} {gender[v[1]]}"})
    return sorted(out, key=lambda d: d["id"])


def main():
    global KOKORO, VOICES
    from kokoro_onnx import Kokoro
    print("[web] loading Kokoro...")
    KOKORO = Kokoro(os.path.join(ROOT, "tts", "kokoro-fp32.onnx"),
                    os.path.join(ROOT, "tts", "voices-v1.0.bin"))
    VOICES = build_voice_list(KOKORO)
    print(f"[web] {len(VOICES)} English voices available")

    def load_stt():
        global STT
        from faster_whisper import WhisperModel
        STT = WhisperModel(os.path.join(ROOT, "tts", "whisper-base-en"),
                           device="cpu", compute_type="int8", cpu_threads=8)
        print("[web] speech-to-text (whisper base.en, English) ready")

    threading.Thread(target=load_stt, daemon=True).start()
    threading.Thread(target=lambda: ensure_llm("bonsai"), daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT_WEB), Handler)
    print(f"[web] Soshyant Assistant UI: http://127.0.0.1:{PORT_WEB}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
