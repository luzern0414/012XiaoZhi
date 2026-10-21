import {getAudioPlayer} from '/js/core/audio/player.js?v=0205';
import {getAudioRecorder} from '/js/core/audio/recorder.js?v=0205';
const $=id=>document.getElementById(id);
const player=getAudioPlayer(), recorder=getAudioRecorder();
let ws, ready=false, busy=false, current=null, turn=null, spoken=true, audioStarted=false, reconnectTimer, deadline;
let pendingUser=null, startedAt=0, firstTokenAt=0, chunks=0, recordingStream=null;
let micStarting=false, generation=0;
const deviceId='browser-'+crypto.randomUUID();
function notice(text){$('notice').textContent=text;}
function scroll(){window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});}
function message(role,text=''){
  $('welcome').hidden=true;
  const article=document.createElement('article'); article.className='message '+role;
  const label=document.createElement('div');label.className='label';label.textContent=role==='user'?'你':'✳ 小智';
  const body=document.createElement('div');body.className='text';body.textContent=text;
  article.append(label,body);$('messages').append(article);scroll();return {article,body};
}
function controls(){ $('send').disabled=!ready||busy; $('mic').disabled=!ready||micStarting||busy&&!recorder.isRecording; $('stop').hidden=!busy||recorder.isRecording; $('send').hidden=busy&&!recorder.isRecording; }
function finish(text){clearTimeout(deadline);if(current){current.article.classList.remove('streaming');if(text&&!current.body.textContent)current.body.textContent=text;} busy=false;controls();}
function watch(){clearTimeout(deadline);deadline=setTimeout(()=>{if(busy){ws?.send(JSON.stringify({type:'abort'}));finish('本次回答超时，请重试。');notice('响应超时，可以重新提问。');}},90000);}
async function audio(){
  if(!window.ModuleInstance)window.ModuleInstance=typeof Module==='function'?Module():Module;
  const context=player.getAudioContext();await context.resume();
  if(!audioStarted){audioStarted=true;await player.start();}
}
function sendEvent(event){if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify(event));}
function submit(text){
  text=text.trim();if(!text||!ready||busy)return;
  player.clearAllAudio();audio().catch(()=>notice('文字可用，音频播放暂不可用。'));
  pendingUser=message('user',text);current=message('assistant');current.article.classList.add('streaming');turn=null;chunks=0;firstTokenAt=0;startedAt=performance.now();
  busy=true;controls();notice('小智正在思考…');watch();
  sendEvent({type:'listen',state:'detect',text});$('question').value='';$('question').style.height='';
}
function connect(){
  generation++;
  clearTimeout(reconnectTimer);if(ws){ws.onclose=null;ws.close();}
  ready=false;controls();$('service').classList.remove('online');$('service').textContent='服务连接中';
  ws=new WebSocket(`ws://${location.hostname}:8000/xiaozhi/v1/?device-id=${encodeURIComponent(deviceId)}&client-id=minimal-web`);const socket=ws;ws.binaryType='arraybuffer';recorder.setWebSocket(ws);
  ws.onopen=()=>sendEvent({type:'hello',version:1,transport:'websocket',features:{text_stream:true,emoji:false},audio_params:{format:'opus',sample_rate:16000,channels:1,frame_duration:60}});
  ws.onmessage=event=>{
    if(socket!==ws)return;
    if(event.data instanceof ArrayBuffer){if(spoken&&audioStarted)player.enqueueAudioData(new Uint8Array(event.data));return;}
    let e;try{e=JSON.parse(event.data);}catch{return;}
    if(e.type==='hello'){setTimeout(()=>{if(socket!==ws||socket.readyState!==WebSocket.OPEN)return;ready=true;controls();$('service').textContent='服务已连接';$('service').classList.add('online');notice('准备好了，聊点什么？');},2500);}
    if(e.type==='stt'){
      if(pendingUser)pendingUser.body.textContent=e.text;
      else{pendingUser=message('user',e.text);current=message('assistant');current.article.classList.add('streaming');}
    }
    if(e.type==='text_stream'){
      if(!busy)return;
      if(e.state==='start'){if(turn&&turn!==e.request_id)return;turn=e.request_id;current??=message('assistant');}
      if(e.request_id!==turn)return;
      if(e.state==='delta'){if(!firstTokenAt)firstTokenAt=performance.now();chunks++;current.body.textContent+=e.text;notice('正在回答…');watch();scroll();}
      if(e.state==='end'){
        current.article.classList.remove('streaming');const meta=document.createElement('div');meta.className='meta';meta.textContent=`${((performance.now()-startedAt)/1000).toFixed(1)} 秒 · 流式回答`;
        meta.dataset.chunks=chunks;meta.dataset.firstTokenMs=Math.round(firstTokenAt-startedAt);current.article.append(meta);notice(spoken?'文字已完成，正在朗读…':'文字已完成');
      }
      if(e.state==='error'){finish(e.text);notice(e.text);}
    }
    if(e.type==='tts'&&e.state==='sentence_start'&&e.text&&!turn){current??=message('assistant');current.body.textContent+=e.text;}
    if(e.type==='tts'&&e.state==='stop'){finish();pendingUser=null;notice('回答完成，可以继续提问。');}
  };
  ws.onerror=()=>notice('连接失败，请检查本地服务是否已启动。');
  ws.onclose=()=>{ready=false;finish('连接已中断，请重新提问。');current=null;pendingUser=null;turn=null;controls();$('service').classList.remove('online');$('service').textContent='服务已断开';notice('正在重新连接…');player.clearAllAudio();stopMicrophone(false);reconnectTimer=setTimeout(connect,4000);};
}
function stopMicrophone(send=true){
  if(recorder.isRecording)recorder.stop();
  recordingStream?.getTracks().forEach(track=>track.stop());recordingStream=null;
  if(send)sendEvent({type:'listen',state:'stop'});
  $('mic').classList.remove('recording');$('mic').setAttribute('aria-label','开始语音输入');$('mic').querySelector('span').textContent='语音输入';
}
$('composer').addEventListener('submit',e=>{e.preventDefault();submit($('question').value);});
$('question').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();submit($('question').value);}});
$('question').addEventListener('input',()=>{$('question').style.height='auto';$('question').style.height=Math.min(140,$('question').scrollHeight)+'px';});
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>submit(b.dataset.prompt));
$('stop').onclick=()=>{sendEvent({type:'abort'});player.clearAllAudio();finish('已停止回答。');pendingUser=null;current=null;turn=null;connect();notice('已停止，正在准备下一次对话…');};
$('reconnect').onclick=()=>{finish();stopMicrophone(false);current=null;pendingUser=null;turn=null;connect();};
$('sound').onclick=()=>{spoken=!spoken;$('sound').setAttribute('aria-pressed',String(spoken));$('sound').querySelector('span').textContent=spoken?'朗读开启':'朗读关闭';if(!spoken)player.clearAllAudio();};
// Keep the actual acquired stream so every microphone track is released on stop.
const nativeGetMedia=navigator.mediaDevices?.getUserMedia.bind(navigator.mediaDevices);
$('mic').onclick=async()=>{
  if(micStarting)return;
  if(recorder.isRecording){stopMicrophone();controls();notice('正在识别你的问题…');watch();return;}
  if(!ready||busy)return;
  micStarting=true;busy=true;controls();const attempt=generation;let stream=null;
  try{
    await audio();player.clearAllAudio();
    if(!nativeGetMedia)throw Error('当前浏览器不支持麦克风');
    stream=await nativeGetMedia({audio:{echoCancellation:true,noiseSuppression:true,sampleRate:16000,channelCount:1}});
    if(attempt!==generation||!ready){stream.getTracks().forEach(track=>track.stop());return;}
    recordingStream=stream;
    sendEvent({type:'listen',state:'start',mode:'manual'});
    const ok=await recorder.start(stream);
    if(attempt!==generation||!ready){stopMicrophone(false);return;}
    if(!ok)throw Error('录音启动失败');
    pendingUser=null;current=null;turn=null;busy=true;startedAt=performance.now();firstTokenAt=0;chunks=0;controls();
    $('mic').classList.add('recording');$('mic').setAttribute('aria-label','结束语音输入');$('mic').querySelector('span').textContent='结束录音';notice('正在听，点击“结束录音”发送。');
  }catch(e){stream?.getTracks().forEach(track=>track.stop());stopMicrophone(false);busy=false;notice('无法使用麦克风，请检查浏览器权限；也可以输入文字。');}
  finally{micStarting=false;if(attempt!==generation)stream?.getTracks().forEach(track=>track.stop());controls();}
};
async function status(){try{const r=await fetch('/api/status',{cache:'no-store'});const data=await r.json();$('device').textContent=data.hardware_online?'硬件在线':data.hardware_configured?'硬件已配置 · 待连接':'硬件未连接';$('device').classList.toggle('online',data.hardware_online);$('model').textContent=data.model+' · 流式对话';}catch{$('device').textContent='硬件状态不可用';}}
window.addEventListener('pagehide',()=>{stopMicrophone(false);ws?.close();});
connect();status();setInterval(status,4000);
