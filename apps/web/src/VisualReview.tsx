import {useEffect,useState} from 'react';
import {VideoPlayer} from './VideoPlayer';
type Candidate={id:string;name:string;description:string;reference:string;sample_path:string;fingerprint:string;ready:boolean;error:string};
type State={required:boolean;candidates:Candidate[];approved:string|null;error?:string;history:{id:string;actor:string;decision:string;candidate_id:string}[]};
export function VisualReview({projectId,api,onChange}:{projectId:string;api:(path:string,data?:any)=>Promise<any>;onChange:()=>Promise<any>}) {
 const [data,setData]=useState<State|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[viewed,setViewed]=useState<Record<string,boolean>>({});
 useEffect(()=>{let live=true;setData(null);setError('');setViewed({});api(`/projects/${projectId}/visual`).then(d=>{if(live)setData(d)}).catch(e=>{if(live)setError(String(e))});return()=>{live=false}},[projectId]);
 async function choose(c:Candidate){setBusy(true);setError('');try{const d=await api(`/projects/${projectId}/visual/review`,{candidate_id:c.id,fingerprint:c.fingerprint,actor:'user',decision:'approve',note:`用户在视觉方向面板选择 ${c.name}；只确认本小样视觉，不代表整片或声音已验收。`});setData(d);await onChange()}catch(e){setError(String(e))}finally{setBusy(false)}}
 if(!data?.required&&!error)return null;
 return <section className="panel visual-review" aria-label="视觉方向确认">
 <h2>先选视觉方向</h2><p className="muted">比较实际动态小样，再选你认可的方向。技术检查通过不会替你选择配色。</p>
 {(error||data?.error)&&<p role="alert">{error||data?.error}</p>}
 {!data?.candidates.length&&<p>尚未准备视觉小样。可以继续整理资料和声音；完整预览与交付会等待视觉确认。</p>}
 <div className="visual-candidates">{data?.candidates.map(c=><article key={c.id}>
 <h3>{c.name}{data.approved===c.id?' · 已选择':''}</h3><p>{c.description}</p><p className="muted">参考：{c.reference}</p>
 {c.ready?<div className="player"><VideoPlayer key={c.fingerprint} src={`/api/projects/${projectId}/visual/${encodeURIComponent(c.id)}/sample?fingerprint=${c.fingerprint}`}/></div>:<p role="alert">{c.error}</p>}
 <label className="visual-check"><input type="checkbox" checked={!!viewed[c.fingerprint]} onChange={e=>setViewed({...viewed,[c.fingerprint]:e.target.checked})}/>我已看过这个小样，认可其配色、排版和动效方向</label>
 <button disabled={busy||!c.ready||!viewed[c.fingerprint]||data.approved===c.id} onClick={()=>choose(c)}>选择「{c.name}」</button>
 </article>)}</div>
 {data?.history.length? <details><summary>视觉确认历史（{data.history.length}）</summary>{data.history.map(r=><p key={r.id}>{r.actor==='user'?'用户视觉选择':'自动化检查（不代表视觉认可）'} · {r.candidate_id} · {r.decision==='approve'?'通过':'要求修改'}</p>)}</details>:<p className="hint">等待你的选择；目前没有任何方向被确认。</p>}
 <p className="hint">下方版本预览包含历史文件；选择方向不会自动替换旧成片，需按所选设计重新制作整片。</p>
 </section>
}
