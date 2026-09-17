import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';

// Explicit controls avoid the embedded browser's crashing native media toolbar.
export const VideoPlayer = forwardRef<HTMLVideoElement, {src:string}>(({src}, ref) => {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  // Paint decoded frames in the DOM layer: some embedded WebViews omit the
  // native video compositor surface while continuing to play its audio.
  useEffect(() => {
    const media = video.current!, surface = canvas.current!;
    const context = surface.getContext('2d');
    let frame = 0;
    const paint = () => {
      if (context && media.readyState >= 2 && media.videoWidth) {
        if (surface.width !== media.videoWidth || surface.height !== media.videoHeight) {
          surface.width = media.videoWidth;
          surface.height = media.videoHeight;
        }
        context.drawImage(media, 0, 0, surface.width, surface.height);
      }
    };
    const tick = () => { paint(); frame = requestAnimationFrame(tick); };
    const start = () => { cancelAnimationFrame(frame); tick(); };
    const stop = () => { cancelAnimationFrame(frame); paint(); };
    media.addEventListener('loadeddata', paint);
    media.addEventListener('seeked', paint);
    media.addEventListener('play', start);
    media.addEventListener('pause', stop);
    media.addEventListener('ended', stop);
    paint();
    return () => {
      cancelAnimationFrame(frame);
      media.removeEventListener('loadeddata', paint);
      media.removeEventListener('seeked', paint);
      media.removeEventListener('play', start);
      media.removeEventListener('pause', stop);
      media.removeEventListener('ended', stop);
    };
  }, [src]);
  useImperativeHandle(ref, () => video.current!);
  const [playing,setPlaying]=useState(false), [time,setTime]=useState(0), [duration,setDuration]=useState(0), [error,setError]=useState('');
  const clock=(n:number)=>`${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,'0')}`;
  return <div className="video-player">
    <div className="video-surface">
    <canvas ref={canvas} width={1920} height={1080} aria-label="视频画面"/>
    <video ref={video} src={src} playsInline preload="auto"
      onLoadedMetadata={()=>setDuration(video.current?.duration || 0)}
      onTimeUpdate={()=>setTime(video.current?.currentTime || 0)}
      onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onEnded={()=>setPlaying(false)}
      onError={()=>setError('视频加载失败，请重新选择版本或下载文件。')}/>
    </div>
    <div className="video-controls">
      <button aria-label={playing?'暂停视频':'播放视频'} onClick={async()=>{
        try { if(playing) video.current?.pause(); else await video.current?.play(); }
        catch {setError('无法播放视频，请重新选择版本。');}
      }}>{playing?'暂停':'播放'}</button>
      <span aria-live="off">{clock(time)} / {clock(duration)}</span>
      <input aria-label="视频进度" type="range" min="0" max={duration || 0} step="0.1" value={time}
        onChange={e=>{if(video.current) video.current.currentTime=Number(e.target.value);setTime(Number(e.target.value));}}/>
      <button aria-label="后退10秒" onClick={()=>{if(video.current) video.current.currentTime=Math.max(0,time-10);}}>−10秒</button>
      <button aria-label="前进10秒" onClick={()=>{if(video.current) video.current.currentTime=Math.min(duration,time+10);}}>+10秒</button>
    </div>
    {error && <p role="alert">{error}</p>}
  </div>;
});
