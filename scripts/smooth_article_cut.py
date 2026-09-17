"""Re-edit existing article narration boundaries without changing speech rate or words."""
import sys,json,re,math,shutil,zipfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.server.core import Store,ROOT,atomic,dumps,digest,uid,now
from adapters.tools import process,hf_command,media_qa
from adapters.timing import check_timing

s=Store(); pid='ddb2465b0e174d398f3de6d6cd2c999e';root=s.root(pid)
old=root/'runs/article-v1/work';w=root/'runs/article-v2/work'
if w.exists() and '--resume' not in sys.argv: raise SystemExit('v2 已存在；中断恢复使用 --resume')
for part in ['documents','assets','audio','captions','hyperframes']:
 if not (w/part).exists(): shutil.copytree(old/part,w/part)
for part in ['qa','exports']: (w/part).mkdir(exist_ok=True)
def cmd(args,log):return process(args,w,w/'qa'/log)
recipe=json.loads((w/'documents/recipe.json').read_text());oldtime=json.loads((old/'documents/timing.json').read_text())
records=[];shots=[];captions=[];start=0.; boundaries=[]
for i,seg in enumerate(recipe['segments']):
 sid=seg['id'];raw=w/'audio'/f'{sid}.wav';m=json.loads(raw.with_suffix('.json').read_text());duration=m['duration_s']
 log=cmd(['ffmpeg','-hide_banner','-i',raw,'-af','silencedetect=noise=-30dB:d=0.08','-f','null','-'],f'{sid}-silence.log')
 ranges=[];a=None
 for kind,value in re.findall(r'silence_(start|end): ([\d.]+)',log):
  if kind=='start':a=float(value)
  elif a is not None:ranges.append((a,float(value)));a=None
 # Trim ONLY the boundary silence detected; keep guards around speech.
 head=next((b for a,b in ranges if a<.04),0)
 tail=next((a for a,b in reversed(ranges) if b>=duration-.005),duration)
 trim_start=max(0,head-.08);trim_end=min(duration,tail+.12)
 nframes=math.ceil((trim_end-trim_start)*30)
 kept=nframes/30
 dst=w/'audio'/f'{sid}-trim.wav'
 cmd(['ffmpeg','-y','-i',raw,'-af',f'atrim=start={trim_start}:end={trim_end},asetpts=PTS-STARTPTS,afade=t=in:d=0.005,afade=t=out:st={max(0,trim_end-trim_start-.005)}:d=0.005,apad=whole_dur={kept}', '-t',str(kept),'-ar','48000','-ac','2',dst],f'{sid}-trim.log')
 oldgap=oldtime['shots'][i]['duration_s']-duration
 records.append(dst)
 boundaries.append({'shot_id':sid,'source_sha256':digest(raw),'source_duration_s':duration,'trim_start_s':trim_start,'trim_end_s':trim_end,'original_extra_hold_s':round(oldgap,4),'new_extra_hold_s':round(kept-(trim_end-trim_start),4),'output_sha256':digest(dst),'threshold_db':-30,'speech_guard_head_s':.08,'speech_guard_tail_s':.12})
 shots.append({'shot_id':sid,'start_s':round(start,6),'duration_s':kept})
 captions.append({'id':sid,'start_s':round(start,6),'duration_s':kept,'text':seg['text'],'method':'trimmed_utterance_bounds'})
 start+=kept
atomic(w/'audio/concat.txt',''.join(f"file '{p.name}'\n" for p in records))
voice=w/'audio/narration-continuous.wav'
cmd(['ffmpeg','-y','-f','concat','-safe','0','-i',w/'audio/concat.txt','-c','copy',voice],'concat.log')
h=w/'hyperframes';shutil.copyfile(voice,h/'assets/narration-continuous.wav')
page=(old/'hyperframes/index.html').read_text()
for shot in shots:
 sid=shot['shot_id']
 pattern=rf'(<section[^>]*id="{sid}"[^>]*data-start=")[^"]+(" data-duration=")[^"]+'
 page=re.sub(pattern,lambda m:m[1]+str(shot['start_s'])+m[2]+str(shot['duration_s']),page)
page=re.sub(r'(<div id="root"[^>]*data-duration=")[^"]+',lambda m:m[1]+str(start),page)
page=re.sub(r'<audio\b[^>]*></audio>','',page)
page=page.replace('</div><script>','<div id="progress" style="position:absolute;left:0;bottom:0;width:100%;height:5px;background:#a43b20;transform-origin:left center"></div><audio id="continuous-voice" class="clip" src="assets/narration-continuous.wav" data-start="0" data-duration="'+str(start)+'" data-track-index="1"></audio></div><script>')
page=re.sub(r'<script>const tl=.*?</script>',f'<script>const tl=gsap.timeline({{paused:true}});tl.fromTo("#progress",{{scaleX:0}},{{scaleX:1,duration:{start},ease:"none"}},0);window.__timelines["main"]=tl;</script>',page,flags=re.S)
# Balance the longest subtitle rather than leaving a single orphan at line end.
page=page.replace('下一次看人工智能设计，别只问好不好看，要问改了什么，为什么。','下一次看人工智能设计，别只问好不好看，要问改了什么、为什么。')
atomic(h/'index.html',page)
timing={'fps':30,'total_duration_s':round(start,6),'status':'auto_timed','human_review':'not_done','shots':shots,'captions':captions}
atomic(w/'documents/timing.json',dumps(timing));atomic(w/'qa/boundary-edits.json',dumps(boundaries))
def stamp(t):
 ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
atomic(w/'captions/narration.srt','\n\n'.join(f"{i+1}\n{stamp(c['start_s'])} --> {stamp(c['start_s']+c['duration_s'])}\n{c['text']}" for i,c in enumerate(captions))+'\n')
atomic(w/'qa/timing-check.json',dumps(check_timing(w/'documents/timing.json',h/'index.html')))
print('DURATION',start,'SAVED',oldtime['total_duration_s']-start,flush=True)
cmd(hf_command('check',h),'hyperframes-check.log')
raw=w/'exports/render.mp4'
if not raw.exists(): cmd(hf_command('render',h,raw),'render.log')
log=cmd(['ffmpeg','-hide_banner','-i',raw,'-vn','-af','loudnorm=I=-18:TP=-2:LRA=11:print_format=json','-f','null','-'],'normalize-pass1.log')
m=json.loads(re.search(r'\{\s*"input_i".*?\}',log,re.S).group())
filt=f"loudnorm=I=-18:TP=-2:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=json"
final=w/'exports/second-production-line-v2.mp4'
cmd(['ffmpeg','-y','-i',raw,'-c:v','copy','-af',filt,'-ar','48000','-ac','2','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(round(start,6)),final],'normalize-pass2.log')
targets=s.project(pid)['config']['targets']|{'duration_s':start}
report=media_qa(final,w/'qa/final',targets,lambda args,log:process(args,w,log))
if report['automated_status']!='pass':raise RuntimeError('最终QA未通过')
for i,t in enumerate(shots):
 cmd(['ffmpeg','-y','-ss',str(t['start_s']+1),'-i',final,'-frames:v','1',w/'qa'/f'shot-{i+1:02}.jpg'],f'shot-{i+1:02}.log')
shutil.copyfile(w/'qa/shot-01.jpg',w/'exports/cover.jpg');shutil.copyfile(w/'captions/narration.srt',w/'exports/narration.srt')
notes=f'''# v2 连贯性修订

用户反馈：每页停顿，连贯性差。
原因：每页独立配音首尾空白 + 统一0.6秒空白 + 自检4秒/结尾2秒停留 + 标题反复入场。
修改：仅裁掉检测出的片段边界低电平区，保留起音80ms/尾音120ms保护；不删除句中停顿，不加速声音。取消固定空白与强制答题等待；合并连续声音轨。标题稳定显示，画面随叙述换镜，不重复入场。
时长：103.680 → {report['actual']['duration_s']:.3f} 秒。
旧版完整保留在 article-v1；本版 SHA256 {digest(final)}。
QA：{report['automated_status']}，{report['loudness']['input_i']} LUFS，{report['loudness']['input_tp']} dBTP。
字幕按新真实片段边界重排，非词级对齐。声音自然度仍需用户试听。
'''
atomic(w/'documents/CHANGELOG-v2.md',notes);atomic(w/'exports/README.md',notes)
# Remove inherited v1 report to avoid presenting old QA as v2 evidence.
(w/'documents/PRODUCTION-REPORT.md').unlink(missing_ok=True)
atomic(w/'exports/delivery.json',dumps({'version':'v2','previous_video_sha256':digest(old/'exports/second-production-line.mp4'),'video_sha256':digest(final),'qa':'qa/final/report.json','human_listening':'not_done','files':{str(f.relative_to(w)):digest(f) for f in w.rglob('*') if f.is_file() and f.name!='render.mp4'}}))
with zipfile.ZipFile(w/'exports/delivery-v2.zip','w',zipfile.ZIP_DEFLATED) as z:
 for f in w.rglob('*'):
  if f.is_file() and f.name not in ['render.mp4','delivery-v2.zip']:z.write(f,f.relative_to(w))
for part in ['documents','audio','captions','hyperframes']:shutil.copytree(w/part,root/part,dirs_exist_ok=True)
s.scan(pid)
with s.conn() as c:
 for f in w.rglob('*'):
  if f.is_file() and f.suffix in ['.mp4','.zip','.md','.json','.jpg','.srt'] and f.name!='render.mp4':
   c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uid(),pid,None,str(f.relative_to(root)),digest(f),'automated_delivery',now()))
 s.event(c,pid,None,'automation.stage',{'stage':'delivery','status':'completed','details':'v2 连贯性修订：重剪配音边界、统一声音轨、重排镜头字幕，最终QA通过；未伪造试听确认'})
s.export_status(pid)
print('FINAL',final,flush=True)
