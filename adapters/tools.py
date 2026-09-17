from __future__ import annotations
import base64, json, os, re, signal, subprocess, time, urllib.parse
import httpx
from apps.server.core import ROOT, digest, dumps, atomic


class Blocked(Exception):
    pass


class Cancelled(Exception):
    pass


def local_url(url):
    p = urllib.parse.urlparse(url)
    if (
        p.scheme != "http"
        or p.hostname not in ("localhost", "127.0.0.1", "::1")
        or p.username
        or p.password
        or p.query
        or p.fragment
    ):
        raise ValueError("首版仅支持无凭据的本机 HTTP 服务地址")
    return url.rstrip("/")


def process(
    argv, cwd, log, cancel=lambda: False, heartbeat=lambda pid: None, timeout=1800
):
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VIDEO_"):
            env.pop(key)
    with log.open("w") as out:
        p = subprocess.Popen(
            [str(x) for x in argv],
            cwd=cwd,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
        started = time.monotonic()
        try:
            while p.poll() is None:
                heartbeat(p.pid)
                if cancel():
                    raise Cancelled("用户取消")
                if time.monotonic() - started > timeout:
                    raise Blocked("执行超时，检查日志后重试")
                time.sleep(0.3)
        except BaseException:
            try:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            raise
    if p.returncode:
        raise RuntimeError(f"工具退出码 {p.returncode}，见 {log.name}")
    return log.read_text(errors="replace")


def qwen_health(config):
    url = local_url(config.get("base_url", "http://127.0.0.1:8001"))
    with httpx.Client(timeout=5, trust_env=False) as client:
        r = client.get(url + "/health")
        r.raise_for_status()
        health = r.json()
        r = client.get(url + "/openapi.json")
        r.raise_for_status()
        api = r.json()
    if "/synthesize" not in api.get("paths", {}):
        raise Blocked("服务不符合 synthesize 接口，请添加适配器")
    return {
        "status": "ready" if health.get("ready") else "blocked",
        "health": health,
        "capabilities": list(api["paths"]),
    }


def qwen_synthesize(config, text, voice, style, out):
    health = qwen_health(config)
    if health["status"] != "ready":
        raise Blocked("Qwen 服务未就绪")
    with httpx.Client(timeout=240, trust_env=False) as client:
        r = client.post(
            local_url(config.get("base_url", "http://127.0.0.1:8001")) + "/synthesize",
            json={"text": text, "voice": voice, "style": style},
        )
        r.raise_for_status()
    if r.headers.get("content-type", "").startswith("audio/") or r.content[:4] in (
        b"RIFF",
        b"fLaC",
        b"OggS",
    ):
        content = r.content
    else:
        data = r.json()
        encoded = data.get("audio_base64") or data.get("audio")
        if not isinstance(encoded, str):
            raise Blocked("未知合成响应；需适配实际音频字段")
        content = base64.b64decode(encoded.split(",")[-1], validate=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(probe.stdout)
    return {
        "model_version": health["health"].get("model"),
        "reported_voice": health["health"].get("voice"),
        "requested_voice": voice,
        "duration_s": float(info["format"]["duration"]),
        "sha256": digest(out),
    }


def transcribe(config, audio, out):
    with audio.open("rb") as f, httpx.Client(timeout=240, trust_env=False) as client:
        r = client.post(
            local_url(config.get("base_url", "http://127.0.0.1:8001")) + "/transcribe",
            files={"audio": (audio.name, f, "application/octet-stream")},
        )
        r.raise_for_status()
    result = r.json()
    atomic(
        out,
        dumps(
            {
                "status": "needs_correction",
                "result": result,
                "source_sha256": digest(audio),
            }
        ),
    )
    return result


def hf_command(action, project, output=None):
    binary = ROOT / "node_modules/.bin/hyperframes"
    if not binary.exists():
        raise Blocked("HyperFrames 尚未安装，请先运行 npm ci")
    command = [str(binary), action, str(project)]
    if action == "render":
        command += ["--quality", "delivery", "--output", str(output)]
    return command


def media_qa(source, out, targets, run_process):
    out.mkdir(parents=True, exist_ok=True)
    raw = run_process(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(source),
        ],
        out / "probe.log",
    )
    probe = json.loads(raw)
    video = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("交付文件不含视频轨道")
    audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    duration = float(probe["format"]["duration"])
    a, b = map(int, video["avg_frame_rate"].split("/"))
    fps = a / b if b else 0
    actual = {
        "width": video["width"],
        "height": video["height"],
        "fps": fps,
        "duration_s": duration,
        "video_codec": video["codec_name"],
        "audio_codec": audio["codec_name"] if audio else None,
        "sample_rate": int(audio["sample_rate"]) if audio else None,
        "channels": audio.get("channels") if audio else None,
    }
    checks = []
    for key in (
        "width",
        "height",
        "fps",
        "video_codec",
        "sample_rate",
        "audio_codec",
        "channels",
    ):
        if key in targets:
            checks.append(
                {
                    "name": key,
                    "target": targets[key],
                    "actual": actual[key],
                    "status": "pass" if actual[key] == targets[key] else "fail",
                }
            )
    if "duration_s" in targets:
        checks.append(
            {
                "name": "duration_s",
                "target": targets["duration_s"],
                "actual": duration,
                "status": "pass"
                if abs(duration - targets["duration_s"]) <= max(1 / fps, 0.05)
                else "fail",
            }
        )
    for key in ("width", "height", "fps", "video_codec"):
        if key not in targets:
            checks.append({"name": key, "status": "not_configured"})
    loudness = None
    if audio:
        log = run_process(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(source),
                "-vn",
                "-af",
                "loudnorm=print_format=json",
                "-f",
                "null",
                "-",
            ],
            out / "loudness.log",
        )
        match = re.search(r'\{\s*"input_i".*?\}', log, re.S)
        if match:
            loudness = json.loads(match.group())
            integrated = float(loudness["input_i"])
            peak = float(loudness["input_tp"])
            for key, value in [("lufs", integrated), ("true_peak_db", peak)]:
                target = targets.get(key)
                ok = (
                    (abs(value - target) <= targets.get("lufs_tolerance", 1))
                    if key == "lufs" and target is not None
                    else (value <= target if target is not None else False)
                )
                checks.append(
                    {
                        "name": key,
                        "target": target,
                        "actual": value if abs(value) != float("inf") else None,
                        "status": ("pass" if ok else "fail")
                        if target is not None
                        else "not_configured",
                    }
                )
    else:
        checks.append(
            {"name": "audio", "status": "not_applicable", "reason": "最终文件无音轨"}
        )
    run_process(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(source),
            "-vf",
            "blackdetect=d=0.1:pix_th=0.1",
            "-an",
            "-f",
            "null",
            "-",
        ],
        out / "blackdetect.log",
    )
    frames = []
    # AAC padding can extend the container past the final video frame. Seek just
    # before the final frame timestamp, using the VIDEO track rather than audio.
    frame_count = int(video.get("nb_frames") or round(float(video.get("duration", duration)) * fps))
    last_frame_at = max(0, (frame_count - 1.25) / fps)
    for index, at in enumerate([0, min(duration / 2, last_frame_at), last_frame_at]):
        frame = out / f"frame-{index}.jpg"
        run_process(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(at),
                "-i",
                str(source),
                "-frames:v",
                "1",
                str(frame),
            ],
            out / f"frame-{index}.log",
        )
        if not frame.exists():
            raise RuntimeError("抽帧未产生文件")
        frames.append({"path": frame.name, "at_s": at, "sha256": digest(frame)})
    report = {
        "output_path": str(source),
        "output_sha256": digest(source),
        "tools": {
            name: run_process(
                [name, "-version"], out / f"{name}-version.log"
            ).splitlines()[0]
            for name in ("ffmpeg", "ffprobe")
        },
        "actual": actual,
        "checks": checks,
        "loudness": loudness,
        "frames": frames,
        "automated_status": "fail"
        if any(c["status"] == "fail" for c in checks)
        else (
            "incomplete"
            if not targets or any(c["status"] == "not_configured" for c in checks)
            else "pass"
        ),
        "human_review": "not_done",
        "learning_effect": "not_verified",
    }
    atomic(out / "report.json", dumps(report))
    return report
