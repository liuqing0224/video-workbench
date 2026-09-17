#!/usr/bin/env python3
"""本机启动、停止、备份与离线恢复。"""

import argparse, fcntl, os, signal, sqlite3, subprocess, sys, time, zipfile, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.server.core import Store, ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["start", "stop", "backup", "restore"])
    p.add_argument("--file")
    p.add_argument("--port", type=int, default=8794)
    args = p.parse_args()
    s = Store()
    pids = s.home / "processes.txt"
    if args.action == "start":
        if pids.exists():
            raise SystemExit("已有启动记录，请先运行 stop")
        processes = []
        try:
            for name, cmd in [
                (
                    "api",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "apps.server.main:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.port),
                    ],
                ),
                ("worker", [sys.executable, "-m", "worker.main"]),
            ]:
                with (s.home / f"{name}.log").open("a") as log:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=ROOT,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                processes.append(proc)
            time.sleep(1)
            if any(x.poll() is not None for x in processes):
                raise RuntimeError("服务未启动，检查 workspace 日志")
            pids.write_text("\n".join(str(x.pid) for x in processes))
            print(f"http://127.0.0.1:{args.port}")
        except:
            for proc in processes:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
            raise
    elif args.action == "stop":
        if pids.exists():
            for pid in map(int, pids.read_text().split()):
                try:
                    # Do not terminate a recycled unrelated PID.
                    info = subprocess.check_output(
                        ["ps", "-p", str(pid), "-o", "command="], text=True
                    )
                    if "apps.server.main:" in info or "worker.main" in info:
                        os.killpg(pid, signal.SIGTERM)
                        for _ in range(50):
                            try:
                                os.kill(pid, 0)
                            except ProcessLookupError:
                                break
                            time.sleep(0.1)
                except (ProcessLookupError, subprocess.CalledProcessError):
                    pass
            pids.unlink()
        print("已停止启动脚本登记的服务")
    elif args.action == "backup":
        if not args.file:
            raise SystemExit("需要 --file /absolute/backup.zip")
        if pids.exists():
            raise SystemExit("先 stop，再备份，确保文件与数据库一致")
        lock = (s.home / "worker.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Worker 正在运行，请先停止")
        if s.rows("SELECT 1 FROM runs WHERE status='running'"):
            raise SystemExit("仍有运行任务，先恢复为中断状态")
        dest = Path(args.file).resolve()
        if dest.is_relative_to(s.home):
            raise SystemExit("备份文件必须在 workspace 外")
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "platform.sqlite"
            with sqlite3.connect(s.db) as src, sqlite3.connect(db) as dst:
                src.backup(dst)
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(db, "platform.sqlite")
                for f in (s.home / "projects").rglob("*"):
                    if f.is_symlink():
                        raise SystemExit("不备份符号链接")
                    if f.is_file() and "node_modules" not in f.parts:
                        z.write(f, str(f.relative_to(s.home)))
        print(dest)
    else:
        if not args.file:
            raise SystemExit("需要 --file backup.zip")
        if pids.exists() or s.rows("SELECT 1 FROM projects LIMIT 1"):
            raise SystemExit(
                "仅恢复到停止且无项目的新 workspace；用 VIDEO_WORKSPACE 指定目标"
            )
        with zipfile.ZipFile(args.file) as z:
            for item in z.infolist():
                target = (s.home / item.filename).resolve()
                if (
                    not target.is_relative_to(s.home)
                    or (item.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise SystemExit("非法归档成员")
                if item.filename != "platform.sqlite" and not item.filename.startswith(
                    "projects/"
                ):
                    raise SystemExit("归档范围错误")
            z.extractall(s.home)
        # Clear WAL from the empty destination; session tokens are deliberately not restored.
        for suffix in ("-wal", "-shm"):
            Path(str(s.db) + suffix).unlink(missing_ok=True)
        with sqlite3.connect(s.db) as c:
            c.execute(
                "UPDATE runs SET status='blocked',message='从备份恢复，需核对后重试' WHERE status IN ('running','queued')"
            )
        print("恢复完成；请启动平台核对项目")


if __name__ == "__main__":
    main()
