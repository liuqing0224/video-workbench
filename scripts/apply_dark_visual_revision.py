"""Apply the explicitly selected dark candidate without changing narration/timing."""
from pathlib import Path
import re,shutil,json
from apps.server.core import Store,digest
from apps.server.visual import require_approved
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'workspace/projects/c96ef29387e84eb7809374b6d8c541be'
s=Store();selection=require_approved(s,P.name)
assert selection['approved']=='dark-v1','This revision needs the actual dark-v1 user selection'
archive=P/'qa/visual-dark-v2';archive.mkdir(exist_ok=True)
source=P/'hyperframes/index.html';backup=archive/'previous-index.html'
if not backup.exists():shutil.copyfile(source,backup)
html=backup.read_text()
locked={str(p.relative_to(P)):digest(p) for p in [P/'documents/SCRIPT.md',P/'documents/timing.json',P/'audio/narration.wav',P/'captions/narration.srt'] if p.exists()}
colors={'#102B25':'#181C25','#1B3B32':'#232937','#F3EEDC':'#F3F5FA','#B9C8BB':'#B5BDCE','#D2F86A':'#B6A5FF','#E9A064':'#F2B76C','rgba(210,248,106,0.08)':'rgba(182,165,255,0.08)','rgba(210,248,106,0)':'rgba(182,165,255,0)'}
for old,new in colors.items():html=html.replace(old,new)
sample=(P/'assets/visual-20260918/dark-v1/index.html').read_text()
section=re.search(r'<section[^>]*>(.*?)</section>',sample,re.S).group(1)
# Keep the full-film shared current-version object and caption track.
section=re.sub(r'<div id="current".*?</div>','',section,flags=re.S)
section=re.sub(r'<div class="caption">.*?</div>','',section,flags=re.S)
# Unique sample selectors, scoped to SH03 to keep unrelated scenes intact.
section=section.replace('id="old"','id="s3-old"').replace('id="report"','id="s3-report"').replace('id="mismatch"','id="s3-mismatch"').replace('id="wrong"','id="s3-wrong"')
html=re.sub(r'(<section id="SH03"[^>]*>).*?</section>',lambda m:m.group(1)+section+'</section>',html,flags=re.S)
# Reuse typography, panel and quote specifications from selected sample.
css=re.search(r'<style>(.*?)</style>',sample,re.S).group(1)
# Only scope visual selectors; global canvas reset/token declaration are handled separately.
parts=[]
for selectors,body in re.findall(r'([^{}]+)\{([^{}]*)\}',css):
 selectors=selectors.strip()
 if selectors==':root':parts.append(':root{'+body+'}');continue
 if selectors in ('*','html,body','body','#visual','.scene','p,h1'):continue
 if selectors.startswith('#current') or selectors=='.caption' or selectors=='.caption span':continue
 selectors=selectors.replace('#old','#s3-old').replace('#report','#s3-report')
 parts.append(','.join('#SH03 '+x.strip() for x in selectors.split(','))+'{'+body+'}')
extra='''
h1{left:112px;top:136px;width:1696px;height:98px;font-size:76px;line-height:98px;font-weight:650;letter-spacing:-2px}
.node{border-width:2px;border-radius:16px}.current{border-width:3px}.fold{display:none}
.diagram-label,.limit{top:70px;font-size:27px}.diagram-label{left:112px}.limit{left:1160px;width:648px}
.open-node{border-bottom-width:2px}.caption{left:112px;top:878px;width:1696px;font-size:38px;line-height:55px}
#SH03 .node{display:block;align-items:initial;justify-content:initial}#SH03 .quote{height:auto}
#SH03 .source{height:auto}.current .sub{font-size:25px;line-height:34px;margin-top:0}
#current-version{font-size:38px;line-height:48px;padding:24px 30px}
'''
html=html.replace('</style>','\n'+'\n'.join(parts)+extra+'</style>')
# Replace old SH03-only motion with the selected candidate timings.
html='\n'.join(line for line in html.splitlines() if not (line.startswith('tl.') and any(x in line for x in ['#mismatch-cross','#mismatch-line','#quote-key'])))
insert='''
tl.set('.diagram-label,.limit',{opacity:0},14.3);
tl.set('.diagram-label,.limit',{opacity:1},21.266666666666666);
tl.to('#current-version',{x:172,y:282,width:330,height:126,duration:.55,ease:'power2.out'},14.3);
tl.fromTo('#s3-wrong',{scale:.94},{scale:1,duration:.25,ease:'power2.out',transformOrigin:'50% 50%'},14.85);
tl.fromTo('#s3-mismatch,#s3-wrong',{opacity:1},{opacity:0,duration:.45,ease:'none'},15.5);
tl.fromTo('#SH03 .key',{opacity:.65},{opacity:1,duration:.4,ease:'none'},15.95);
'''
html=html.replace("tl.to('#current-version',{x:640",insert+"tl.to('#current-version',{width:320,height:180,x:640")
source.write_text(html)
assert all(digest(P/path)==sha for path,sha in locked.items())
(archive/'revision.json').write_text(json.dumps({'selection':selection['approved'],'locked_inputs':locked,'previous_engine':digest(backup),'updated_engine':digest(source),'status':'awaiting_render'},ensure_ascii=False,indent=2))
print(source)
