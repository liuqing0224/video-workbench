from __future__ import annotations
import contextlib, hashlib, json, os, secrets, shutil, sqlite3, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGES = [
    "brief",
    "content",
    "storyboard",
    "sample",
    "timing",
    "preview",
    "render",
    "delivery",
]
LABELS = [
    "目标与证据",
    "内容设计",
    "镜头设计",
    "关键小样",
    "素材与时间",
    "整片预览",
    "渲染验收",
    "交付复盘",
]
GATES = {"content", "sample", "timing", "preview"}
EDITABLE = {".md", ".json", ".srt", ".txt", ".html", ".css", ".js"}
CONTENT_DIRS = ("documents", "assets", "audio", "captions", "hyperframes")


def now():
    return time.time()


def uid():
    return uuid.uuid4().hex


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def dumps(v):
    return json.dumps(v, ensure_ascii=False)


def safe(root: Path, path: str):
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise ValueError("路径越过项目边界")
    # Disallow every symlink, including ones resolving inside the root.
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("路径必须是项目内相对路径")
    cur = root
    for part in relative.parts:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError("不允许符号链接")
    return target


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uid() + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, home=None):
        self.home = Path(
            home or os.environ.get("VIDEO_WORKSPACE", ROOT / "workspace")
        ).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "projects").mkdir(exist_ok=True)
        self.db = self.home / "platform.sqlite"
        with self.conn() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,branch TEXT NOT NULL,config TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,stage TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,idem TEXT NOT NULL,payload TEXT NOT NULL,inputs TEXT NOT NULL,outputs TEXT NOT NULL DEFAULT '{}',message TEXT NOT NULL DEFAULT '',created REAL NOT NULL,heartbeat REAL,pid INTEGER,retry_of TEXT,UNIQUE(project_id,idem));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,run_id TEXT,path TEXT NOT NULL,sha256 TEXT NOT NULL,role TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,run_id TEXT,kind TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS services(name TEXT PRIMARY KEY,config TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY,project_id TEXT,artifact_id TEXT,at_s REAL,note TEXT,created REAL);
            PRAGMA user_version=1;
            """)
        token = self.home / "session.token"
        if not token.exists():
            try:
                fd = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(secrets.token_urlsafe(32))
            except FileExistsError:
                pass
        self.token = token.read_text().strip()

    @contextlib.contextmanager
    def conn(self):
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=30000")
        try:
            yield c
            c.commit()
        except:
            c.rollback()
            raise
        finally:
            c.close()

    def rows(self, sql, args=()):
        with self.conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def event(self, c, pid, rid, kind, data):
        c.execute(
            "INSERT INTO events(project_id,run_id,kind,data,created) VALUES(?,?,?,?,?)",
            (pid, rid, kind, dumps(data), now()),
        )

    def project(self, pid):
        rows = self.rows("SELECT * FROM projects WHERE id=?", (pid,))
        if not rows:
            raise KeyError("项目不存在")
        row = rows[0]
        row["config"] = json.loads(row["config"])
        return row

    def root(self, pid):
        self.project(pid)
        return self.home / "projects" / pid

    def active(self, c, pid):
        return c.execute(
            "SELECT id FROM runs WHERE project_id=? AND status IN ('queued','running')",
            (pid,),
        ).fetchone()

    def create(self, name, branch, config):
        pid = uid()
        root = self.home / "projects" / pid
        root.mkdir()
        for folder in (*CONTENT_DIRS, "runs", "qa", "exports"):
            (root / folder).mkdir()
        for group in ["common", branch]:
            for src in (ROOT / "templates" / group).rglob("*"):
                if src.is_file():
                    dst = (
                        root / "documents" / src.relative_to(ROOT / "templates" / group)
                    )
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
        for f in (root / "documents").rglob("*.json"):
            data = json.loads(f.read_text())
            data["project_id"] = pid
            atomic(f, dumps(data))
        atomic(
            root / "documents" / "BRIEF.md",
            f"# {name}\n\n主类型：{branch}\n\n"
            + config.get("brief", "")
            + "\n\n状态：待完善，未确认。\n",
        )
        atomic(
            root / "AGENTS.md",
            f"# {name}\n\n项目编号：{pid}\n分支：{branch}\n读取 documents/BRIEF.md 与平台传入的任务说明。只在当前运行副本产出内容。不要修改父目录、平台状态、确认或凭据。\n公共规则：{ROOT / 'AGENTS.md'}\n",
        )
        with self.conn() as c:
            c.execute(
                "INSERT INTO projects VALUES(?,?,?,?,?)",
                (pid, name, branch, dumps(config), now()),
            )
            self.event(c, pid, None, "project.created", {"name": name})
        self.export_status(pid)
        return self.project(pid)

    def snapshot(self, pid):
        root = self.root(pid)
        result = {}
        for folder in CONTENT_DIRS:
            for f in sorted((root / folder).rglob("*")):
                if f.is_symlink():
                    raise ValueError("项目包含符号链接")
                if (
                    f.is_file()
                    and "node_modules" not in f.parts
                    and f.name != "STATUS.md"
                ):
                    result[str(f.relative_to(root))] = digest(f)
        result["@config"] = hashlib.sha256(
            dumps(self.project(pid)["config"]).encode()
        ).hexdigest()
        return result

    def scan(self, pid):
        snap = self.snapshot(pid)
        with self.conn() as c:
            for path, sha in snap.items():
                if path.startswith("@"):
                    continue
                last = c.execute(
                    "SELECT sha256 FROM artifacts WHERE project_id=? AND path=? ORDER BY created DESC LIMIT 1",
                    (pid, path),
                ).fetchone()
                if not last or last["sha256"] != sha:
                    c.execute(
                        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                        (uid(), pid, None, path, sha, "source", now()),
                    )
                    self.event(c, pid, None, "artifact.changed", {"path": path})
        return snap

    def run(self, rid):
        rows = self.rows("SELECT * FROM runs WHERE id=?", (rid,))
        if not rows:
            raise KeyError("任务不存在")
        r = rows[0]
        for key in ["payload", "inputs", "outputs"]:
            r[key] = json.loads(r[key])
        return r

    def dependencies(self, stage, snapshot):
        # New audio must not invalidate an approved script; edits to script must.
        common = {
            "BRIEF.md",
            "claims-map.json",
            "assets-manifest.json",
            "REFERENCES.md",
        }
        content = common | {
            "SCRIPT.md",
            "LESSON-PLAN.md",
            "ANSWER-KEY.md",
            "steps.json",
        }
        story = content | {"STORYBOARD.md", "DESIGN.md", "components-map.json"}
        names = common if stage == "brief" else content if stage == "content" else story
        if stage in ("timing", "preview", "render", "delivery"):
            return snapshot
        return {
            k: v
            for k, v in snapshot.items()
            if k == "@config"
            or (
                k.startswith("documents/")
                and (Path(k).name in names or "/practice/" in k)
            )
            or k.startswith("assets/")
            or (stage == "sample" and k.startswith("hyperframes/"))
        }

    def valid(self, run, snapshot):
        if run["status"] not in ("succeeded", "awaiting_review"):
            return False
        if self.dependencies(
            run["stage"], run["outputs"].get("snapshot", {})
        ) != self.dependencies(run["stage"], snapshot):
            return False
        for aid in run["outputs"].get("artifacts", []):
            rows = self.rows("SELECT path,sha256 FROM artifacts WHERE id=?", (aid,))
            if not rows:
                return False
            path = safe(self.root(run["project_id"]), rows[0]["path"])
            if not path.is_file() or digest(path) != rows[0]["sha256"]:
                return False
        return True

    def gate(self, pid, stage, snapshot):
        # Every mutation conservatively invalidates dependent approvals; stage output snapshots
        # carry previous evidence forward only when generated by a valid sequential run.
        rows = self.rows(
            "SELECT id FROM runs WHERE project_id=? AND stage=? AND kind IN ('agent','render','qa','package','article','article-plan') ORDER BY created DESC",
            (pid, stage),
        )
        if not rows:
            return False
        run = self.run(rows[0]["id"])
        if not self.valid(run, snapshot):
            return False
        if stage in GATES and not (
            stage == "timing"
            and self.project(pid)["config"].get("audio_mode") == "none"
        ):
            reviews = self.rows(
                "SELECT decision FROM reviews WHERE run_id=? ORDER BY created DESC LIMIT 1",
                (run["id"],),
            )
            return bool(reviews and reviews[0]["decision"] == "approve")
        return run["status"] == "succeeded"

    def create_run(self, pid, stage, kind, idem, payload, retry_of=None):
        snap = self.scan(pid)
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT id FROM runs WHERE project_id=? AND idem=?", (pid, idem)
            ).fetchone()
            if existing:
                old = self.run(existing["id"])
                if (old["stage"], old["kind"], old["payload"]) != (
                    stage,
                    kind,
                    payload,
                ):
                    raise ValueError("幂等键已被其他请求使用")
                return old
            if self.active(c, pid):
                raise ValueError("项目已有排队或运行任务")
            if kind == "agent" and STAGES.index(stage) > 0:
                prev = STAGES[STAGES.index(stage) - 1]
                if not self.gate(pid, prev, snap):
                    raise ValueError(f"先完成或重新确认：{LABELS[STAGES.index(prev)]}")
            if kind in ("render", "package"):
                required = {"render": "preview", "package": "render"}[
                    kind
                ]
                if not self.gate(pid, required, snap):
                    raise ValueError(f"先完成有效的 {required} 检查或确认")
            if kind == "article-plan":
                from adapters.article_plan import read_article
                if stage != "content":
                    raise ValueError("文章拆解属于内容设计阶段")
                read_article(self.root(pid), payload.get("article_path"))
            if kind == "article":
                from adapters.article_video import validate_recipe
                recipe_path = payload.get("recipe_path", "")
                if not isinstance(recipe_path, str) or not recipe_path.startswith("assets/") or not recipe_path.endswith("-video-recipe.json"):
                    raise ValueError("请选择已导入的文章制作方案")
                recipe = safe(self.root(pid), recipe_path)
                if not recipe.is_file() or recipe.stat().st_size > 2_000_000:
                    raise ValueError("文章制作方案不存在或过大")
                validate_recipe(json.loads(recipe.read_text()))
            if kind == "qa":
                # Inspect an existing immutable file independently of production gates.
                # This does not approve preview or waive the post-QA human review.
                artifact = c.execute(
                    "SELECT path,sha256 FROM artifacts WHERE id=? AND project_id=?",
                    (payload.get("artifact_id"), pid),
                ).fetchone()
                if not artifact:
                    raise ValueError("请选择本项目的有效视频产物")
                source = safe(self.root(pid), artifact["path"])
                if source.suffix.lower() not in (".mp4", ".webm", ".mov"):
                    raise ValueError("技术复检仅支持视频文件")
                if not source.is_file() or digest(source) != artifact["sha256"]:
                    raise ValueError("视频文件已变化或不存在，请重新登记后检查")
            rid = uid()
            c.execute(
                "INSERT INTO runs(id,project_id,stage,kind,status,idem,payload,inputs,created,retry_of) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    pid,
                    stage,
                    kind,
                    "queued",
                    idem,
                    dumps(payload),
                    dumps(snap),
                    now(),
                    retry_of,
                ),
            )
            self.event(c, pid, rid, "run.queued", {"stage": stage, "kind": kind})
        self.export_status(pid)
        return self.run(rid)

    def review(self, rid, decision, note):
        run = self.run(rid)
        snap = self.scan(run["project_id"])
        if run["status"] != "awaiting_review":
            raise ValueError("该任务不在待确认状态")
        if not self.valid(run, snap):
            raise ValueError("输入或文件已变化，请重新执行受影响阶段")
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if self.active(c, run["project_id"]):
                raise ValueError("请等待当前任务结束后确认")
            if (
                c.execute("SELECT status FROM runs WHERE id=?", (rid,)).fetchone()[
                    "status"
                ]
                != "awaiting_review"
            ):
                raise ValueError("该版本已被处理，请刷新")
            if not self.valid(run, self.snapshot(run["project_id"])):
                raise ValueError("确认期间输入发生变化，请重新检查")
            c.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?)",
                (uid(), rid, decision, note, now()),
            )
            c.execute(
                "UPDATE runs SET status=?,message=? WHERE id=?",
                ("succeeded" if decision == "approve" else "blocked", note, rid),
            )
            self.event(
                c,
                run["project_id"],
                rid,
                "review.recorded",
                {"decision": decision, "note": note},
            )
        self.export_status(run["project_id"])

    def cancel(self, rid):
        r = self.run(rid)
        with self.conn() as c:
            c.execute(
                "UPDATE runs SET status='cancelled',message='用户取消' WHERE id=? AND status IN ('queued','running')",
                (rid,),
            )
            self.event(c, r["project_id"], rid, "run.cancelled", {})
        return self.run(rid)

    def files(self, pid):
        root = self.root(pid)
        self.scan(pid)
        return [
            {
                "path": str(f.relative_to(root)),
                "revision": digest(f),
                "size": f.stat().st_size,
            }
            for folder in CONTENT_DIRS
            for f in sorted((root / folder).rglob("*"))
            if f.is_file() and not f.is_symlink() and "node_modules" not in f.parts
        ]

    def save(self, pid, path, content, revision):
        root = self.root(pid)
        f = safe(root, path)
        if (
            Path(path).parts[0] not in CONTENT_DIRS
            or f.suffix not in EDITABLE
            or f.name == "STATUS.md"
        ):
            raise ValueError("此文件不能在编辑器中修改")
        if f.suffix == ".json":
            json.loads(content)
        if f.suffix == ".srt":
            from adapters.captions import parse_srt

            parse_srt(content)
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if self.active(c, pid):
                raise ValueError("运行期间不可修改输入；请先取消或等待完成")
            actual = digest(f) if f.exists() else None
            if actual != revision:
                raise ValueError("版本冲突：请重新加载文件")
            if f.exists():
                backup = root / "runs" / "edits" / uid() / path
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, backup)
            atomic(f, content)
            self.event(c, pid, None, "document.saved", {"path": path})
        self.scan(pid)
        self.export_status(pid)
        return {"revision": digest(f)}

    def export_status(self, pid):
        rows = self.rows(
            "SELECT stage,status,message,id FROM runs WHERE project_id=? ORDER BY created DESC LIMIT 15",
            (pid,),
        )
        text = "# 制作状态（平台生成）\n\n数据库是运行和确认状态来源。文件变化会使依赖它的检查失效。\n\n"
        text += "\n".join(
            f"- {r['stage']} · {r['status']} · {r['message']} · {r['id']}" for r in rows
        )
        events = self.rows(
            "SELECT data FROM events WHERE project_id=? AND kind='automation.stage' ORDER BY id DESC LIMIT 100",
            (pid,),
        )
        if events:
            text += "\n\n## 授权自动制作记录\n\n自动完成不代表人工试听或确认；人工确认仍以 reviews 为准。\n\n"
            latest = {}
            for event in events:
                data = json.loads(event['data'])
                latest.setdefault(data['stage'], data)
            for stage in STAGES:
                if stage in latest:
                    data = latest[stage]
                    text += f"- {stage} · {data['status']} · {data.get('details', '')}\n"
        atomic(self.root(pid) / "documents" / "STATUS.md", text)

    def services(self):
        return {
            r["name"]: json.loads(r["config"])
            for r in self.rows("SELECT * FROM services")
        }
