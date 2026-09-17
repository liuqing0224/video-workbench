"""Case-led Menza concept film. Fixed illustrations, never fabricated product UI."""
import html

def build_case_film(recipe, shots, total):
    e=html.escape
    def text(x,y,s,size=38,color='#eeeae0',anchor='start'):
        return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{e(s)}</text>'
    def line(x1,y1,x2,y2,color='#77d9c0',dash=False):
        return f'<path class="trace" d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="5" fill="none"'+(' stroke-dasharray="12 12"' if dash else '')+'/>'
    def circle(x,y,r=13,color='#77d9c0'):
        return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'
    def group(n,s):return f'<g class="beat b{n}">{s}</g>'
    def bottle(x,y):
        return f'<g transform="translate({x} {y})"><rect x="52" y="0" width="116" height="56" rx="10" fill="#ddd3b9"/><rect x="22" y="55" width="176" height="230" rx="30" fill="#243d40" stroke="#77d9c0" stroke-width="5"/>'+text(110,160,'SERUM',30,anchor='middle')+text(110,208,'完整体验',25,'#77d9c0','middle')+'</g>'
    def sachet(x,y):
        return f'<g transform="translate({x} {y})"><path d="M0 0H180L167 245H13Z" fill="#323434" stroke="#e8bd72" stroke-width="5"/>'+line(12,25,168,25,'#e8bd72')+text(90,124,'SAMPLE',27,anchor='middle')+text(90,165,'试用包装',24,'#e8bd72','middle')+'</g>'
    def row(x,y,label,value,color='#77d9c0'):
        return line(x,y+18,x+620,y+18,'#344b50')+text(x,y,label,30,'#a5b9b9')+text(x+265,y,value,34,color)
    def source(x,y,name,rows):
        return text(x,y,name,36,'#77d9c0')+''.join(row(x,y+75+i*72,k,v) for i,(k,v) in enumerate(rows))
    # Beats reveal the explanation, instead of exposing a complete slide at once.
    diagrams=[]
    diagrams.append(group(0,bottle(360,320)+text(470,675,'畅销正装',41,anchor='middle'))+group(1,line(660,470,1190,470)+text(925,430,'也适合获客？',40,'#e8bd72','middle')+sachet(1270,345)+text(1360,675,'免费小样',41,anchor='middle'))+group(2,text(960,757,'配方相同 ≠ 体验相同',46,'#e8bd72','middle')))
    diagrams.append(group(0,source(150,322,'订单系统',[('客户','同一位顾客'),('赠品','免费小样')]))+group(1,source(1120,322,'仓储履约',[('客户','同一位顾客'),('产品','眼部精华小样')])+line(795,390,1060,390)+circle(920,390))+group(2,line(460,547,460,650)+line(1430,547,1430,650)+line(460,650,1430,650)+circle(960,650)+text(960,731,'关联后，才能追踪后续购买',44,'#77d9c0','middle')))
    diagrams.append(group(0,bottle(250,340)+text(360,695,'正装畅销',38,anchor='middle'))+group(1,sachet(840,360)+text(930,695,'小样表现不理想',38,'#e8bd72','middle')+text(650,485,'≠',110,'#e8bd72','middle'))+group(2,line(1060,485,1300,485,'#e8bd72',True)+text(1460,439,'包装 / 使用方式',36,anchor='middle')+text(1460,505,'体验缺失？',52,'#e8bd72','middle')+text(1460,568,'解释假设 · 尚待验证',28,'#a5b9b9','middle')))
    diagrams.append(group(0,text(300,370,'菜单',45,'#77d9c0','middle')+text(300,448,'品类与组合',31,anchor='middle')+text(790,370,'产品记录',45,'#77d9c0','middle')+text(790,448,'实际销售内容',31,anchor='middle'))+group(1,line(430,401,620,401)+line(960,401,1150,401)+text(1450,370,'财务记录',45,'#77d9c0','middle')+text(1450,448,'已申报与已缴款项',31,anchor='middle'))+group(2,line(1450,502,1450,623)+line(1450,623,660,623,'#e8bd72')+circle(660,623,15,'#e8bd72')+text(610,639,'可能多缴？',58,'#e8bd72','end')+text(960,749,'数据给出线索，不能直接代替税务判断',39,'#a5b9b9','middle')))
    diagrams.append(group(0,text(290,480,'异常线索',52,'#e8bd72','middle')+circle(290,540,16,'#e8bd72'))+group(1,line(310,540,960,540)+text(960,424,'财务 / 专业人员',45,anchor='middle')+text(960,485,'核对原始记录',34,'#77d9c0','middle')+circle(960,540,19))+group(2,line(980,540,1600,540)+text(1600,450,'采取行动',49,anchor='middle')+text(1600,504,'受访者称追回款项',29,'#77d9c0','middle')+circle(1600,540)+text(960,727,'未经独立审计，不填造金额或收益率',38,'#e8bd72','middle')))
    diagrams.append(group(0,text(200,362,'01',36,'#77d9c0')+text(320,362,'原始事实',48)+text(900,362,'订单、履约、账目',35,'#a5b9b9')+line(320,400,1650,400))+group(1,text(200,513,'02',36,'#77d9c0')+text(320,513,'计算结果',48)+text(900,513,'关联规则与统计口径',35,'#a5b9b9')+line(320,551,1650,551))+group(2,text(200,664,'03',36,'#e8bd72')+text(320,664,'解释建议',48)+text(900,664,'为什么发生？下一步怎么验证？',35,'#e8bd72')+line(320,702,1650,702,'#e8bd72',True)))
    diagrams.append(group(0,text(240,363,'01 / 业务问题',34,'#77d9c0')+text(240,452,'哪件事还在凭感觉？',59))+group(1,text(240,562,'02 / 数据依赖',34,'#77d9c0')+text(240,650,'需要连起哪些系统？',59))+group(2,text(1170,363,'03 / 行动',34,'#e8bd72')+text(1170,452,'谁来做？',59)+text(1170,555,'做什么？',59)+text(1170,675,'可暂停，代入自己的业务',30,'#a5b9b9')))
    diagrams.append(group(0,text(250,360,'问题',32,'#a5b9b9')+text(250,430,'判断赠品组合',49)+circle(250,506))+group(1,line(270,506,960,506)+text(960,360,'数据',32,'#a5b9b9','middle')+text(960,430,'订单 × 履约 × 复购',45,'#77d9c0','middle')+circle(960,506))+group(2,line(980,506,1650,506)+text(1650,360,'行动',32,'#a5b9b9','end')+text(1650,430,'营销团队调整后验证',43,'#e8bd72','end')+circle(1650,506,15,'#e8bd72')+text(960,725,'好的 AI，帮助你发现值得做的事',53,'#eeeae0','middle')))
    heads=['卖得好，就该拿来做小样吗？','把分散的记录，连成同一段经历','发现关联，不等于证明原因','换一个问题：经营数据里藏着什么？','线索之后，还有一道核查','让结论能够被追溯','把三个问题，留给自己的业务','回到小样案例：答案落在行动上']
    sections=[]; motion=[]
    for i,(seg,shot,diagram) in enumerate(zip(recipe['segments'],shots,diagrams)):
        sid=seg['id'];t=shot['start_s'];d=shot['duration_s']
        sections.append(f'<section class="scene clip" id="{sid}" data-shot-id="{sid}" data-start="{t}" data-duration="{d}" data-track-index="0"><div class="top">MENZA / 经营洞察<span>{i+1:02} — 08</span></div><h1>{e(heads[i])}</h1><svg viewBox="0 0 1920 1080" aria-label="解释性示意">{diagram}</svg><div class="caption">{e(seg["text"])}</div><div class="foot">访谈案例转述 · 未经独立审计 · 图形为解释性示意</div></section>')
        for n,f in [(0,0),(1,.27),(2,.57)]:
            at=t+d*f
            motion.append(f'tl.fromTo("#{sid} .b{n}",{{opacity:0,y:14}},{{opacity:1,y:0,duration:.48,ease:"power2.out",immediateRender:false}},{at});')
    css='''*{box-sizing:border-box;margin:0}body{font-family:system-ui,sans-serif;background:#12272c}#root{position:relative;width:100%;height:100%;overflow:hidden}.scene{position:absolute;inset:0;background:#12272c;color:#eeeae0}.top{position:absolute;left:90px;right:90px;top:53px;font-size:24px;letter-spacing:3px;color:#a5b9b9}.top span{float:right}h1{position:absolute;top:135px;left:90px;font-size:63px;letter-spacing:-1px;font-weight:620;z-index:1}svg{position:absolute;inset:0;width:100%;height:100%;font-weight:500}.beat{opacity:0;transform-box:view-box}.caption{position:absolute;left:160px;right:160px;top:826px;font-size:34px;line-height:1.65;color:#eeeae0}.foot{position:absolute;left:90px;bottom:42px;font-size:22px;color:#a5b9b9}.rail{position:absolute;bottom:0;width:100%;height:5px;background:#77d9c0;transform-origin:left center}'''
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><script src="gsap.min.js"></script><style>'+css+'</style></head><body>'+f'<div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="1920" data-height="1080" data-fps="30">'+''.join(sections)+f'<div class="rail"></div><audio class="clip" id="narration" src="assets/narration.wav" data-start="0" data-duration="{total}" data-track-index="1"></audio></div><script>const tl=gsap.timeline({{paused:true}});'+''.join(motion)+f'tl.fromTo(".rail",{{scaleX:0}},{{scaleX:1,duration:{total},ease:"none"}},0);window.__timelines=window.__timelines||{{}};window.__timelines.main=tl;</script></body></html>'
