"""Render an explicit, data-only article recipe in the Worker's isolated run directory."""
import html, json, math, re, shutil, sys, zipfile
from pathlib import Path
from apps.server.core import ROOT, atomic, digest, dumps
from adapters.tools import Blocked, Cancelled, hf_command, media_qa
from adapters.timing import check_timing


def validate_recipe(data):
    if data.get('schema_version') != 1:
        raise ValueError('不支持的文章制作方案版本')
    for field, limit in [('title',120),('source_text',100000),('boundary',300)]:
        if not isinstance(data.get(field),str) or not 0 < len(data[field]) <= limit:
            raise ValueError('文章方案字段无效：'+field)
    style=data.get('visual_style','cards')
    if style not in ('cards','menza-case-study-v2'):
        raise ValueError('不支持的案例设计')
    if style=='menza-case-study-v2' and (len(data.get('segments',[]))!=8 or not isinstance(data.get('reference_plan'),str) or not data['reference_plan'].strip()):
        raise ValueError('案例版需要8个镜头及参考映射')
    segments=data.get('segments')
    if not isinstance(segments,list) or not 1 <= len(segments) <= 20:
        raise ValueError('需要1–20个镜头')
    ids=set()
    for item in segments:
        sid=item.get('id','')
        if not re.fullmatch(r'SH\d{2}',sid) or sid in ids:
            raise ValueError('镜头编号无效或重复')
        ids.add(sid)
        for field,limit in [('text',150),('title',32),('chapter',50),('key',60),('source_section',200)]:
            if not isinstance(item.get(field),str) or not 0<len(item[field])<=limit:
                raise ValueError(f'{sid} 字段无效：{field}')
        if item.get('layout') not in ('compare','flow'):
            raise ValueError('不支持的镜头版式')
        n=2 if item['layout']=='compare' else 3
        for field,limit in [('labels',16),('details',32)]:
            if not isinstance(item.get(field),list) or len(item[field])!=n or any(not isinstance(v,str) or not 0<len(v)<=limit for v in item[field]):
                raise ValueError(f'{sid} 图形文本无效')
    return data


def build_html(recipe,shots,total):
    if recipe.get('visual_style')=='menza-case-study-v2':
        from adapters.article_visuals import build_case_film
        return build_case_film(recipe,shots,total)
    esc=html.escape; sections=[]; motion=[]
    for i,(seg,shot) in enumerate(zip(recipe['segments'],shots)):
        sid=seg['id']; start=shot['start_s']; dur=shot['duration_s']
        cards=''.join(f'<div class="card" id="{sid}-card{j}"><div class="number">0{j+1}</div><h2>{esc(label)}</h2><p>{esc(detail)}</p></div>'+ ('<div class="arrow">→</div>' if j<len(seg['labels'])-1 else '') for j,(label,detail) in enumerate(zip(seg['labels'],seg['details'])))
        title=''.join(f'<span>{esc(line)}</span>' for line in seg['title'].split('\n'))
        theme='dark' if i in (0,len(shots)-1) else 'light'
        sections.append(f'''<section id="{sid}" class="scene clip {theme}" data-shot-id="{sid}" data-start="{start}" data-duration="{dur}" data-track-index="0">
<div class="top"><span>MENZA / CUSTOMER INSIGHTS</span><span>案例解读 · {i+1:02} / {len(shots):02}</span></div>
<div class="heading"><p class="eyebrow">{esc(seg['chapter'])}</p><h1>{title}</h1></div>
<div class="diagram {seg['layout']}">{cards}</div>
<div class="takeaway">{esc(seg['key'])}</div><div class="caption">{esc(seg['text'])}</div>
<div class="foot">访谈案例转述 · 未经独立审计 · 图形为解释性示意</div><div class="scene-progress" id="{sid}-progress"></div></section>''')
        for j in range(len(seg['labels'])):
            motion.append(f'tl.fromTo("#{sid}-card{j}",{{y:12}},{{y:0,duration:.5,ease:"power2.out"}},{start+j*.12});')
        motion.append(f'tl.fromTo("#{sid}-progress",{{scaleX:0}},{{scaleX:1,duration:{dur},ease:"none"}},{start});')
    css='''*{box-sizing:border-box;margin:0}body{font-family:system-ui,sans-serif}#root{position:relative;width:100%;height:100%;overflow:hidden}.scene{position:absolute;inset:0;padding:62px 82px;background:#f4f3ef;color:#142327}.dark{background:#102c32;color:#f4f3ef}.top{display:flex;justify-content:space-between;font-size:23px;letter-spacing:3px;color:#435d60}.dark .top{color:#b9cfcb}.heading{position:absolute;left:82px;top:157px}.eyebrow{font-size:27px;color:#216451;margin-bottom:22px;letter-spacing:2px}.dark .eyebrow{color:#d2e990}h1{font-size:74px;line-height:1.2;letter-spacing:-2px;font-weight:740}h1 span{display:block}.diagram{position:absolute;left:760px;right:82px;top:196px;display:flex;align-items:center;gap:16px}.card{width:306px;min-height:350px;background:#fff;border:2px solid #c4d4cb;padding:28px 25px}.dark .card{background:#20464b;border-color:#668b81}.number{font-size:57px;color:#216451;margin-bottom:36px;line-height:1}.dark .number{color:#d2e990}h2{font-size:33px;line-height:1.35;margin-bottom:23px;font-weight:680}.card p{font-size:26px;line-height:1.65;color:#435d60}.dark .card p{color:#d5dfd9}.arrow{font-size:34px;color:#216451}.dark .arrow{color:#d2e990}.compare .card{width:452px;min-height:350px}.takeaway{position:absolute;left:82px;right:82px;top:637px;border-top:2px solid #b9c8bf;padding-top:28px;font-size:38px;font-weight:650}.dark .takeaway{border-color:#668b81;color:#d2e990}.caption{position:absolute;left:82px;right:82px;top:775px;padding:25px 30px;font-size:35px;line-height:1.6;background:#e4e9e1;min-height:140px;color:#142327}.dark .caption{background:#20464b;color:#f4f3ef}.foot{position:absolute;left:82px;bottom:55px;font-size:23px;color:#435d60}.dark .foot{color:#b9cfcb}.scene-progress{position:absolute;bottom:0;left:0;width:100%;height:8px;background:#216451;transform-origin:left center}.dark .scene-progress{background:#d2e990}'''
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><script src="gsap.min.js"></script><style>{css}</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="1920" data-height="1080" data-fps="30">'+''.join(sections)+f'<audio id="narration" class="clip" src="assets/narration.wav" data-start="0" data-duration="{total}" data-track-index="1"></audio></div><script>const tl=gsap.timeline({{paused:true}});'+''.join(motion)+'window.__timelines["main"]=tl;</script></body></html>'


def produce(work,recipe,config,services,run_cmd,cancel,progress):
    validate_recipe(recipe)
    targets=config.get('targets',{})
    if (targets.get('width'),targets.get('height')) != (1920,1080):
        raise Blocked('当前文章模板支持1920×1080横版，请为竖版另行编排')
    def write(rel,data):
        atomic(work/rel,dumps(data) if isinstance(data,(dict,list)) else data)
    write('documents/SOURCE.md',recipe['source_text'])
    write('documents/video-recipe.json',recipe)
    write('documents/BRIEF.md',f"---\nworkflow: faceless-explainer\nflow: automation\nstoryboard: no\n---\n# {recipe['title']}\n\n{config.get('brief','')}\n\n{recipe['boundary']}\n\n仅自动制作，human_review=not_done。")
    write('documents/SCRIPT.md','# 脚本\n\n'+'\n\n'.join(f"## {s['id']} {s['title']}\n\n{s['text']}\n\n来源章节：{s['source_section']}" for s in recipe['segments']))
    write('documents/STORYBOARD.md','# 分镜\n\n'+'\n\n'.join(f"## {s['id']}\n\n{s['layout']}：{' → '.join(s['labels'])}\n\n信息目标：{s['key']}\n\n转场依据：对应旁白完成后衔接下一段，无额外固定留白。" for s in recipe['segments']))
    write('documents/DESIGN.md','# 视觉规范\n\n深青与暖白交替，黄绿色强调；横版1920×1080；标题74px，节点33px，字幕35px。\n图形为解释性示意；不用虚构数据或产品截图；真实片段边界驱动画面。')
    if recipe.get('visual_style')=='menza-case-study-v2':
        write('documents/REFERENCES.md',recipe['reference_plan'])
        write('documents/DESIGN.md','# 案例驱动视觉规范\n\n主参考3Blue1Brown：逐步显现对象与关系；辅助Linear：一致的节点与连接线。\n深青画布，青绿色表示记录与连接，琥珀色表示疑问与待验证。8镜采用包装对照、记录关联、假设分离、核查路径、证据分层、三问迁移。\n每镜三次解释性显现，贯穿连续旁白；不伪造产品界面与业务数字。\n具体参考映射见 REFERENCES.md。')
        write('documents/STORYBOARD.md',recipe['reference_plan'])
    write('documents/claims-map.json',{'claims':[{'id':s['id'],'source_section':s['source_section'],'text':s['text'],'status':'source_attributed_or_editorial_summary'} for s in recipe['segments']],'boundary':recipe['boundary']})
    write('documents/LESSON-PLAN.md','# 教学计划\n\n受众：品牌经营者及AI产品创作者。目标：能提出业务问题、数据依赖和行动负责人。\n方法：问题→两个访谈案例→可解释性→三问自检→参考答案。学习效果未验证。')
    write('documents/ANSWER-KEY.md','# 自检答案\n\n小样案例：判断赠品组合；关联订单、仓储履约和后续购买；营销团队调整后继续验证。\n迁移到自己的业务：三个问题各给出一个具体答案，不能仅回答“使用AI”。未开展学习者测试。')
    write('documents/assets-manifest.json',{'assets':[{'asset_id':'SOURCE','path':'documents/SOURCE.md','status':'available','sha256':digest(work/'documents/SOURCE.md'),'source':'用户上传Markdown'}]})
    progress('脚本、分镜和来源已归档；开始本地 Qwen 配音')
    shots=[]; records=[]; paths=[]; start=0
    for seg in recipe['segments']:
        if cancel(): raise Cancelled()
        sid=seg['id']; raw=work/'audio'/f'{sid}-raw.wav'; meta=raw.with_suffix('.json')
        request=work/'audio'/f'{sid}-request.json'
        prior_request=json.loads(request.read_text()) if request.is_file() else {}
        reusable_voice=prior_request.get('text')==seg['text'] and prior_request.get('voice')=='Serena' and prior_request.get('config')==services.get('qwen',{})
        write(str(request.relative_to(work)),{'kind':'tts','config':services.get('qwen',{}),'text':seg['text'],'voice':'Serena','style':'自然连贯、清晰的普通话讲解，正常语速','output':str(raw),'metadata':str(meta)})
        progress(f'本地 Qwen 配音 {sid} / {len(recipe["segments"])}')
        if not (reusable_voice and raw.is_file() and meta.is_file() and json.loads(meta.read_text()).get('sha256') == digest(raw)):
            run_cmd([sys.executable,'-m','adapters.service_job',str(request)],work/'qa'/f'{sid}-tts.log',cwd=ROOT,timeout=300)
        m=json.loads(meta.read_text()); duration=m['duration_s']
        log=run_cmd(['ffmpeg','-hide_banner','-i',raw,'-af','silencedetect=noise=-35dB:d=0.1','-f','null','-'],work/'qa'/f'{sid}-silence.log')
        ranges=[]; a=None
        for kind,value in re.findall(r'silence_(start|end): ([\d.]+)',log):
            if kind=='start':a=float(value)
            elif a is not None:ranges.append((a,float(value)));a=None
        head=next((b for a,b in ranges if a<.04),0)
        tail=next((a for a,b in reversed(ranges) if b>=duration-.005),duration)
        lo=max(0,head-.1); hi=min(duration,tail+.16)
        if hi-lo<.3:raise Blocked('合成声音过短，需要重新试听生成')
        kept=math.ceil((hi-lo)*30)/30; wav=work/'audio'/f'{sid}.wav'
        run_cmd(['ffmpeg','-y','-i',raw,'-af',f'atrim=start={lo}:end={hi},asetpts=PTS-STARTPTS,apad=whole_dur={kept}','-t',str(kept),'-ar','48000','-ac','2',wav],work/'qa'/f'{sid}-trim.log')
        # Preserve independent transcription evidence, without claiming word alignment.
        asr=work/'captions'/f'{sid}.asr.json'; req=work/'audio'/f'{sid}-asr-request.json'
        write(str(req.relative_to(work)),{'kind':'transcribe','config':services.get('alignment',{}),'input':str(wav),'output':str(asr)})
        if not (asr.is_file() and json.loads(asr.read_text()).get('source_sha256') == digest(wav)):
            run_cmd([sys.executable,'-m','adapters.service_job',req],work/'qa'/f'{sid}-asr.log',cwd=ROOT,timeout=300)
        shots.append({'shot_id':sid,'start_s':round(start,6),'duration_s':kept})
        records.append({**m,'segment_id':sid,'text':seg['text'],'trim_start_s':lo,'trim_end_s':hi,'final_sha256':digest(wav),'human_listening':'not_done'})
        paths.append(wav); start+=kept
    write('audio/concat.txt',''.join(f"file '{p.name}'\n" for p in paths))
    voice=work/'audio/narration.wav'
    run_cmd(['ffmpeg','-y','-f','concat','-safe','0','-i',work/'audio/concat.txt','-c','copy',voice],work/'qa/concat.log')
    def stamp(t):
        ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    write('captions/narration.srt','\n\n'.join(f"{i+1}\n{stamp(t['start_s'])} --> {stamp(t['start_s']+t['duration_s'])}\n{s['text']}" for i,(s,t) in enumerate(zip(recipe['segments'],shots)))+'\n')
    write('documents/timing.json',{'fps':30,'total_duration_s':round(start,6),'status':'auto_timed','human_review':'not_done','shots':shots,'alignment':'真实独立句段边界，非词级对齐'})
    write('documents/voice-config.json',{'provider':'local_qwen','requests':records,'human_listening':'not_done'})
    hf=work/'hyperframes';(hf/'assets').mkdir(exist_ok=True)
    gsap=ROOT/'workspace/service-tests/gsap.min.js'
    if not gsap.is_file():raise Blocked('缺少本地GSAP资源')
    shutil.copyfile(gsap,hf/'gsap.min.js');shutil.copyfile(voice,hf/'assets/narration.wav')
    page=build_html(recipe,shots,start)
    reuse_render=(hf/'index.html').is_file() and (hf/'index.html').read_text()==page
    atomic(hf/'index.html',page)
    write('qa/timing-check.json',check_timing(work/'documents/timing.json',hf/'index.html'))
    progress(f'配音完成，共{start:.2f}秒；检查画面与时间轴')
    run_cmd(hf_command('check',hf),work/'qa/hyperframes-check.log')
    progress('HyperFrames 检查通过；正在渲染整片')
    raw=work/'exports/render.mp4'
    if not (reuse_render and raw.is_file()):
        run_cmd(hf_command('render',hf,raw),work/'qa/render.log',timeout=3600)
    progress('画面渲染完成；执行双遍响度处理和最终验收')
    lufs=targets.get('lufs',-18);peak=min(targets.get('true_peak_db',-1.5)-.5,-2)
    log=run_cmd(['ffmpeg','-hide_banner','-i',raw,'-vn','-af',f'loudnorm=I={lufs}:TP={peak}:LRA=11:print_format=json','-f','null','-'],work/'qa/normalize-1.log')
    m=json.loads(re.search(r'\{\s*"input_i".*?\}',log,re.S).group())
    filt=f"loudnorm=I={lufs}:TP={peak}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
    final=work/'exports/article-video.mp4'
    run_cmd(['ffmpeg','-y','-i',raw,'-c:v','copy','-af',filt,'-ar','48000','-ac','2','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(round(start,6)),final],work/'qa/normalize-2.log')
    report=media_qa(final,work/'qa/final',targets|{'duration_s':start},run_cmd)
    if report['automated_status']!='pass':raise Blocked('成片技术验收未通过，见 qa/final/report.json')
    for i,t in enumerate(shots):
        run_cmd(['ffmpeg','-y','-ss',str(t['start_s']+min(1,t['duration_s']/2)),'-i',final,'-frames:v','1',work/'qa'/f'shot-{i+1:02}.jpg'],work/'qa'/f'shot-{i+1:02}.log')
    shutil.copyfile(work/'qa/shot-01.jpg',work/'exports/cover.jpg');shutil.copyfile(work/'captions/narration.srt',work/'exports/narration.srt')
    write('exports/delivery.json',{'title':recipe['title'],'video_sha256':digest(final),'source_sha256':digest(work/'documents/SOURCE.md'),'qa':'qa/final/report.json','human_review':'not_done','learning_effect':'not_verified','boundary':recipe['boundary']})
    write('exports/README.md',f"# {recipe['title']}\n\n自动制作完成，技术检查通过。人工试听与预览待确认；学习效果未验证。\n\n{recipe['boundary']}\n\n时长{start:.3f}秒；字幕为真实句段边界；无背景音乐。\n\n文件哈希：{digest(final)}")
    bundle=work/'exports/delivery.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for p in work.rglob('*'):
            if p.is_file() and p!=bundle and p.name!='render.mp4' and 'request' not in p.name:z.write(p,p.relative_to(work))
    progress('技术检查通过；成片和交付包已生成，等待人工确认')
    return [str(p.relative_to(work)) for part in ['qa','exports'] for p in (work/part).rglob('*') if p.is_file() and p.name!='render.mp4']
