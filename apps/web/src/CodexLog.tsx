import {useEffect, useRef, useState} from 'react';
import type {CodexActivity} from './codexProgress';

export function CodexLog({runId, entries, checked, running, error}: {runId:string; entries:CodexActivity[]; checked:number; running:boolean; error:boolean}) {
  const viewport = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [following, setFollowing] = useState(true);
  useEffect(()=>{follow.current=true;setFollowing(true);},[runId]);
  useEffect(()=>{
    if (follow.current && viewport.current) viewport.current.scrollTop=viewport.current.scrollHeight;
  },[entries,runId]);
  const resume = () => {
    follow.current=true;setFollowing(true);
    if(viewport.current) viewport.current.scrollTop=viewport.current.scrollHeight;
  };
  return <section className="codex-progress" aria-label="实时运行日志">
    <div className="section-head"><h3>实时运行日志</h3><span className="muted">{running?'实时更新中':'运行记录'} · {entries.length} 条</span></div>
    <div className="codex-log" ref={viewport} tabIndex={0} role="log" aria-label="执行记录" aria-live="off" onScroll={()=>{
      const el=viewport.current;if(!el)return;
      const atBottom=el.scrollHeight-el.scrollTop-el.clientHeight<32;
      follow.current=atBottom;setFollowing(atBottom);
    }}>
      {entries.length ? <ol>{entries.map((a,index)=><li key={a.id}><span className="log-number">{String(index+1).padStart(3,'0')}</span><span className="activity-state">{a.state}</span><p>{a.text}</p></li>)}</ol> : <p className="muted">等待新的执行记录。模型未输出时不会生成占位进度。</p>}
    </div>
    <div className="log-footer"><span className="muted">{following?'跟随最新记录':'已暂停滚动，可查看历史'}{checked ? ` · 最近检查 ${new Date(checked).toLocaleTimeString('zh-CN',{hour12:false})}`:''}</span><button onClick={resume} disabled={following}>回到最新</button></div>
    {error && <p role="status">日志暂时读取失败，保留现有记录，稍后自动重试。</p>}
    <small className="muted">每 3 秒读取真实日志，累计保留当前页面最近 500 条执行事件；重新进入仅载入日志尾部。已记录不代表人工验收通过。</small>
  </section>;
}
