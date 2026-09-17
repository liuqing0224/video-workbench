import {useRef,useState} from 'react';
export function AudioPlayer({src}:{src:string}) {
  const audio=useRef<HTMLAudioElement>(null);
  const [playing,setPlaying]=useState(false),[time,setTime]=useState(0),[duration,setDuration]=useState(0),[error,setError]=useState('');
  const format=(n:number)=>`${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,'0')}`;
  return <div className="audio-controls">
    <audio ref={audio} src={src} preload="metadata" onLoadedMetadata={()=>setDuration(audio.current?.duration||0)} onTimeUpdate={()=>setTime(audio.current?.currentTime||0)} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onEnded={()=>setPlaying(false)} onError={()=>setError('音频加载失败，请重新选择版本。')}/>
    <button aria-label={playing?'暂停音频':'播放音频'} onClick={async()=>{try {if(playing) audio.current?.pause();else await audio.current?.play();}catch{setError('音频暂时无法播放，请重试。');}}}>{playing?'暂停':'播放'}</button>
    <span>{format(time)} / {format(duration)}</span>
    <input aria-label="音频进度" type="range" min={0} max={duration||0} step={0.1} value={time} onChange={e=>{if(audio.current) audio.current.currentTime=Number(e.target.value);setTime(Number(e.target.value));}}/>
    {error&&<p role="alert">{error}</p>}
  </div>;
}
