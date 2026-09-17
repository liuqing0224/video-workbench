import re


def parse_srt(text):
    result = []
    for block in re.split(r"\n\s*\n", text.strip().replace("\r", "")):
        if not block.strip():
            continue
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].isdigit():
            raise ValueError("SRT 需要序号、时间和字幕文本")
        m = re.fullmatch(
            r"(\d{2,}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2,}):(\d{2}):(\d{2}),(\d{3})",
            lines[1],
        )
        if not m:
            raise ValueError("SRT 时间格式错误")
        v = list(map(int, m.groups()))
        if any(v[i] >= 60 for i in (1, 2, 5, 6)):
            raise ValueError("SRT 分秒超出范围")
        start = v[0] * 3600 + v[1] * 60 + v[2] + v[3] / 1000
        end = v[4] * 3600 + v[5] * 60 + v[6] + v[7] / 1000
        if end <= start or (
            result and start < result[-1]["start_s"] + result[-1]["duration_s"] - 1e-6
        ):
            raise ValueError("SRT 时间倒序或重叠")
        result.append(
            {
                "caption_id": f"CAP{len(result) + 1:03}",
                "start_s": start,
                "duration_s": round(end - start, 3),
                "text": "\n".join(lines[2:]),
            }
        )
    if not result:
        raise ValueError("字幕为空")
    return result
