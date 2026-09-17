"""Import existing trial evidence without creating or approving production stages."""

import sys, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.server.core import Store, ROOT, uid, digest, now

s = Store()
for branch in ("marketing", "teaching"):
    projects = s.rows(
        "SELECT id FROM projects WHERE branch=? ORDER BY created LIMIT 1", (branch,)
    )
    if not projects:
        continue
    pid = projects[0]["id"]
    root = s.root(pid)
    source = ROOT / "workspace/trials" / branch
    dst = root / "exports/trials"
    shutil.copytree(source, dst, dirs_exist_ok=True)
    with s.conn() as c:
        for f in dst.rglob("*"):
            if f.is_file() and f.suffix in (".mp4", ".json", ".jpg", ".md"):
                rel = str(f.relative_to(root))
                sha = digest(f)
                if not c.execute(
                    "SELECT 1 FROM artifacts WHERE project_id=? AND path=? AND sha256=?",
                    (pid, rel, sha),
                ).fetchone():
                    c.execute(
                        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                        (uid(), pid, None, rel, sha, "trial", now()),
                    )
        s.event(
            c,
            pid,
            None,
            "trial.imported",
            {"status": "needs_human_review", "production_gates": "not_approved"},
        )
    print(branch, pid)
