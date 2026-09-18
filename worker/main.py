from __future__ import annotations
import fcntl, json, shutil, signal, threading, time, zipfile, sys
import jsonschema
from apps.server.core import (
    Store,
    ROOT,
    GATES,
    CONTENT_DIRS,
    now,
    uid,
    dumps,
    digest,
    safe,
    atomic,
)
from adapters.timing import check_timing
from adapters.handoff import validate_handoff
from adapters.tools import Blocked, Cancelled, process, hf_command, media_qa

REQUIRED = {
    "brief": [
        "documents/BRIEF.md",
        "documents/claims-map.json",
        "documents/assets-manifest.json",
    ],
    "content": ["documents/SCRIPT.md"],
    "storyboard": ["documents/STORYBOARD.md", "documents/DESIGN.md"],
    "sample": ["hyperframes/index.html"],
    "timing": ["documents/timing.json"],
    "preview": ["hyperframes/index.html"],
    "render": [],
    "delivery": [],
}


def timing_validate(path):
    d = json.loads(path.read_text())
    if d.get("status") != "locked":
        raise Blocked("timing.json 尚未锁定；请先试听、校正字幕与时间")
    duration = d.get("total_duration_s", 0)
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise ValueError("总时长必须大于零")
    ids = set()
    for s in d.get("shots", []):
        if (
            s["shot_id"] in ids
            or s["start_s"] < 0
            or s["duration_s"] <= 0
            or s["start_s"] + s["duration_s"] > duration + 0.001
        ):
            raise ValueError("镜头编号或时间无效")
        ids.add(s["shot_id"])
    if not ids:
        raise ValueError("缺少镜头时间")
    return d


class Worker:
    def __init__(self, store):
        self.store = store

    def claim(self):
        # The explicit article runner uses the same local synthesis/render resources.
        # Do not start a queued job while that runner holds its process lock.
        with (self.store.home / "article-pipeline.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
        with self.store.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            stale = c.execute(
                "SELECT * FROM runs WHERE status='running' AND heartbeat<?",
                (now() - 30,),
            ).fetchall()
            for r in stale:
                # Lost leases never imply success. The exclusive worker lock guarantees no live
                # worker owns this lease. A PID is not killed here: it may have been reused.
                c.execute(
                    "UPDATE runs SET status='blocked',message='Worker 中断；检查产物后重试' WHERE id=?",
                    (r["id"],),
                )
                self.store.event(c, r["project_id"], r["id"], "run.interrupted", {})
            if c.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
                return None
            r = c.execute(
                "SELECT id FROM runs WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if not r:
                return None
            c.execute(
                "UPDATE runs SET status='running',heartbeat=? WHERE id=?",
                (now(), r["id"]),
            )
        return self.store.run(r["id"])

    def execute(self, r):
        s = self.store
        pid = r["project_id"]
        rid = r["id"]
        root = s.root(pid)
        folder = root / "runs" / rid
        work = folder / "work"
        folder.mkdir(parents=True, exist_ok=True)
        work.mkdir(exist_ok=True)
        stop = threading.Event()

        def beat(child=None):
            with s.conn() as c:
                c.execute(
                    "UPDATE runs SET heartbeat=?,pid=COALESCE(?,pid) WHERE id=? AND status=?",
                    (now(), child, rid, "running"),
                )

        def ticker():
            while not stop.wait(2):
                beat()

        thread = threading.Thread(target=ticker, daemon=True)
        thread.start()

        def cancel():
            return s.run(rid)["status"] == "cancelled"

        def run_cmd(args, log, cwd=None, timeout=1800):
            return process(args, cwd or work, log, cancel, beat, timeout)

        try:
            if s.snapshot(pid) != r["inputs"]:
                raise Blocked("排队期间输入已变化，请重新提交任务")
            for part in CONTENT_DIRS:
                shutil.copytree(
                    root / part,
                    work / part,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("node_modules"),
                )
            shutil.copyfile(root / "AGENTS.md", work / "AGENTS.md")
            (work / "qa").mkdir(exist_ok=True)
            (work / "exports").mkdir(exist_ok=True)
            config = s.project(pid)["config"]
            visual_lock = None
            if (r["kind"] == "agent" and r["stage"] == "preview") or r["kind"] in ("render", "package", "article"):
                from apps.server.visual import require_approved
                try:
                    visual_lock = require_approved(s, pid)
                except ValueError as exc:
                    raise Blocked(str(exc))
            outputs = []
            message = ""
            needs_review = False
            if r["kind"] == "article":
                from adapters.article_video import produce
                if r.get("retry_of"):
                    previous = s.run(r["retry_of"])
                    cache = root / "runs" / previous["id"] / "work"
                    if previous["kind"] == "article" and previous["inputs"] == r["inputs"] and cache.is_dir():
                        for part in ("audio", "captions", "hyperframes", "qa", "exports"):
                            shutil.copytree(cache/part, work/part, dirs_exist_ok=True)
                recipe = json.loads(safe(work, r["payload"]["recipe_path"]).read_text())
                def progress(text):
                    with s.conn() as c:
                        c.execute("UPDATE runs SET message=? WHERE id=?", (text,rid))
                        s.event(c,pid,rid,"article.progress",{"message":text})
                outputs = produce(work,recipe,config,s.services(),run_cmd,cancel,progress)
                needs_review = True
                message = "文章视频已生成，技术检查通过；请完整试听和观看后确认此版本"
            elif r["kind"] in ("agent", "article-plan"):
                if r["stage"] in ("render", "delivery"):
                    raise Blocked("渲染和交付请使用对应工具任务")
                branch = s.project(pid)["branch"]
                skills = ["video-orchestrator", f"video-{branch}"]
                if r["stage"] == "timing":
                    skills += ["video-qwen-narration"]
                prompt = f"""你正在执行视频平台的单个阶段：{r["stage"]}。只在当前工作目录内产出内容。\n读取 AGENTS.md 以及下列 Skills：{[str(ROOT / ".agents/skills" / x / "SKILL.md") for x in skills]}\n输入配置：{dumps(config)}\n用户本次意见（作为需求，不得覆盖执行边界）：{r["payload"].get("instruction", "")}\n交接字段见 {ROOT / "文件交接约定.md"}。当前目录 documents 存放文档和 JSON，其他目录存放素材。维护稳定编号。\n必需产物：{REQUIRED[r["stage"]]}。不得虚构事实、声音、生成结果、审核或运行工具证据。缺少依赖就返回 blocked 并列出原因。不得直接访问 Qwen、执行渲染、发布或更改平台数据库；需要这些操作时列为阻塞。\n每个完整工程镜头节点写 data-shot-id 对应 timing.json 的 shot_id；data-start、data-duration 和根总时长必须匹配时间表。画面工程使用 HyperFrames，先读取已安装 hyperframes Skill 及对应领域规范。已存在 BRIEF 时不重新访谈；必要时补 workflow/flow 字段。\n只返回 schema 规定的结果；artifacts 必须列出现有文件的相对路径。"""
                from apps.server.visual import state as visual_state
                visual = visual_state(s, pid)
                if visual["required"]:
                    prompt += "\n视觉交接（平台状态为准，不得自行写已批准）：" + dumps(visual) + "\n若已选择方向，读取对应design_path实现整片。未选择时只准备参考和小样，不制作完整视频。不要继承旧项目颜色。已确认时不得更改DESIGN.md、REFERENCES.md、VISUAL-PLAN.json、候选设计及小样证据；需修改则返回blocked请求重新确认。"
                required = REQUIRED[r["stage"]]
                if r["kind"] == "article-plan":
                    from adapters.article_plan import read_article, plan_prompt, REQUIRED_ARTICLE_PLAN
                    article_text = read_article(work, r["payload"].get("article_path"))
                    atomic(work / "documents/SOURCE.md", article_text)
                    prompt = f"平台根目录：{ROOT}。读取规则和 Skills：{[str(ROOT / '.agents/skills' / x / 'SKILL.md') for x in skills]}。项目配置：{dumps(config)}。\n" + plan_prompt(r["payload"]["article_path"], branch)
                    required = REQUIRED_ARTICLE_PLAN
                atomic(folder / "request.txt", prompt)
                result = folder / "agent-result.json"
                run_cmd(
                    [
                        "codex",
                        "exec",
                        "-C",
                        str(work),
                        "-s",
                        "workspace-write",
                        "--skip-git-repo-check",
                        "--json",
                        "--output-schema",
                        str(ROOT / "schemas/agent-result.json"),
                        "-o",
                        str(result),
                        prompt,
                    ],
                    folder / "codex.jsonl",
                    timeout=1800,
                )
                data = json.loads(result.read_text())
                jsonschema.validate(
                    data, json.loads((ROOT / "schemas/agent-result.json").read_text())
                )
                if data["status"] == "blocked":
                    raise Blocked("; ".join(data["blockers"]) or data["summary"])
                for path in required + data["artifacts"]:
                    target = safe(work, path)
                    if not target.is_file() or not target.stat().st_size:
                        raise ValueError(f"缺少有效产物：{path}")
                if r["kind"] == "article-plan" and (work / "documents/SOURCE.md").read_text() != article_text:
                    raise ValueError("原文留档被修改，请保持 SOURCE.md 与导入文章一致")
                if r["stage"] == "timing":
                    timing_validate(work / "documents/timing.json")
                if visual_lock:
                    from apps.server.visual import verify_work_copy
                    verify_work_copy(visual_lock, work)
                if r["stage"] in ("sample", "preview"):
                    if r["stage"] == "preview":
                        check_timing(
                            work / "documents/timing.json",
                            work / "hyperframes/index.html",
                        )
                    run_cmd(
                        hf_command("check", work / "hyperframes"),
                        folder / "hyperframes-check.log",
                    )
                    preview = work / "exports" / f"{r['stage']}.mp4"
                    args = hf_command("render", work / "hyperframes", preview)
                    args[args.index("delivery")] = "draft"
                    run_cmd(args, folder / "preview-render.log")
                    outputs.append(str(preview.relative_to(work)))
                    if r["stage"] == "sample" and (config.get("visual_review_required") or (work / "documents/VISUAL-PLAN.json").exists()):
                        from apps.server.visual import register_sample
                        register_sample(work, rid)
                message = data["summary"]
                needs_review = r["stage"] in GATES and not (
                    r["stage"] == "timing" and config.get("audio_mode") == "none"
                )
            elif r["kind"] == "tts":
                req = r["payload"]
                services = s.services()
                voice = req.get("voice", "Serena")
                text = req["text"]
                audio = work / "audio" / f"{rid}.wav"
                request = folder / "service-request.json"
                atomic(
                    request,
                    dumps(
                        {
                            "kind": "tts",
                            "config": services.get("qwen", {}),
                            "text": text,
                            "voice": voice,
                            "style": req.get("style", "自然清晰，适合教学与产品解说"),
                            "output": str(audio),
                            "metadata": str(folder / "voice-meta.json"),
                        }
                    ),
                )
                run_cmd(
                    [sys.executable, "-m", "adapters.service_job", str(request)],
                    folder / "qwen.log",
                    cwd=ROOT,
                    timeout=300,
                )
                info = json.loads((folder / "voice-meta.json").read_text())
                atomic(
                    work / "audio" / f"{rid}.json",
                    dumps(
                        {
                            **info,
                            "text": text,
                            "requested_style": req.get("style"),
                            "segment_id": req.get("segment_id"),
                            "listening_review": "not_done",
                        }
                    ),
                )
                voice_path = work / "documents/voice-config.json"
                voice_data = (
                    json.loads(voice_path.read_text())
                    if voice_path.exists()
                    else {"requests": []}
                )
                voice_data.update(
                    {
                        "provider": "local_qwen",
                        "model_version": info["model_version"],
                        "voice": info["reported_voice"],
                        "listening_review": "not_done",
                    }
                )
                voice_data.setdefault("requests", []).append(
                    {
                        "segment_id": req.get("segment_id") or "UNASSIGNED-" + rid[:8],
                        "text": text,
                        "output_path": "audio/" + audio.name,
                        "revision": rid,
                    }
                )
                atomic(voice_path, dumps(voice_data))
                outputs += ["audio/" + audio.name, "audio/" + rid + ".json"]
                message = "音频已生成，等待试听；尚未锁定时间"
            elif r["kind"] == "transcribe":
                src = safe(work, r["payload"]["path"])
                if not src.is_file():
                    raise ValueError("音频不存在")
                out = work / "captions" / f"{rid}.json"
                request = folder / "service-request.json"
                atomic(
                    request,
                    dumps(
                        {
                            "kind": "transcribe",
                            "config": s.services().get("qwen", {}),
                            "input": str(src),
                            "output": str(out),
                        }
                    ),
                )
                run_cmd(
                    [sys.executable, "-m", "adapters.service_job", str(request)],
                    folder / "transcribe.log",
                    cwd=ROOT,
                    timeout=300,
                )
                outputs.append(str(out.relative_to(work)))
                message = "转录完成，需人工校正；未生成虚构词级时间"
            elif r["kind"] in ("render", "qa"):
                if r["kind"] == "render":
                    timing_validate(work / "documents/timing.json")
                    check_timing(
                        work / "documents/timing.json", work / "hyperframes/index.html"
                    )
                    run_cmd(
                        hf_command("check", work / "hyperframes"),
                        folder / "hyperframes-check.log",
                    )
                    source = work / "exports" / f"{rid}.mp4"
                    run_cmd(
                        hf_command("render", work / "hyperframes", source),
                        folder / "render.log",
                    )
                else:
                    artifact = s.rows(
                        "SELECT * FROM artifacts WHERE id=? AND project_id=?",
                        (r["payload"]["artifact_id"], pid),
                    )
                    if not artifact:
                        raise ValueError("视频产物不存在")
                    original = safe(root, artifact[0]["path"])
                    if (
                        not original.is_file()
                        or digest(original) != artifact[0]["sha256"]
                    ):
                        raise Blocked("视频已变化，需重新登记")
                    source = work / "exports" / original.name
                    shutil.copyfile(original, source)
                report = media_qa(
                    source, work / "qa", config.get("targets", {}), run_cmd
                )
                outputs += [
                    str(f.relative_to(work))
                    for f in (work / "qa").rglob("*")
                    if f.is_file()
                ] + [str(source.relative_to(work))]
                message = "技术检查完成；人工声画与分支检查仍需确认"
                if report["automated_status"] != "pass":
                    raise Blocked("QA 未通过或目标未配置，见运行目录 qa/report.json")
                needs_review = True
            elif r["kind"] == "package":
                render = s.rows(
                    "SELECT id FROM runs WHERE project_id=? AND stage='render' AND status='succeeded' ORDER BY created DESC LIMIT 1",
                    (pid,),
                )
                if not render:
                    raise Blocked("缺少通过确认的渲染验收")
                rr = s.run(render[0]["id"])
                exports = s.rows("SELECT * FROM artifacts WHERE run_id=?", (rr["id"],))
                target = work / "exports" / "delivery.zip"
                with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
                    for art in exports:
                        src = safe(root, art["path"])
                        if digest(src) != art["sha256"]:
                            raise Blocked("交付产物哈希不一致")
                        z.write(src, art["path"])
                    for part in CONTENT_DIRS:
                        for src in (work / part).rglob("*"):
                            if src.is_file():
                                z.write(src, str(src.relative_to(work)))
                manifest = {
                    "project_id": pid,
                    "revision": rid,
                    "status": "packaged",
                    "input_versions": r["inputs"],
                    "hyperframes_version": json.loads(
                        (ROOT / "node_modules/hyperframes/package.json").read_text()
                    )["version"],
                    "outputs": [
                        {"path": a["path"], "sha256": a["sha256"]} for a in exports
                    ],
                    "qa_review_run": rr["id"],
                    "learning_effect": "not_verified",
                    "visual_review": visual_lock,
                }
                atomic(work / "exports" / "delivery.json", dumps(manifest))
                with zipfile.ZipFile(target, "a", zipfile.ZIP_DEFLATED) as z:
                    z.write(work / "exports/delivery.json", "delivery.json")
                outputs += ["exports/delivery.zip", "exports/delivery.json"]
                message = "交付包已生成，未发布"
            else:
                raise ValueError("未知任务类型")
            if cancel():
                raise Cancelled()
            # Validate before promoting any file. The run copy remains the immutable evidence.
            if s.snapshot(pid) != r["inputs"]:
                raise Blocked("执行期间源文件变化，保留运行副本，未覆盖项目")
            validate_handoff(work)
            changed = []
            for part in CONTENT_DIRS:
                for src in (work / part).rglob("*"):
                    if src.is_symlink():
                        raise ValueError("产物不允许符号链接")
                    if (
                        src.is_file()
                        and src.name != "STATUS.md"
                        and "node_modules" not in src.parts
                    ):
                        rel = str(src.relative_to(work))
                        safe(work, rel)
                        if digest(src) != r["inputs"].get(rel):
                            changed.append((src, rel))
            with s.conn() as c:
                c.execute("BEGIN IMMEDIATE")
                if (
                    c.execute("SELECT status FROM runs WHERE id=?", (rid,)).fetchone()[
                        "status"
                    ]
                    == "cancelled"
                ):
                    raise Cancelled()
                for src, rel in changed:
                    dst = safe(root, rel)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
                    # Artifact points to immutable run copy, never to the promoted mutable input.
                    outputs.append(rel)
                artifact_ids = []
                for rel in sorted(set(outputs)):
                    src = safe(work, rel)
                    if not src.is_file():
                        continue
                    aid = uid()
                    artifact_ids.append(aid)
                    c.execute(
                        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                        (
                            aid,
                            pid,
                            rid,
                            str(src.relative_to(root)),
                            digest(src),
                            "output",
                            now(),
                        ),
                    )
                snapshot = s.snapshot(pid)
                status = "awaiting_review" if needs_review else "succeeded"
                c.execute(
                    "UPDATE runs SET status=?,outputs=?,message=?,heartbeat=? WHERE id=?",
                    (
                        status,
                        dumps({"snapshot": snapshot, "artifacts": artifact_ids}),
                        message,
                        now(),
                        rid,
                    ),
                )
                s.event(
                    c, pid, rid, "run.finished", {"status": status, "message": message}
                )
        except BaseException as e:
            status = (
                "cancelled"
                if isinstance(e, Cancelled)
                else "blocked"
                if isinstance(e, (Blocked, KeyboardInterrupt, SystemExit))
                else "failed"
            )
            with s.conn() as c:
                if s.run(rid)["status"] == "cancelled":
                    status = "cancelled"
                evidence = []
                for part in ("qa", "exports"):
                    for src in (work / part).rglob("*"):
                        if (
                            src.is_file()
                            and not src.is_symlink()
                            and src.suffix in (".json", ".jpg", ".mp4")
                        ):
                            aid = uid()
                            evidence.append(aid)
                            c.execute(
                                "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                                (
                                    aid,
                                    pid,
                                    rid,
                                    str(src.relative_to(root)),
                                    digest(src),
                                    "failed_evidence",
                                    now(),
                                ),
                            )
                if evidence:
                    c.execute(
                        "UPDATE runs SET outputs=? WHERE id=?",
                        (dumps({"artifacts": evidence}), rid),
                    )
                c.execute(
                    "UPDATE runs SET status=?,message=?,heartbeat=? WHERE id=?",
                    (status, str(e)[:1500], now(), rid),
                )
                s.event(
                    c,
                    pid,
                    rid,
                    "run.finished",
                    {"status": status, "message": str(e)[:1500]},
                )
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            stop.set()
            thread.join(timeout=3)
            s.export_status(pid)

    def loop(self):
        lock = (self.store.home / "worker.lock").open("w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("已有 Worker 在运行")
        while True:
            r = self.claim()
            if r:
                self.execute(r)
            else:
                time.sleep(1)


if __name__ == "__main__":

    def shutdown(signum, frame):
        raise KeyboardInterrupt("Worker 已停止，任务需重试")

    signal.signal(signal.SIGTERM, shutdown)
    Worker(Store()).loop()
