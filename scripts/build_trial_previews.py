"""制作本平台界面证据的待审核试制；不登记人工确认、不冒充正式交付。"""

import sys, json, shutil, math, html
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.server.core import ROOT, dumps, atomic
from adapters.tools import qwen_synthesize, process, hf_command, media_qa

OUT = ROOT / "workspace/trials"
OUT.mkdir(parents=True, exist_ok=True)
TOPICS = {
    "marketing": {
        "title": "片场，把视频制作留成版本。",
        "segments": [
            (
                "从一个清楚的目标开始",
                "创建项目，选择营销或教学。把观众、目标和资料，写进同一份简报。",
                "platform-create.png",
            ),
            (
                "把修改留在项目里",
                "脚本、分镜和声音分别管理。阶段任务留下记录，修改意见也有对应的版本。",
                "platform-editor.png",
            ),
            (
                "下一条，从这里开始",
                "打开本机片场工作台，创建你的第一个项目。试制版本还需要你试听和确认。",
                "platform-workbench.png",
            ),
        ],
        "end": "打开本机工作台  127.0.0.1:8794",
    },
    "teaching": {
        "title": "第一次使用片场，先把简报写清楚。",
        "segments": [
            (
                "01  创建一个项目",
                "点击新建视频，填写项目名称，选择内容分支。先写清给谁看、看完做什么，以及有哪些资料。",
                "platform-create.png",
            ),
            (
                "02  保存并核对简报",
                "创建后打开内容与素材，选择简报文件，补充内容后保存。重新打开，核对刚才填写的信息。",
                "platform-editor.png",
            ),
            (
                "03  换一个选题，自己试试",
                "现在暂停视频，换一个选题创建项目。检查简报里是否都有观众、目标和素材。缺少哪项，就补上哪项。",
                "platform-workbench.png",
            ),
        ],
        "end": "自检：观众是谁？目标是什么？素材在哪里？",
    },
}
for branch, data in TOPICS.items():
    folder = OUT / branch
    folder.mkdir(exist_ok=True)
    audio = folder / "audio"
    audio.mkdir(exist_ok=True)
    lengths = []
    records = []
    for i, (title, text, img) in enumerate(data["segments"]):
        wav = audio / f"{i}.wav"
        record = audio / f"{i}.json"
        if not wav.exists():
            meta = qwen_synthesize({}, text, "Serena", "自然清晰的普通话解说", wav)
            atomic(
                record, dumps({**meta, "text": text, "listening_review": "not_done"})
            )
        meta = json.loads(record.read_text())
        if meta.get("text") != text:
            raise ValueError("试制旁白已变化，请生成新音频版本；不复用旧文本音频")
        lengths.append(math.ceil((meta["duration_s"] + 0.45) * 30) / 30)
        records.append(meta)
    for variant in (
        ["horizontal", "vertical", "silent"]
        if branch == "marketing"
        else ["horizontal"]
    ):
        work = folder / variant
        work.mkdir(exist_ok=True)
        (work / "assets").mkdir(exist_ok=True)
        shutil.copyfile(
            ROOT / "workspace/service-tests/gsap.min.js", work / "gsap.min.js"
        )
        for _, _, img in data["segments"]:
            shutil.copyfile(ROOT / "qa" / img, work / "assets" / img)
        silent = variant == "silent"
        vertical = variant == "vertical"
        width, height = (1080, 1920) if vertical else (1920, 1080)
        durations = [5, 5, 5] if silent else lengths
        duration = sum(durations)
        sections = []
        tracks = []
        shots = []
        start = 0
        for i, ((title, text, img), d) in enumerate(zip(data["segments"], durations)):
            src = audio / f"{i}.wav"
            shutil.copyfile(src, work / "assets" / src.name)
            sections.append(
                f'<section class="clip scene" id="SH{i + 1:02}" data-shot-id="SH{i + 1:02}" data-start="{start}" data-duration="{d}" data-track-index="0"><div class="inner" id="inner{i}"><p class="tag">片场 / {"营销视频" if branch == "marketing" else "教学自媒体"} · 试制预览</p><h1>{html.escape(title)}</h1><img src="assets/{img}"/><p class="caption">{html.escape(text)}</p><p class="end">{html.escape(data["end"]) if i == 2 else "实际界面状态截图 · 未经人工验收"}</p></div></section>'
            )
            if not silent:
                tracks.append(
                    f'<audio id="voice{i}" class="clip" src="assets/{i}.wav" data-start="{start}" data-duration="{records[i]["duration_s"]}" data-track-index="1"></audio>'
                )
            shots.append(
                {"shot_id": f"SH{i + 1:02}", "start_s": start, "duration_s": d}
            )
            start += d
        markup = f'''<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><script src="gsap.min.js"></script><style>
*{{box-sizing:border-box;margin:0}}body{{background:#edf1e8;color:#243d29;font-family:system-ui,sans-serif}}#root{{width:100%;height:100%;overflow:hidden;position:relative}}.scene{{position:absolute;inset:0;padding:{"150px 80px" if vertical else "64px 110px"};background:#edf1e8}}.inner{{width:100%;height:100%}}.tag{{font-size:24px;color:#42633b;letter-spacing:3px}}h1{{font-size:{"62" if vertical else "60"}px;line-height:1.4;margin:22px 0 28px}}img{{width:100%;height:{"760" if vertical else "590"}px;object-fit:contain;object-position:top;border:2px solid #bdcbb4;border-radius:12px;background:#fafbf8}}.caption{{font-size:{"40" if vertical else "30"}px;line-height:1.6;margin-top:28px;max-width:1600px}}.end{{font-size:23px;color:#42633b;position:absolute;bottom:{"90" if vertical else "30"}px}}
</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{width}" data-height="{height}" data-fps="30">{"".join(sections + tracks)}</div><script>const tl=gsap.timeline({{paused:true}});{"".join(f'tl.fromTo("#inner{i}",{{y:18,opacity:0}},{{y:0,opacity:1,duration:0.6}},{sh["start_s"]});' for i, sh in enumerate(shots))}window.__timelines["main"]=tl;</script></body></html>'''
        atomic(work / "index.html", markup)
        atomic(
            work / "timing.json",
            dumps(
                {
                    "fps": 30,
                    "total_duration_s": duration,
                    "status": "estimated",
                    "audio_mode": "none" if silent else "qwen",
                    "shots": shots,
                    "captions": [],
                }
            ),
        )
        atomic(
            work / "README.md",
            "# 待人工确认的试制预览\n\n实际截图与Qwen音频。段落时间取实际音频长度加停顿；屏幕为句段文案，不是声称词级对齐的字幕。尚未试听、未确认创意或预览，不属于正式交付。\n",
        )
        process(hf_command("check", work), work, work / "check.log")
        dest = work / "preview.mp4"
        args = hf_command("render", work, dest)
        args[args.index("delivery")] = "draft"
        process(args, work, work / "render.log")
        report = media_qa(
            dest,
            work / "qa",
            {"width": width, "height": height, "fps": 30, "video_codec": "h264"},
            lambda args, log: process(args, work, log),
        )
        print(branch, variant, report["automated_status"], duration, flush=True)
