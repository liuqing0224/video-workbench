from __future__ import annotations
import asyncio, json, mimetypes, secrets, subprocess
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from apps.server.core import (
    Store,
    ROOT,
    STAGES,
    LABELS,
    CONTENT_DIRS,
    EDITABLE,
    safe,
    digest,
    dumps,
    uid,
    now,
)
from adapters.tools import qwen_health, local_url


class NewProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    branch: Literal["marketing", "teaching"]
    config: dict = Field(default_factory=dict)


class Document(BaseModel):
    path: str
    content: str = Field(max_length=2_000_000)
    revision: str | None = None


class RunRequest(BaseModel):
    stage: Literal[
        "brief",
        "content",
        "storyboard",
        "sample",
        "timing",
        "preview",
        "render",
        "delivery",
    ]
    kind: Literal["agent", "tts", "transcribe", "render", "qa", "package", "article", "article-plan"] = "agent"
    idempotency_key: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    decision: Literal["approve", "revise"]
    note: str = Field(default="", max_length=10000)


class Comment(BaseModel):
    artifact_id: str
    at_s: float = Field(ge=0)
    note: str = Field(min_length=1, max_length=10000)


def create_app(store=None):
    s = store or Store()
    app = FastAPI(title="视频制作工作台", version="0.1.0")
    app.state.store = s

    @app.middleware("http")
    async def security(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "无效主机"}, status_code=403)
        origin = request.headers.get("origin")
        expected = "http://" + request.headers.get("host", "")
        if origin and origin != expected:
            return JSONResponse({"detail": "请求来源不匹配"}, status_code=403)
        if request.url.path.startswith("/api/") and request.url.path != "/api/session":
            token = request.cookies.get("video_session", "")
            if not secrets.compare_digest(token, s.token):
                return JSONResponse(
                    {"detail": "请刷新页面建立本机会话"}, status_code=401
                )
            if (
                request.method not in ("GET", "HEAD")
                and request.headers.get("x-video-request") != "workbench"
            ):
                return JSONResponse({"detail": "缺少本机请求标识"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, e):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(request, e):
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.get("/api/session")
    def session():
        r = JSONResponse(
            {
                "ready": True,
                "stages": [{"id": a, "label": b} for a, b in zip(STAGES, LABELS)],
            }
        )
        r.set_cookie("video_session", s.token, httponly=True, samesite="strict")
        return r

    @app.get("/api/projects")
    def projects():
        return [
            s.project(r["id"])
            for r in s.rows("SELECT id FROM projects ORDER BY created DESC")
        ]

    @app.post("/api/projects")
    def create(p: NewProject):
        return s.create(p.name, p.branch, p.config)

    @app.get("/api/projects/{pid}")
    def project(pid: str):
        p = s.project(pid)
        snapshot = s.scan(pid)
        runs = [
            s.run(r["id"])
            for r in s.rows(
                "SELECT id FROM runs WHERE project_id=? ORDER BY created DESC", (pid,)
            )
        ]
        for r in runs:
            r["stale"] = r["status"] in (
                "succeeded",
                "awaiting_review",
            ) and not s.valid(r, snapshot)
        artifacts = []
        hashes = {}
        seen = set()
        for a in s.rows("SELECT * FROM artifacts WHERE project_id=? ORDER BY created DESC", (pid,)):
            key = (a["path"], a["sha256"])
            if key in seen:
                continue
            seen.add(key)
            if a["path"] not in hashes:
                try:
                    f = safe(s.root(pid), a["path"])
                    hashes[a["path"]] = digest(f) if f.is_file() else None
                except ValueError:
                    hashes[a["path"]] = None
            a["available"] = hashes[a["path"]] == a["sha256"]
            a["version"] = a["path"].split("/")[1] if a["path"].startswith("runs/") else "项目文件"
            artifacts.append(a)
        return {
            **p,
            "config_revision": digest_config(p["config"]),
            "runs": runs,
            "automation_events": [
                {**e, "data": json.loads(e["data"])}
                for e in s.rows(
                    "SELECT id,data,created FROM events WHERE project_id=? AND kind='automation.stage' ORDER BY id DESC LIMIT 100",
                    (pid,),
                )
            ],
            "artifacts": artifacts,
            "reviews": s.rows(
                "SELECT reviews.* FROM reviews JOIN runs ON runs.id=reviews.run_id WHERE runs.project_id=?",
                (pid,),
            ),
            "comments": s.rows(
                "SELECT * FROM comments WHERE project_id=? ORDER BY created", (pid,)
            ),
        }

    @app.patch("/api/projects/{pid}")
    def update(pid: str, body: dict):
        with s.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if s.active(c, pid):
                raise ValueError("请等待任务结束后修改配置")
            old = s.project(pid)
            if body.get("revision") != digest_config(old["config"]):
                raise ValueError("项目配置版本冲突")
            config = body.get("config", {})
            c.execute("UPDATE projects SET config=? WHERE id=?", (dumps(config), pid))
            s.event(c, pid, None, "config.changed", {})
        return s.project(pid)

    @app.get("/api/projects/{pid}/files")
    def files(pid: str):
        return s.files(pid)

    @app.get("/api/projects/{pid}/document")
    def document(pid: str, path: str):
        f = safe(s.root(pid), path)
        if Path(path).parts[0] not in CONTENT_DIRS or f.suffix not in EDITABLE:
            raise ValueError("不是可编辑文档")
        if not f.is_file():
            raise KeyError("文件不存在")
        if f.stat().st_size > 2_000_000:
            raise ValueError("文件过大，请使用本地编辑器")
        return {"path": path, "content": f.read_text(), "revision": digest(f)}

    @app.put("/api/projects/{pid}/document")
    def save(pid: str, body: Document):
        return s.save(pid, body.path, body.content, body.revision)

    @app.post("/api/projects/{pid}/assets")
    async def upload(
        pid: str,
        folder: Literal["assets", "audio", "captions"] = "assets",
        file: UploadFile = File(...),
    ):
        name = Path(file.filename or "asset").name
        if not name or name in (".", ".."):
            raise ValueError("文件名无效")
        rel = f"{folder}/{uid()[:8]}-{name}"
        target = safe(s.root(pid), rel)
        with s.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if s.active(c, pid):
                raise ValueError("任务运行中不能导入素材")
            size = 0
            try:
                with target.open("wb") as out:
                    while data := await file.read(1024 * 1024):
                        size += len(data)
                        if size > 1024**3:
                            raise ValueError("单文件上限 1GB")
                        out.write(data)
                if target.suffix.lower() == ".srt":
                    from adapters.captions import parse_srt

                    parse_srt(target.read_text("utf-8-sig"))
            except:
                target.unlink(missing_ok=True)
                raise
            s.event(c, pid, None, "asset.imported", {"path": rel})
        s.scan(pid)
        return {"path": rel, "sha256": digest(target)}

    @app.post("/api/projects/{pid}/runs")
    def start(pid: str, body: RunRequest):
        if body.kind == "tts" and (
            not isinstance(body.payload.get("text"), str)
            or not 0 < len(body.payload["text"]) <= 500
        ):
            raise ValueError("每段合成文本需要 1–500 字")
        mapping = {
            "tts": "timing",
            "transcribe": "timing",
            "render": "render",
            "qa": "render",
            "package": "delivery",
            "article": "render",
            "article-plan": "content",
        }
        if body.kind in mapping and body.stage != mapping[body.kind]:
            raise ValueError("任务类型与阶段不一致")
        if body.kind == "agent" and body.stage in ("render", "delivery"):
            raise ValueError("该阶段由确定性工具执行")
        return s.create_run(
            pid, body.stage, body.kind, body.idempotency_key, body.payload
        )

    @app.post("/api/runs/{rid}/cancel")
    def cancel(rid: str):
        return s.cancel(rid)

    @app.post("/api/runs/{rid}/retry")
    def retry(rid: str):
        r = s.run(rid)
        if r["status"] not in ("blocked", "failed", "cancelled"):
            raise ValueError("当前任务不可重试")
        return s.create_run(
            r["project_id"], r["stage"], r["kind"], uid(), r["payload"], rid
        )

    @app.post("/api/runs/{rid}/review")
    def review(rid: str, body: ReviewRequest):
        s.review(rid, body.decision, body.note)
        return s.run(rid)

    @app.get("/api/runs/{rid}/logs")
    def logs(rid: str):
        r = s.run(rid)
        folder = s.root(r["project_id"]) / "runs" / rid
        return {
            f.name: f.read_text(errors="replace")[-20000:]
            for f in folder.glob("*")
            if f.is_file() and f.suffix in (".log", ".jsonl", ".json")
        }

    @app.get("/api/projects/{pid}/events")
    async def events(pid: str, request: Request, after: int = 0):
        s.project(pid)
        try:
            after = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise HTTPException(400, "无效事件编号")

        async def stream():
            cursor = after
            while not await request.is_disconnected():
                rows = s.rows(
                    "SELECT * FROM events WHERE project_id=? AND id>? ORDER BY id LIMIT 100",
                    (pid, cursor),
                )
                for row in rows:
                    cursor = row["id"]
                    yield f"id: {cursor}\ndata: {dumps(row)}\n\n"
                if not rows:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/artifacts/{aid}/file")
    def media(aid: str):
        rows = s.rows("SELECT * FROM artifacts WHERE id=?", (aid,))
        if not rows:
            raise KeyError("产物不存在")
        a = rows[0]
        f = safe(s.root(a["project_id"]), a["path"])
        if not f.exists() or digest(f) != a["sha256"]:
            raise ValueError("产物文件已变化，不能使用旧版本链接")
        ext = f.suffix.lower()
        media = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ext not in (
            ".mp4",
            ".webm",
            ".wav",
            ".mp3",
            ".m4a",
            ".ogg",
            ".png",
            ".jpg",
            ".jpeg",
        ):
            return FileResponse(
                f, filename=f.name, media_type="application/octet-stream"
            )
        return FileResponse(f, media_type=media)

    @app.post("/api/projects/{pid}/comments")
    def comment(pid: str, body: Comment):
        if not s.rows(
            "SELECT 1 FROM artifacts WHERE id=? AND project_id=?",
            (body.artifact_id, pid),
        ):
            raise KeyError("产物不存在")
        with s.conn() as c:
            c.execute(
                "INSERT INTO comments VALUES(?,?,?,?,?,?)",
                (uid(), pid, body.artifact_id, body.at_s, body.note, now()),
            )
        return {"saved": True}

    @app.get("/api/services")
    def services():
        return s.services()

    @app.put("/api/services/qwen")
    def configure(body: dict):
        config = {"base_url": local_url(body["base_url"])}
        with s.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO services VALUES(?,?)", ("qwen", dumps(config))
            )
        return config

    @app.post("/api/services/probe")
    def probe():
        result = {}
        for name, cmd in {
            "codex": ["codex", "--version"],
            "ffmpeg": ["ffmpeg", "-version"],
            "ffprobe": ["ffprobe", "-version"],
            "hyperframes": [str(ROOT / "node_modules/.bin/hyperframes"), "--version"],
        }.items():
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                result[name] = {
                    "status": "ready" if p.returncode == 0 else "blocked",
                    "version": (p.stdout or p.stderr).splitlines()[0],
                }
            except Exception as e:
                result[name] = {"status": "blocked", "message": str(e)}
        try:
            result["qwen"] = qwen_health(s.services().get("qwen", {}))
        except Exception as e:
            result["qwen"] = {"status": "blocked", "message": str(e)}
        return result

    dist = ROOT / "apps/web/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    else:

        @app.get("/")
        def not_built():
            return {"message": "先执行 npm --prefix apps/web run build"}

    return app


def digest_config(config):
    import hashlib

    return hashlib.sha256(dumps(config).encode()).hexdigest()
