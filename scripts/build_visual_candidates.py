"""Prepare isolated SH03 visual alternatives; never approve or replace the full film."""
from pathlib import Path
import json, shutil, hashlib
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'workspace/projects/c96ef29387e84eb7809374b6d8c541be'
DEST=P/'assets/visual-20260918'
SOURCE=P/'hyperframes/vendor/gsap.min.js'
AUDIO=P/'audio/processed/SEG03.wav'
BASE='''<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><title>SH03 视觉候选</title><script src="vendor/gsap.min.js"></script><style>
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%}body{font-family:system-ui,sans-serif;color:var(--ink);background:var(--bg)}
:root{TOKENS}#visual{position:relative;width:100%;height:100%;overflow:hidden;background:var(--bg)}.scene{position:absolute;inset:0}p,h1{margin:0}
.eyebrow{position:absolute;left:112px;top:68px;font-size:30px;line-height:44px;letter-spacing:3px;color:var(--muted)}h1{position:absolute;left:112px;top:136px;width:1696px;font-size:76px;line-height:98px;font-weight:650;letter-spacing:-2px}
.rule{position:absolute;left:112px;top:274px;width:1696px;height:2px;background:var(--line)}.section{position:absolute;left:112px;top:304px;color:var(--muted);font-size:28px;line-height:42px}
.node{position:absolute;background:var(--surface);border:2px solid var(--line);border-radius:RADIUSpx;width:310px;height:126px;padding:24px 30px;font-size:38px;line-height:48px}.small{display:block;font-size:25px;line-height:34px;color:var(--muted)}
#old{left:112px;top:402px}#report{left:552px;top:402px;border-color:var(--warn);color:var(--warn)}#current{left:332px;top:642px;width:330px;border:3px solid var(--accent);color:var(--accent)}
#current .small{color:var(--ink)}.links{position:absolute;inset:0;width:100%;height:100%}.wrong{color:var(--warn);position:absolute;left:678px;top:571px;font-size:30px;line-height:42px}
.split{position:absolute;left:942px;top:350px;width:2px;height:440px;background:var(--line)}.quote{position:absolute;left:1010px;top:378px;width:798px;font-size:54px;line-height:82px;font-weight:500}.quote span{display:block}.key{color:var(--accent)}.source{position:absolute;left:1010px;top:682px;width:798px;font-size:27px;line-height:43px;color:var(--muted)}.source span{display:block}
.caption{position:absolute;left:112px;top:878px;width:1696px;text-align:center;font-size:38px;line-height:55px;color:var(--ink)}.caption span{display:block}.footer{position:absolute;left:112px;top:1005px;font-size:23px;line-height:32px;color:var(--muted)}
</style></head><body><div id="visual" data-composition-id="visual" data-width="1920" data-height="1080" data-start="0" data-duration="7.2">
<section class="scene clip" id="SH03" data-shot-id="SH03" data-start="0" data-duration="7.2" data-track-index="0">
<p class="eyebrow">VERSION / EVIDENCE</p><h1>旧报告，不能证明新版本</h1><div class="rule"></div><p class="section">01　先看清，报告属于哪一版</p>
<svg class="links" viewBox="0 0 1920 1080" aria-hidden="true"><path d="M552 465 H422 M436 454 L422 465 L436 476" fill="none" stroke="WARN" stroke-width="4"/><g id="mismatch"><path d="M707 528 V596 H497 V642" fill="none" stroke="WARN" stroke-width="4" stroke-dasharray="10 8"/></g></svg>
<div id="old" class="node">旧版视频<span class="small">历史文件</span></div><div id="report" class="node">旧报告<span class="small">对应旧版视频</span></div><p id="wrong" class="wrong">× 不能沿用</p><div id="current" class="node">当前版本<span class="small">需重新核对</span></div>
<div class="split"></div><div class="quote"><span>文件变化以后，</span><span class="key">旧报告不能继续作为</span><span class="key">新版本的证明。</span></div>
<p class="source"><span>原文摘录 · 作者陈述</span><span>《我用 Codex 搭了一个视频工作台》</span><span>／验收必须对应具体文件</span></p>
<div class="caption"><span>文章写得很明确：文件变了，旧报告就不能证明新版本。</span><span>检查要对应最终文件。</span></div><p class="footer">关系示意 · 据作者文章，未独立核验产品能力</p></section>
<audio id="voice" class="clip" src="voice.wav" data-start="0" data-duration="6.977083333333334" data-track-index="2" data-volume="1"></audio>
</div><script>const tl=gsap.timeline({paused:true});tl.fromTo('#current',{y:24,opacity:0},{y:0,opacity:1,duration:.55,ease:'power2.out'},0);tl.fromTo('#wrong',{scale:.94},{scale:1,duration:.25,ease:'power2.out',transformOrigin:'50% 50%'},.55);tl.fromTo('#mismatch,#wrong',{opacity:1},{opacity:0,duration:.45,ease:'none'},1.2);tl.fromTo('.key',{opacity:.65},{opacity:1,duration:.4,ease:'none'},1.65);window.__timelines=window.__timelines||{};window.__timelines.visual=tl;</script></body></html>'''
def main():
 DEST.mkdir(parents=True,exist_ok=True)
 candidates=[]
 variants=[('light-v1','浅色编辑式',{'bg':'#F7F8FC','surface':'#FFFFFF','ink':'#202433','muted':'#626B7F','accent':'#6258E8','warn':'#A85C08','line':'#A9B1C0'},4,'data-chart','7 / 10秒：纸白背景、信息依次出现、稳定留白'),('dark-v1','中性深色式',{'bg':'#181C25','surface':'#232937','ink':'#F3F5FA','muted':'#B5BDCE','accent':'#B6A5FF','warn':'#F2B76C','line':'#79859D'},16,'ui-3d-reveal','4 / 7秒：中性深色承托主体、层级聚焦；不借用Figma品牌或倾斜界面')]
 for cid,name,colors,radius,ref,point in variants:
  folder=DEST/cid;(folder/'vendor').mkdir(parents=True,exist_ok=True)
  shutil.copyfile(SOURCE,folder/'vendor/gsap.min.js');shutil.copyfile(AUDIO,folder/'voice.wav')
  reference=DEST/f'{ref}-reference.jpg';shutil.copyfile(ROOT/f'references/hyperframes-showcases/{ref}-frames/contact-sheet.jpg',reference)
  tokens=';'.join('--'+k+':'+v for k,v in colors.items())
  (folder/'index.html').write_text(BASE.replace('TOKENS',tokens).replace('RADIUS',str(radius)).replace('WARN',colors['warn']))
  design=P/f'documents/visual/{cid}.md';design.parent.mkdir(parents=True,exist_ok=True)
  design.write_text(f'# {name} · 待用户选择\n\n参考：{ref}，{point}。已查看本地组件连续采样图，未听辨参考音轨。\n\n本次色值为设计推导，不声称是案例采样值。背景约75%、文字和结构约20%、强调与注意色约5%；实际随镜头变化。\n\n'+ '\n'.join(f'- {k}: `{v}`' for k,v in colors.items())+'\n\n1920×1080；112px水平安全区；76px标题、54px引用、38px字幕。旧报告与旧视频的线持续保留，错误新版本连线在1.2–1.65秒消失，之后稳定读图。保持原文归因，不制作假UI或捏造通过标记。\n\n整片沿同一当前版本对象延续四镜，不机械重复本镜布局。此小样7.2秒，复用既有SEG03音频；正式整片仍用原锁定时间表。视觉确认以平台为准。\n')
  relative=lambda p:str(p.relative_to(P))
  candidates.append({'id':cid,'name':name,'description':'暖白底、深灰正文、蓝紫当前版本；以原文证据为重心。' if cid.startswith('light') else '中性深灰底、浅紫当前版本、琥珀历史报告；以对象聚焦为重心。','reference':f'{ref} {point}；配色为本次设计推导','design_path':relative(design),'sample_path':relative(folder/'sample.mp4'),'evidence_paths':[relative(folder/'index.html'),relative(folder/'voice.wav'),relative(folder/'vendor/gsap.min.js'),relative(reference)]})
 (DEST/'plan-draft.json').write_text(json.dumps({'candidates':candidates},ensure_ascii=False,indent=2))
 print(DEST)
if __name__=='__main__':main()
