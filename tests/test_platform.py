import json, time, subprocess, sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.server.core import Store, uid, dumps, digest, safe, now
from apps.server.main import create_app
from worker.main import Worker
from adapters.captions import parse_srt
from adapters.tools import process, Cancelled


@pytest.fixture
def env(tmp_path):
    s = Store(tmp_path / "workspace")
    c = TestClient(create_app(s))
    c.get("/api/session")
    c.headers["x-video-request"] = "workbench"
    p = s.create("测试教学", "teaching", {})
    return s, c, p["id"]


def finish(s, r, status="succeeded"):
    with s.conn() as c:
        c.execute(
            "UPDATE runs SET status=?,outputs=? WHERE id=?",
            (
                status,
                dumps({"snapshot": s.snapshot(r["project_id"]), "artifacts": []}),
                r["id"],
            ),
        )


def test_auth_and_origin(env):
    s, c, p = env
    c.cookies.clear()
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/session", headers={"host": "evil.test"}).status_code == 403
    c.get("/api/session")
    assert (
        c.post(
            "/api/services/probe", headers={"origin": "https://evil.test"}
        ).status_code
        == 403
    )


def test_templates_and_version_conflict(env):
    s, c, p = env
    doc = c.get(
        f"/api/projects/{p}/document", params={"path": "documents/BRIEF.md"}
    ).json()
    assert (
        c.put(
            f"/api/projects/{p}/document", json={**doc, "content": "# 修订"}
        ).status_code
        == 200
    )
    assert (
        c.put(
            f"/api/projects/{p}/document", json={**doc, "content": "# 旧版本"}
        ).status_code
        == 409
    )
    assert (
        c.get(
            f"/api/projects/{p}/document", params={"path": "../../session.token"}
        ).status_code
        == 409
    )
    assert (s.root(p) / "documents/LESSON-PLAN.md").exists()


def test_idempotency_and_stage_gate(env):
    s, c, p = env
    with pytest.raises(ValueError):
        s.create_run(p, "content", "agent", "first", {})
    r = s.create_run(p, "brief", "agent", "same", {})
    assert s.create_run(p, "brief", "agent", "same", {})["id"] == r["id"]
    with pytest.raises(ValueError):
        s.create_run(p, "brief", "agent", "same", {"instruction": "different"})
    with pytest.raises(ValueError):
        s.create_run(p, "brief", "agent", "another", {})
    finish(s, r)
    content = s.create_run(p, "content", "agent", "content", {})
    finish(s, content, "awaiting_review")
    with pytest.raises(ValueError):
        s.create_run(p, "storyboard", "agent", "story", {})
    s.review(content["id"], "approve", "检查脚本")
    assert s.create_run(p, "storyboard", "agent", "story", {})["status"] == "queued"


def test_change_invalidates_review(env):
    s, c, p = env
    r = s.create_run(p, "brief", "agent", "a", {})
    finish(s, r)
    r = s.create_run(p, "content", "agent", "b", {})
    finish(s, r, "awaiting_review")
    f = s.root(p) / "documents/SCRIPT.md"
    f.write_text("外部修改")
    with pytest.raises(ValueError):
        s.review(r["id"], "approve", "")
    assert c.get(f"/api/projects/{p}").json()["runs"][0]["stale"]


def test_lease_and_cancel(env):
    s, c, p = env
    r = s.create_run(p, "brief", "agent", "a", {})
    w = Worker(s)
    assert w.claim()["id"] == r["id"]
    with s.conn() as db:
        db.execute("UPDATE runs SET heartbeat=? WHERE id=?", (now() - 60, r["id"]))
    assert w.claim() is None
    assert s.run(r["id"])["status"] == "blocked"
    r = s.create_run(p, "brief", "agent", "b", {})
    s.cancel(r["id"])
    assert w.claim() is None


def test_process_cancel(tmp_path):
    begin = time.monotonic()
    with pytest.raises(Cancelled):
        process(
            [sys.executable, "-c", "import time;time.sleep(60)"],
            tmp_path,
            tmp_path / "log",
            cancel=lambda: time.monotonic() - begin > 0.4,
        )
    assert time.monotonic() - begin < 8


def test_srt():
    good = "1\n00:00:01,000 --> 00:00:02,500\n你好\n\n2\n00:00:02,500 --> 00:00:04,000\n结果"
    assert parse_srt(good)[0]["duration_s"] == 1.5
    with pytest.raises(ValueError):
        parse_srt(good.replace("00:00:02,500 -->", "00:00:01,500 -->"))
    with pytest.raises(ValueError):
        parse_srt("1\n00:60:01,000 --> 00:61:00,000\n不合法")


def test_asset_boundary_and_upload(env, tmp_path):
    s, c, p = env
    link = s.root(p) / "assets/link"
    link.symlink_to(tmp_path)
    with pytest.raises(ValueError):
        safe(s.root(p), "assets/link/private")
    link.unlink()
    r = c.post(
        f"/api/projects/{p}/assets?folder=captions",
        files={"file": ("wrong.srt", b"invalid", "text/plain")},
    )
    assert r.status_code == 409
    assert not list((s.root(p) / "captions").iterdir())


def test_worker_blocks_changed_queued_inputs(env):
    s, c, p = env
    r = s.create_run(p, "brief", "agent", "a", {})
    (s.root(p) / "documents/BRIEF.md").write_text("新输入")
    w = Worker(s)
    w.execute(w.claim())
    assert s.run(r["id"])["status"] == "blocked"
    assert "输入已变化" in s.run(r["id"])["message"]


def test_audio_does_not_invalidate_content_approval(env):
    s, c, p = env
    r = s.create_run(p, "brief", "agent", "a", {})
    finish(s, r)
    r = s.create_run(p, "content", "agent", "b", {})
    finish(s, r, "awaiting_review")
    s.review(r["id"], "approve", "")
    (s.root(p) / "audio/new.wav").write_bytes(b"audio fixture")
    assert s.gate(p, "content", s.snapshot(p))
    (s.root(p) / "documents/SCRIPT.md").write_text("旁白改写")
    assert not s.gate(p, "content", s.snapshot(p))


def test_old_hash_not_accepted_after_reencode(env):
    s, c, p = env
    r = s.create_run(p, "brief", "agent", "a", {})
    finish(s, r, "awaiting_review")
    out = s.root(p) / "runs" / r["id"] / "final.mp4"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"original")
    aid = uid()
    with s.conn() as db:
        db.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
            (
                aid,
                p,
                r["id"],
                str(out.relative_to(s.root(p))),
                digest(out),
                "output",
                now(),
            ),
        )
        db.execute(
            "UPDATE runs SET outputs=? WHERE id=?",
            (dumps({"snapshot": s.snapshot(p), "artifacts": [aid]}), r["id"]),
        )
    out.write_bytes(b"reencoded")
    assert not s.valid(s.run(r["id"]), s.snapshot(p))
    assert c.get(f"/api/artifacts/{aid}/file").status_code == 409


def test_worker_agent_contract_and_promotion(env, monkeypatch):
    import worker.main as wm

    s, c, p = env

    def fake(argv, cwd, log, *args, **kwargs):
        (cwd / "documents/BRIEF.md").write_text("# 已根据输入整理")
        result = Path(argv[argv.index("-o") + 1])
        result.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "summary": "完成简报",
                    "artifacts": ["documents/BRIEF.md"],
                    "review_notes": [],
                    "blockers": [],
                }
            )
        )
        log.write_text("fixture")
        return ""

    monkeypatch.setattr(wm, "process", fake)
    r = s.create_run(p, "brief", "agent", "a", {})
    w = Worker(s)
    w.execute(w.claim())
    assert s.run(r["id"])["status"] == "succeeded"
    assert (s.root(p) / "documents/BRIEF.md").read_text() == "# 已根据输入整理"
    assert s.run(r["id"])["outputs"]["artifacts"]


def test_worker_never_accepts_missing_result(env, monkeypatch):
    import worker.main as wm

    s, c, p = env
    monkeypatch.setattr(wm, "process", lambda *args, **kwargs: "")
    r = s.create_run(p, "brief", "agent", "a", {})
    w = Worker(s)
    w.execute(w.claim())
    assert s.run(r["id"])["status"] == "failed"
    assert not s.run(r["id"])["outputs"]


def test_sqlite_backup_restore(env, tmp_path):
    import os

    s, c, p = env
    backup = tmp_path / "backup.zip"
    target = tmp_path / "restored"
    subprocess.run(
        [sys.executable, "scripts/manage.py", "backup", "--file", str(backup)],
        env={**os.environ, "VIDEO_WORKSPACE": str(s.home)},
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "scripts/manage.py", "restore", "--file", str(backup)],
        env={**os.environ, "VIDEO_WORKSPACE": str(target)},
        check=True,
        capture_output=True,
    )
    restored = Store(target)
    assert restored.project(p)["name"] == "测试教学"
    assert restored.snapshot(p) == s.snapshot(p)
    assert restored.token != s.token


def test_silent_timing_needs_no_voice_review(env):
    s, c, p = env
    with s.conn() as db:
        db.execute(
            "UPDATE projects SET config=? WHERE id=?",
            (dumps({"audio_mode": "none"}), p),
        )
    r = s.create_run(p, "brief", "agent", "silent", {})
    with s.conn() as db:
        db.execute("UPDATE runs SET stage='timing' WHERE id=?", (r["id"],))
    finish(s, s.run(r["id"]))
    assert s.gate(p, "timing", s.snapshot(p))


def test_timing_mismatch_blocks_render(tmp_path):
    from adapters.timing import check_timing

    timing = tmp_path / "timing.json"
    html = tmp_path / "index.html"
    timing.write_text(
        json.dumps(
            {
                "fps": 30,
                "total_duration_s": 3,
                "shots": [{"shot_id": "SH01", "start_s": 0, "duration_s": 3}],
            }
        )
    )
    html.write_text(
        '<div data-composition-id="main" data-duration="3"><section data-shot-id="SH01" data-start="0" data-duration="3"></section></div>'
    )
    assert check_timing(timing, html)["status"] == "pass"
    html.write_text(html.read_text().replace('data-start="0"', 'data-start="1"'))
    with pytest.raises(ValueError):
        check_timing(timing, html)


def test_handoff_rejects_missing_available_asset(env):
    from adapters.handoff import validate_handoff

    s, c, p = env
    root = s.root(p)
    (root / "documents/assets-manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "A01",
                        "path": "assets/missing.png",
                        "status": "available",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        validate_handoff(root)


def test_artifact_listing_deduplicates_and_marks_stale(env):
    s, c, p = env
    f = s.root(p) / 'exports/example.zip'
    f.write_bytes(b'old')
    old = digest(f)
    f.write_bytes(b'new')
    new = digest(f)
    with s.conn() as db:
        for sha in (old,new,new):
            db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)', (uid(),p,None,'exports/example.zip',sha,'automated_delivery',now()))
    rows = [a for a in c.get(f'/api/projects/{p}').json()['artifacts'] if a['path']=='exports/example.zip']
    assert len(rows)==2
    assert [a['available'] for a in rows if a['sha256']==new]==[True]
    assert [a['available'] for a in rows if a['sha256']==old]==[False]
    stale=next(a for a in rows if not a['available'])
    assert c.get(f"/api/artifacts/{stale['id']}/file").status_code==409


def test_existing_video_qa_does_not_require_preview_but_render_does(env):
    s, c, p = env
    video = s.root(p) / "exports/existing.mp4"
    video.write_bytes(b"test-fixture")
    aid = uid()
    with s.conn() as db:
        db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                   (aid,p,None,"exports/existing.mp4",digest(video),"automated_delivery",now()))
    with pytest.raises(ValueError, match="preview"):
        s.create_run(p,"render","render","render-blocked",{})
    run = s.create_run(p,"render","qa","qa-existing",{"artifact_id":aid})
    assert run["status"] == "queued"
    assert not s.gate(p,"preview",s.snapshot(p))
    assert s.rows("SELECT * FROM reviews") == []


def test_existing_video_qa_rejects_stale_or_foreign_artifact(env):
    s, c, p = env
    with pytest.raises(ValueError, match="有效视频"):
        s.create_run(p,"render","qa","missing",{"artifact_id":"missing"})
    video = s.root(p) / "exports/existing.mp4"
    video.write_bytes(b"old")
    aid = uid()
    with s.conn() as db:
        db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                   (aid,p,None,"exports/existing.mp4",digest(video),"automated_delivery",now()))
    video.write_bytes(b"new")
    with pytest.raises(ValueError, match="已变化"):
        s.create_run(p,"render","qa","stale",{"artifact_id":aid})
