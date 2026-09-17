"""Check the shared timeline against authored composition markup, never infer word timing."""

import json, math
from html.parser import HTMLParser


class Composition(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


def check_timing(timing_path, html_path):
    timing = json.loads(timing_path.read_text())
    parser = Composition()
    parser.feed(html_path.read_text())
    root = next((a for _, a in parser.nodes if a.get("data-composition-id")), None)
    if not root:
        raise ValueError("缺少 composition 根节点")
    fps = float(timing["fps"])
    duration = float(timing["total_duration_s"])
    tolerance = 0.5 / fps
    if (
        not math.isfinite(fps)
        or fps <= 0
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("时间/帧率无效")
    if abs(float(root.get("data-duration", -1)) - duration) > tolerance:
        raise ValueError("工程总时长与 timing.json 不一致")
    for shot in timing["shots"]:
        node = next(
            (
                a
                for _, a in parser.nodes
                if a.get("data-shot-id", a.get("id")) == shot["shot_id"]
            ),
            None,
        )
        if not node:
            raise ValueError(f"工程未映射镜头 {shot['shot_id']}；请设置 data-shot-id")
        for attr, key in [("data-start", "start_s"), ("data-duration", "duration_s")]:
            value = float(shot[key])
            if (
                not math.isfinite(value)
                or abs(float(node.get(attr, -1)) - value) > tolerance
            ):
                raise ValueError(f"{shot['shot_id']} 的 {attr} 与时间表不一致")
    for caption in timing.get("captions", []):
        if (
            caption["start_s"] < 0
            or caption["duration_s"] <= 0
            or caption["start_s"] + caption["duration_s"] > duration + tolerance
        ):
            raise ValueError("字幕超出视频时间")
    return {
        "status": "pass",
        "shots": len(timing["shots"]),
        "duration_s": duration,
        "fps": fps,
    }
