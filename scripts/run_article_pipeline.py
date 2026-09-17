"""Explicitly delegated article production. No human Review rows are manufactured.
Usage: python scripts/run_article_pipeline.py recipes/article-second-line/recipe.json
Repeat resumes matching recipe/audio; a changed recipe creates a separate version.
"""
import sys, json, shutil, math, html, hashlib, re, zipfile, subprocess, fcntl
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.server.core import Store, ROOT, atomic, dumps, digest, uid, now
from adapters.tools import qwen_synthesize, transcribe, process, hf_command, media_qa
from adapters.timing import check_timing


def input_fingerprint(recipe_path):
    recipe_path = Path(recipe_path)
    recipe = json.loads(recipe_path.read_text())
    source = Path(recipe['source'])
    h = hashlib.sha256(recipe_path.read_bytes() + source.read_bytes())
    for image in sorted((source.parent / 'images').iterdir()):
        if image.is_file():
            h.update(image.name.encode())
            h.update(bytes.fromhex(digest(image)))
    h.update(Path(__file__).read_bytes())
    return h.hexdigest()


def run(recipe_path):
    recipe_path = Path(recipe_path).resolve()
    recipe = json.loads(recipe_path.read_text())
    source = Path(recipe['source'])
    fingerprint = input_fingerprint(recipe_path)
    state_path = ROOT / 'workspace/article-runs' / (fingerprint + '.json')
    store = Store()
    # A separate lock prevents concurrent copies of this CLI; the platform Worker
    # remains authoritative for queued tasks. Refuse while a production task is active.
    lock = (store.home / 'article-pipeline.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if store.rows("SELECT id FROM runs WHERE status IN ('queued','running')"):
        raise RuntimeError('请先等待平台活动任务完成')
    if state_path.exists():
        pid = json.loads(state_path.read_text())['project_id']
    else:
        project = store.create(recipe['name'], recipe['branch'], {
            'brief':'公众号文章自动改编；假设场地与概念研究；无发布授权。',
            'audio_mode':'qwen', 'variants':['horizontal'],
            'execution_mode':'delegated_automation',
            'authorization':'用户要求将目录下一篇公众号文章通过自动化方式完整跑完流程',
            'targets':{'width':1920,'height':1080,'fps':30,'video_codec':'h264','audio_codec':'aac','sample_rate':48000,'channels':2,'lufs':-18,'lufs_tolerance':0.5,'true_peak_db':-1.5}})
        pid = project['id']
        atomic(state_path, dumps({'project_id':pid,'fingerprint':fingerprint}))
    root = store.root(pid)
    work = root / 'runs/article-v1/work'
    for part in ['documents','assets','audio','captions','hyperframes','qa','exports']:
        (work/part).mkdir(parents=True,exist_ok=True)
    def write(path, value):
        atomic(work/path, dumps(value) if isinstance(value,(dict,list)) else value)
    def event(stage,status,details=''):
        with store.conn() as c:
            store.event(c,pid,None,'automation.stage',{'stage':stage,'status':status,'details':details,'actor':'codex_automation','human_review':'not_done'})
        print(stage,status,details,flush=True)
    def cmd(args, log):
        return process(args,work,Path(log))
    print('PROJECT',pid,str(work),flush=True)
    shutil.copyfile(source,work/'documents/SOURCE.md')
    shutil.copyfile(recipe_path,work/'documents/recipe.json')
    manifest=[]
    for f in sorted((source.parent/'images').iterdir()):
        if f.is_file():
            shutil.copyfile(f,work/'assets'/f.name)
            manifest.append({'asset_id':f.stem,'path':'assets/'+f.name,'source':str(f),'sha256':digest(f),'type':'author_supplied_concept_illustration'})
    write('documents/assets-manifest.json',{'source_sha256':digest(source),'assets':manifest})
    write('documents/BRIEF.md',f'''---
workflow: general-video
flow: automation
storyboard: no
---
# {recipe['name']}

受众：使用 AI 做设计表达的创作者。目标：能区分氛围图与可核对的设计依据。
类型：教学案例讲解；1920×1080，30fps；约 100–150 秒，按真实配音调整。
素材：公众号原文与其六张图，仅说明原文的假设方案，不主张建成事实。
工具：本地 Qwen；HyperFrames 0.8.46；FFmpeg。
声音：现有服务报告的声线；无背景音乐，保证教学清晰度。
响度：-18 LUFS ±0.5，真峰值不高于 -1.5 dBTP；48kHz 双声道 AAC。
授权：本轮用户要求自动完整跑通；脚本、声画选择由 Codex 代执行。
人工确认：未执行。自动化交付与人工验收分别记录；不发布。
''')
    write('documents/claims-map.json',{'source':'SOURCE.md','claims':[{'id':s['id'],'source_section':s['source_section'],'claim':s['text'],'status':'teaching_adaptation' if '教学' in s['source_section'] else 'source_attributed_concept','asset':s['image']} for s in recipe['segments']]})
    event('brief','completed','源文和素材按哈希归档；假设边界保留')
    write('documents/SCRIPT.md','# 旁白与屏幕文字\n\n'+'\n\n'.join(f"## {s['id']} {s['title'].replace(chr(10),'')}\n\n屏幕：{s['key']}\n\n旁白：{s['text']}\n\n来源：{s['source_section']}" for s in recipe['segments']))
    write('documents/LESSON-PLAN.md','# 教学计划\n\n承诺：学会用原始图、总平面与剖面追问设计依据。\n前置：能区分效果图和平剖面；不需要建筑软件操作经验。\n结构：问题→案例返工→方法→边界→暂停自检→答案。\n本片是案例判断教程，不是施工教程。学习效果未验证。\n')
    write('documents/PRACTICE.md','# 迁移练习\n\n找一份不同的 AI 改造概念图，不使用本片案例。\n1. 说出两个无法仅凭终稿判断的问题。\n2. 列出所需原始依据及平面/剖面各一项。\n3. 标注仍需专业核验的一项风险。\n')
    write('documents/ANSWER-KEY.md','# 评分参考\n\n共三项，每项 1 分：\n- 原始图与终稿对应，可辨认保留与改变。\n- 平面验证连续路线，剖面验证高差/进入建筑/落地关系，至少说对一项。\n- 不把概念图当施工依据，指出结构、消防、防洪等待核验问题之一。\n达到 3 项说明完成本练习；不能据此宣称具备专业设计资质。未安排学习者实测。\n')
    event('content','completed','改编脚本与练习答案就绪；自动内容审查')
    write('documents/DESIGN.md','# 视觉规范\n\n暖白纸面 #F2EFE8、炭黑 #242821、砖红 #A43B20。1920×1080。\n左侧 570px 为标题与判断，右侧展示原文图片。大图保留全部图幅、不裁掉图纸关键关系。\n标题 80px、要点 34px、句段字幕 34px；底部保留 72px。\n图像保持原始色彩，经实图检查无需额外调色。轻微文字位移动画；硬切换景，不以转场掩盖关系。\n每镜固定显示“假设场地 / 概念研究”。系统中文字体；GSAP 本地文件，无网络渲染依赖。\n')
    write('documents/STORYBOARD.md','# 分镜\n\n'+'\n\n'.join(f"## {s['id']}\n- 注意点：{s['key']}\n- 画面：{s['image']}，完整呈现\n- 动作：标题从左进入，图片框稳定，重点文字随后出现\n- 转场原因：{s['chapter']}推进教学逻辑\n- 声音：对应 SCRIPT 的同编号段落\n- 时间：以实测音频时长定时，不统一增加空白；只在配方明确要求时停留\n" for s in recipe['segments']))
    event('storyboard','completed')
    # Each paragraph is independently generated. Caption windows are real clip bounds,
    # not fabricated word-level alignment.
    records=[]
    for s in recipe['segments']:
        wav=work/'audio'/f"{s['id']}.wav"; meta=wav.with_suffix('.json')
        if not meta.exists():
            event('timing','running','Qwen '+s['id'])
            m=qwen_synthesize({},s['text'],'Serena','自然清晰的普通话教学解说',wav)
            atomic(meta,dumps({**m,'text':s['text'],'human_listening':'not_done'}))
        m=json.loads(meta.read_text())
        if m['text']!=s['text'] or m['sha256']!=digest(wav):
            raise ValueError('音频缓存与脚本/哈希不一致')
        asr=work/'captions'/f"{s['id']}.asr.json"
        if not asr.exists():
            transcribe({},wav,asr)
        records.append(m)
    # Frame-grid aligned timing, including explicit pause/self-check hold.
    shots=[]; start=0; captions=[]
    for s,m in zip(recipe['segments'],records):
        duration=math.ceil((m['duration_s']+s.get('hold_s',0))*30)/30
        shots.append({'shot_id':s['id'],'start_s':round(start,6),'duration_s':round(duration,6)})
        captions.append({'id':s['id'],'start_s':round(start,6),'duration_s':m['duration_s'],'text':s['text'],'method':'independent_utterance_clip_bounds'})
        start+=duration
    timing={'fps':30,'total_duration_s':round(start,6),'status':'auto_timed','human_review':'not_done','shots':shots,'captions':captions}
    write('documents/timing.json',timing)
    write('documents/voice-config.json',{'provider':'local_qwen','requests':records,'alignment':'真实独立句段音频边界；非词级时间戳','listening':'not_done'})
    def stamp(t):
        ms=round(t*1000); return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    srt='\n\n'.join(f"{i+1}\n{stamp(c['start_s'])} --> {stamp(c['start_s']+c['duration_s'])}\n{c['text']}" for i,c in enumerate(captions))+'\n'
    write('captions/narration.srt',srt)
    event('timing','completed',f'{start:.3f}s，真实句段边界，ASR记录保留')
    h=work/'hyperframes'; (h/'assets').mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'workspace/service-tests/gsap.min.js',h/'gsap.min.js')
    for f in (work/'assets').iterdir(): shutil.copyfile(f,h/'assets'/f.name)
    for f in (work/'audio').glob('*.wav'): shutil.copyfile(f,h/'assets'/f.name)
    sections=[]; animations=[]; tracks=[]
    for i,(s,t,m) in enumerate(zip(recipe['segments'],shots,records)):
        sid=s['id']; st=t['start_s']; d=t['duration_s']
        title=''.join('<span>'+html.escape(x)+'</span>' for x in s['title'].split('\n'))
        sections.append(f'''<section class="scene clip" id="{sid}" data-shot-id="{sid}" data-start="{st}" data-duration="{d}" data-track-index="0">
<div class="rail"><div class="brand">AI 这个时代 <b> / 设计案例</b></div><p class="chapter">{html.escape(s['chapter'])}</p><h1 id="title{i}">{title}</h1><div class="rule"></div><p class="key" id="key{i}">{html.escape(s['key'])}</p><p class="index">{i+1:02}<span> / {len(shots):02}</span></p></div>
<div class="visual"><img src="assets/{s['image']}"/><p class="note">原文概念图 · {html.escape(s['source_section'])}</p></div>
<div class="subtitle">{html.escape(s['text'])}</div><div class="boundary">假设场地 / 概念研究 · 不作为施工依据</div>
</section>''')
        animations.append(f'tl.fromTo("#title{i}",{{x:-24}},{{x:0,duration:.65,ease:"power3.out"}},{st});tl.fromTo("#key{i}",{{y:14}},{{y:0,duration:.7,ease:"power2.out"}},{st+.2});')
        tracks.append(f'<audio id="voice{i}" class="clip" src="assets/{sid}.wav" data-start="{st}" data-duration="{m["duration_s"]}" data-track-index="1"></audio>')
    css='''*{box-sizing:border-box;margin:0}body{font-family:system-ui,sans-serif;background:#f2efe8;color:#242821}#root{width:100%;height:100%;position:relative;overflow:hidden}.scene{position:absolute;inset:0;background:#f2efe8}.rail{position:absolute;left:78px;top:68px;width:500px;height:770px}.brand{font-size:25px;letter-spacing:2px}.brand b{font-weight:400;color:#655c50}.chapter{font-size:25px;color:#a43b20;margin-top:102px;letter-spacing:2px}h1{font-size:80px;line-height:1.26;font-weight:760;margin-top:26px;letter-spacing:-2px}h1 span{display:block}.rule{width:88px;height:7px;background:#a43b20;margin-top:40px}.key{font-size:33px;line-height:1.55;margin-top:27px;max-width:490px}.index{position:absolute;bottom:0;font-size:52px;color:#a43b20}.index span{font-size:25px;color:#655c50}.visual{position:absolute;left:632px;top:146px;width:1210px;height:680px;background:#e5e1d8;overflow:hidden}.visual img{width:100%;height:620px;object-fit:contain}.note{position:absolute;bottom:15px;left:25px;font-size:24px;color:#4c463d}.subtitle{position:absolute;left:78px;right:78px;top:870px;min-height:104px;padding:19px 28px;border-top:2px solid #bbb2a2;font-size:34px;line-height:1.5;background:#f2efe8}.boundary{position:absolute;bottom:35px;left:78px;font-size:24px;color:#655c50}'''
    page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><script src="gsap.min.js"></script><style>{css}</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="{start}" data-width="1920" data-height="1080" data-fps="30">{''.join(sections+tracks)}</div><script>const tl=gsap.timeline({{paused:true}});{''.join(animations)}window.__timelines["main"]=tl;</script></body></html>'''
    atomic(h/'index.html',page)
    write('qa/timing-check.json',check_timing(work/'documents/timing.json',h/'index.html'))
    cmd(hf_command('check',h),work/'qa/hyperframes-check.log')
    event('sample','completed','全片逐场景运行时、布局、动效和对比度检查；不冒充人工确认')
    raw=work/'exports/render.mp4'
    if not raw.exists(): cmd(hf_command('render',h,raw),work/'qa/render.log')
    event('preview','completed','完整 HyperFrames 画面与原始配音已渲染')
    # Two-pass loudness normalization after final frame rendering.
    final=work/'exports/second-production-line.mp4'
    if not final.exists():
        log=cmd(['ffmpeg','-hide_banner','-i',raw,'-vn','-af','loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-'],work/'qa/normalize-pass1.log')
        m=json.loads(re.search(r'\{\s*"input_i".*?\}',log,re.S).group())
        filt=f"loudnorm=I=-18:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=json"
        cmd(['ffmpeg','-y','-i',raw,'-c:v','copy','-af',filt,'-ar','48000','-ac','2','-c:a','aac','-b:a','192k','-movflags','+faststart',final],work/'qa/normalize-pass2.log')
    targets=store.project(pid)['config']['targets']|{'duration_s':timing['total_duration_s']}
    report=media_qa(final,work/'qa/final',targets,cmd)
    if report['automated_status']!='pass': raise RuntimeError('最终技术 QA 未通过')
    event('render','completed',f"最终技术 QA 通过 SHA256 {digest(final)}")
    for i,t in enumerate(shots):
        cmd(['ffmpeg','-y','-ss',str(t['start_s']+min(2,t['duration_s']/2)),'-i',final,'-frames:v','1',work/'qa'/f'shot-{i+1:02}.jpg'],work/'qa'/f'shot-{i+1:02}.log')
    shutil.copyfile(work/'qa/shot-01.jpg',work/'exports/cover.jpg')
    shutil.copyfile(work/'captions/narration.srt',work/'exports/narration.srt')
    write('exports/README.md',f'''# {recipe['name']}

自动制作交付：源文→教学改编→分镜→本地Qwen→句段字幕→HyperFrames→双遍响度处理→最终QA→打包。
成片：{report['actual']['duration_s']:.3f} 秒，1920×1080，30fps；SHA256 `{digest(final)}`。
响度：{report['loudness']['input_i']} LUFS，真峰值 {report['loudness']['input_tp']} dBTP。
原文为假设场地概念研究，视频沿用该边界。教学新增问题/答案为改编归纳。
字幕为真实分段音频边界，非词级强制对齐。保留独立ASR原始结果供检查。
人类试听与完整预览确认：未执行；学习效果：未验证；未公开发布。
在平台查看本项目的“产物”；本次为独立自动化脚本运行，未伪造八阶段人工审批记录。
重跑：在平台源码目录运行 `.venv/bin/python scripts/run_article_pipeline.py recipes/article-second-line/recipe.json`。
修改脚本会建立新项目版本；同配方复用音频前核对文本与哈希。\n''')
    write('documents/RETROSPECTIVE.md','# 复盘\n\n本轮建立了真实源文、素材、声音、时间、工程和最终QA的对应关系。\n适用：有完整图文素材的公众号案例讲解。\n限制：句段级字幕，不提供字词级跟随高亮；人工试听和学习迁移效果未验证。\n公开发布须另行授权；新内容必须先产生新的审阅配方，不自动把任意文章套为本案例。\n')
    write('exports/delivery.json',{'project_id':pid,'execution':'delegated_automation','recipe_sha256':fingerprint,'source_sha256':digest(source),'video_sha256':digest(final),'qa':'qa/final/report.json','human_review':'not_done','learning_effect':'not_verified','files':{str(f.relative_to(work)):digest(f) for folder in ['documents','assets','audio','captions','hyperframes','qa','exports'] for f in (work/folder).rglob('*') if f.is_file() and f.suffix not in ['.log','.mp4','.zip']}})
    bundle=work/'exports/delivery.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for f in work.rglob('*'):
            if f.is_file() and f!=bundle and f.name!='render.mp4': z.write(f,f.relative_to(work))
    for part in ['documents','assets','audio','captions','hyperframes']:
        shutil.copytree(work/part,root/part,dirs_exist_ok=True)
    store.scan(pid)
    with store.conn() as c:
        for f in work.rglob('*'):
            if f.is_file() and f.suffix in ['.mp4','.zip','.jpg','.srt','.json','.md']:
                rel=str(f.relative_to(root)); sha=digest(f)
                if not c.execute('SELECT 1 FROM artifacts WHERE project_id=? AND path=? AND sha256=?',(pid,rel,sha)).fetchone():
                    c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uid(),pid,None,rel,sha,'automated_delivery',now()))
    event('delivery','completed','成片、封面、字幕、工程、练习答案与QA已打包；人工验收待做')
    store.export_status(pid)
    atomic(state_path,dumps({'project_id':pid,'fingerprint':fingerprint,'final':str(final),'bundle':str(bundle),'automated_status':'pass','human_review':'not_done'}))
    print('FINAL',final,flush=True)

if __name__=='__main__':
    run(sys.argv[1])
