'use strict';
// Inline local dictation; the existing question composer is the only editor.
(() => {
  let recorder=null, stream=null, timer=null, clock=null, job=null, generation=0, phase='idle';
  const busy=()=>phase!=='idle';
  const message=text=>{$('speechPhase').textContent=t(text);};
  function cleanup() {
    clearTimeout(timer);clearInterval(clock);timer=clock=null;
    if(recorder?.state==='recording')recorder.stop();
    stream?.getTracks().forEach(track=>track.stop());stream=null;recorder=null;
  }
  function controls(next) {
    phase=next;
    $('speechInline').hidden=!busy();
    $('speechStop').hidden=phase!=='recording';
    $('voiceInput').classList.toggle('recording',phase==='recording');
    $('voiceInput').disabled=busy() || Boolean(state.job) || $('question').disabled;
    $('voiceInput').setAttribute('aria-pressed',String(busy()));
    $('question').readOnly=busy();
    $('askButton').disabled=busy() || Boolean(state.job) || $('question').disabled;
  }
  function fail(text) {
    $('speechError').textContent=t(text);$('speechError').hidden=false;
  }
  function cancel() {
    generation++;cleanup();
    const previous=job;job=null;
    if(previous)api('/api/speech/jobs/'+previous+'/cancel',{method:'POST',data:{}}).catch(()=>{});
    controls('idle');
  }
  async function refresh() {
    if(!state.account)return;
    try {
      const status=await api('/api/speech');
      $('voiceInput').hidden=!(status.enabled && status.installed);
      if((!status.enabled || !status.installed) && busy())cancel();
      if(!$('speechSettings').contains(document.activeElement)) {
        $('speechEnabled').checked=status.enabled;$('speechDevice').value=status.device;
      }
      $('speechInstallation').textContent=t(status.installed?'Speech module installed. English only.':'Speech module is not installed. Run SETUP-SPEECH.bat on the server.');
      if(!busy())controls('idle');
    } catch {$('voiceInput').hidden=true;}
  }
  async function wav(blob) {
    if (blob.size > 10 * 1024 * 1024) throw new Error(t('Choose an audio file smaller than 10 MB.'));
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) throw new Error(t('This browser cannot decode audio. Try a current desktop browser.'));
    const context = new Context();
    let decoded;
    try { decoded = await context.decodeAudioData(await blob.arrayBuffer()); }
    finally { await context.close(); }
    if (decoded.duration > 30 || decoded.duration < .1) throw new Error(t('Record between 0.1 and 30 seconds.'));
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
    const source = offline.createBufferSource(); source.buffer = decoded; source.connect(offline.destination); source.start();
    const samples = (await offline.startRendering()).getChannelData(0);
    const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
    const text = (offset, value) => {for (let i=0;i<value.length;i++) view.setUint8(offset+i,value.charCodeAt(i));};
    text(0,'RIFF'); view.setUint32(4,36+samples.length*2,true); text(8,'WAVE'); text(12,'fmt ');
    view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
    view.setUint32(24,16000,true); view.setUint32(28,32000,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
    text(36,'data'); view.setUint32(40,samples.length*2,true);
    for (let i=0;i<samples.length;i++) {const value=Math.max(-1,Math.min(1,samples[i]));view.setInt16(44+i*2,value<0?value*32768:value*32767,true);}
    return buffer;
  }
  async function transcribe(blob, token, conversation) {
    controls('transcribing');message('Transcribing locally. You can cancel.');
    try {
      const audio=await wav(blob);
      if(token!==generation)return;
      const result=await api('/api/speech/transcribe',{method:'POST',raw:audio});
      if(token!==generation){await api('/api/speech/jobs/'+result.job_id+'/cancel',{method:'POST',data:{}}).catch(()=>{});return;}
      job=result.job_id;const started=Date.now();
      while(token===generation) {
        if(Date.now()-started>210000)throw new Error(t('Transcription timed out. Try a shorter recording.'));
        const current=await api('/api/speech/jobs/'+job);
        if(token!==generation)return;
        if(current.status==='completed') {
          await api('/api/speech/jobs/'+job+'/consume',{method:'POST',data:{}}).catch(()=>{});job=null;
          if(token!==generation || state.conversation!==conversation || state.view!=='chat')return;
          const draft=$('question').value.trim();
          $('question').value=(draft?draft+'\n':'')+current.text.trim();
          $('question').dispatchEvent(new Event('input',{bubbles:true}));
          if($('question').value.length>4000)fail('The combined question exceeds 4,000 characters. Shorten the text.');
          else {$('speechError').hidden=true;toast(t('Voice added. Review your question and send.'));}
          break;
        }
        if(current.status==='failed' || current.status==='canceled')throw new Error(t(current.error || 'Transcription canceled.'));
        await new Promise(resolve=>setTimeout(resolve,700));
      }
    } catch(error) {
      if(token===generation) {
        fail(error.message);
        if(job)await api('/api/speech/jobs/'+job+'/cancel',{method:'POST',data:{}}).catch(()=>{});
        job=null;
      }
    } finally {
      if(token===generation){controls('idle');$('question').focus();}
    }
  }
  $('voiceInput').onclick=async()=>{
    if(busy() || state.job || $('question').disabled)return;
    const token=++generation, conversation=state.conversation;
    $('speechError').hidden=true;controls('requesting');
    try {
      if(!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)throw new Error(t('Microphone recording requires localhost or HTTPS.'));
      if(!window.MediaRecorder)throw new Error(t('Recording is unavailable in this browser.'));
      message('Allow microphone access in your browser.');
      const granted=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1},video:false});
      if(token!==generation){granted.getTracks().forEach(track=>track.stop());return;}
      stream=granted;recorder=new MediaRecorder(stream);const chunks=[];
      recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
      recorder.onstop=()=>{
        if(token!==generation)return;
        const type=chunks[0]?.type || 'audio/webm';cleanup();
        transcribe(new Blob(chunks,{type}),token,conversation);
      };
      recorder.onerror=()=>{if(token!==generation)return;cancel();fail('Recording failed. Please try again.');};
      recorder.start();controls('recording');
      const started=Date.now();
      // The elapsed counter stays in the composer, next to stop/cancel.
      const update=()=>{$('speechPhase').textContent=t('Listening… English only')+' · '+Math.floor((Date.now()-started)/1000)+' / 30 s';};
      update();clock=setInterval(update,1000);
      timer=setTimeout(()=>{if(recorder?.state==='recording')recorder.stop();},29000);
    } catch(error) {
      if(token===generation){cancel();fail(error.name==='NotAllowedError'?'Microphone access was denied. Allow microphone access in your browser to record.':error.message);}
    }
  };
  $('speechStop').onclick=()=>{if(recorder?.state==='recording')recorder.stop();};
  $('speechCancel').onclick=()=>{cancel();$('question').focus();};
  $('question').addEventListener('input',()=>{
    const tooLong=$('question').value.length>4000;
    $('question').setCustomValidity(tooLong?t('The combined question exceeds 4,000 characters. Shorten the text.'):'');
    if(!tooLong)$('speechError').hidden=true;
  });
  window.addEventListener('pagehide',cancel);
  $('speechSettings').onsubmit=async event=>{
    event.preventDefault();const submit=event.submitter;submit.disabled=true;$('speechSettingsError').textContent='';
    try {await api('/api/speech/settings',{method:'POST',data:{enabled:$('speechEnabled').checked,device:$('speechDevice').value}});await refresh();toast(t('Speech settings saved.'));}
    catch(error){$('speechSettingsError').textContent=t(error.message);}finally{submit.disabled=false;}
  };
  window.expertSpeech={refresh,cancel,busy};
  window.addEventListener('expert-language-change',refresh);
  refresh();
})();
