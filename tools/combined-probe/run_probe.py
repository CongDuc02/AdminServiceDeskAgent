#!/usr/bin/env python3
"""Điều phối phép đo `combined_main` (B9a2; O1-6, A-095) từ MÁY NGƯỜI TRIỂN KHAI — chỉ thư viện chuẩn, gọi `docker`. KHÔNG phải mã ứng dụng.

Dựng: một PostgreSQL tạm (container `pg` có sẵn), một bucket SeaweedFS tạm (`bo19-s3`), một máy chủ LLM giả HTTPS (trễ 2 s mỗi lời gọi), và `combined_main` — PID 1 của một container từ IMAGE RUNTIME thật —
giới hạn `--cpus=0.1 --memory=512m` như Render free. Đo:
  A. thời gian lên (`/healthz`);
  B. một lượt chat KHÔNG có chuyển đổi (nền);
  C. ba lượt chat trong lúc `soffice` chuyển đổi (job `render_document`), so với hạn chót lượt WV-02 = 20 s (biên WV-03 = 10 s);
  D. `SIGTERM` (`docker kill -s TERM`, như Render) khi `soffice` đang chạy: thời gian tới khi container thoát, bảng tiến trình (`docker top`) theo thời gian, nhân chứng `pg_stat_activity` (`s4_witness_poll.py`),
     log `JOB_RELEASED_ON_DRAIN` / `PROCESS_TABLE_AT_EXIT` / `PROCESS_EXIT`, và trạng thái job sau đó (`QUEUED`, `attempts` không đổi);
  E. bộ nhớ: đỉnh cgroup (`memory.peak`), `oom_kill`, RSS đỉnh của PID 1.
Kết quả JSON ở `tools/combined-probe/out/result.json`; bản đọc được do người chạy dán vào `docs/reference/combined-main-b9a2.md`.

Điều kiện: image `bo19-runtime` và `bo19-test` đã dựng từ commit đang đo; container `pg`, `bo19-s3` chạy trên network `ci`; file env S3 test (`--s3-env`, ngoài repo).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
NET = "ci"
NL = chr(10)
COMBINED, LLM, POLL = "probe-combined", "probe-llm", "probe-poll"
PORT = 10000
BASE = f"http://{COMBINED}:{PORT}"


def sh(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=check, timeout=timeout)


def tool(s3_env: str, *args: str, detach: bool = False, name: str | None = None, alias: str | None = None, extra: tuple[str, ...] = (), timeout: float = 900) -> subprocess.CompletedProcess:
    cmd = ["run", "--rm" if not detach else "-d", "--network", NET, "--env-file", s3_env, "-v", f"{REPO}:/repo:ro", "-v", f"{OUT}:/out", "-w", "/repo",
           "-e", "PYTHONPATH=/repo/backend/src", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "BO19_TRIAL_PG_ADMIN_DSN=postgresql://postgres@pg:5432/postgres", *extra]
    if name:
        cmd += ["--name", name]
    if alias:
        cmd += ["--network-alias", alias]
    cmd += ["--entrypoint", "python", "bo19-test", *args]
    return sh(*cmd, timeout=timeout)


def jlast(text: str) -> dict:
    for line in reversed([l for l in text.splitlines() if l.strip().startswith("{")]):
        return json.loads(line)
    raise RuntimeError(f"không có JSON trong đầu ra: {text[-500:]}")


def top() -> list[dict]:
    r = sh("top", COMBINED, "-eo", "pid,ppid,stat,comm", check=False)
    rows = []
    for line in r.stdout.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) == 4:
            rows.append({"pid": int(parts[0]), "ppid": int(parts[1]), "stat": parts[2], "comm": parts[3]})
    return rows


def running() -> bool:
    return sh("inspect", "-f", "{{.State.Running}}", COMBINED, check=False).stdout.strip() == "true"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--s3-env", required=True, help="file env S3 test (BO19_TEST_S3_*), ngoài repo")
    ap.add_argument("--cpus", default="0.1")
    ap.add_argument("--memory", default="512m")
    ap.add_argument("--keep", action="store_true", help="không dọn container/DB sau khi đo")
    ap.add_argument("--image", default="bo19-runtime", help="image runtime để đo (so trước/sau: dựng hai tag từ hai commit)")
    ap.add_argument("--label", default="", help="nhãn ghi vào kết quả")
    ap.add_argument("--cpuset", default="", help="ghim container vào CPU này (docker --cpuset-cpus), ví dụ 0 — thử nghiệm: `nice` chỉ có tác dụng khi hai tiến trình chung một runqueue")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*"):
        if f.is_file():
            f.unlink()
    res: dict = {"cpuset": a.cpuset, "image": a.image, "label": a.label, "cpus": a.cpus, "memory": a.memory, "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    for c in (COMBINED, LLM, POLL):
        sh("rm", "-f", c, check=False)
    try:
        res["setup"] = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "setup").stdout)
        tool(a.s3_env, "tools/combined-probe/combined_probe.py", "llm", detach=True, name=LLM, alias="llm.probe.test")
        # nhân chứng pg_stat_activity — chỉ đọc, role bo19_app (trust) của DB tạm
        app_dsn = json.loads((OUT / "state.json").read_text(encoding="utf-8"))["app_dsn"]
        sh("run", "-d", "--name", POLL, "--network", NET, "-v", f"{REPO}:/repo:ro", "-v", f"{OUT}:/out", "-e", f"BO19_S4_POLL_DSN={app_dsn}", "-e", "PYTHONPATH=/repo/backend/src",
           "--entrypoint", "sh", "bo19-test", "-c", "python /repo/tools/render-probes/s4_witness_poll.py --duration 3000 --interval 0.25 --like 'bo19-combined%' > /out/poll.jsonl")

        # `ProviderClient` dùng `trust_env=False` (không đọc SSL_CERT_FILE): chứng chỉ giả phải nằm trong bộ CA của certifi. Dựng bộ CA = bộ của image + chứng chỉ giả, gắn đè lên đúng file đó.
        ca = sh("run", "--rm", "--entrypoint", "python", a.image, "-c", "import certifi,sys;sys.stdout.write(certifi.where()+chr(10)+open(certifi.where(),encoding='utf-8').read())").stdout
        ca_path, _, ca_body = ca.partition(NL)
        (OUT / "cacert.pem").write_text(ca_body.rstrip(NL) + NL + (OUT / "llm-cert.pem").read_text(encoding="utf-8"), encoding="utf-8")
        t0 = time.monotonic()
        sh("run", "-d", "--name", COMBINED, "--network", NET, "--cpus", a.cpus, *(["--cpuset-cpus", a.cpuset] if a.cpuset else []), "--memory", a.memory, "--memory-swap", a.memory, "--env-file", str(OUT / "probe.env"),
           "-v", f"{OUT}:/out:ro", "-v", f"{OUT / 'cacert.pem'}:{ca_path.strip()}:ro", a.image, "python", "-m", "bo19.entrypoints.combined_main")
        res["A_startup"] = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "health", "--base", BASE, "--timeout", "420").stdout)
        res["A_startup"]["wall_s"] = round(time.monotonic() - t0, 1)
        res["pid1"] = top()[:1]

        # B. nền — không có chuyển đổi
        res["B_baseline_turns"] = [jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "turn", "--base", BASE, "--employee", "GIA-0001").stdout) for _ in range(2)]

        # F. job render MỘT MÌNH (không có lượt chat nào): thời gian từ lúc gửi tới lúc `SUCCEEDED` — cái giá của việc hạ ưu tiên `soffice`
        rid0 = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "submit").stdout)["request_id"]
        t_job = time.monotonic()
        while time.monotonic() - t_job < 400 and jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "job", "--request", rid0).stdout)["job"] != "SUCCEEDED":
            time.sleep(1)
        res["F_job_alone_s"] = round(time.monotonic() - t_job, 1)

        # C. lượt chat TRONG LÚC `soffice` chuyển đổi — gom đủ >= 3 lượt có `soffice` chạy cả TRƯỚC và SAU lượt (gửi thêm job khi chuyển đổi xong mà chưa đủ)
        def soffice_up() -> bool:
            return any(r["comm"].startswith("soffice") or r["comm"] == "oosplash" for r in top())

        turns, valid, rid, jobs_sent = [], [], None, 0
        while len(valid) < 3 and len(turns) < 14:
            if not soffice_up():
                if jobs_sent >= 4:
                    break
                rid = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "submit").stdout)["request_id"]
                jobs_sent += 1
                t_sub = time.monotonic()
                while time.monotonic() - t_sub < 240 and not soffice_up():
                    time.sleep(0.3)
            before = soffice_up()
            turn = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "turn", "--base", BASE, "--employee", "GIA-0002").stdout)
            turn["soffice_running_before"], turn["soffice_running_after"] = before, soffice_up()
            turns.append(turn)
            if before and turn["soffice_running_after"] and turn["turn_s"] is not None:
                valid.append(turn["turn_s"])
        res["C_turns_during_conversion"] = turns
        res["C_valid_turn_s"] = valid
        res["C_jobs_sent"] = jobs_sent
        res["C_job_before_sigterm"] = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "job", "--request", rid).stdout) if rid else None
        res["E_memory"] = memory()

        # D. SIGTERM khi soffice còn chạy. Chuyển đổi của job trên có thể đã xong lúc này (các lượt chat chiếm vài chục giây) — khi đó gửi một job mới và chờ `soffice` xuất hiện, rồi mới gửi SIGTERM.
        if not any(r["comm"].startswith("soffice") for r in top()):
            rid = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "submit").stdout)["request_id"]
            res["D_request"] = rid
            t_sub = time.monotonic()
            while time.monotonic() - t_sub < 240 and not any(r["comm"].startswith("soffice") for r in top()):
                time.sleep(0.3)
        rows_before = top()
        res["D_soffice_running_at_sigterm"] = any(r["comm"].startswith("soffice") for r in rows_before)
        res["D_table_before"] = rows_before
        res["vm_clock_skew_s"] = skew = vm_clock_skew()
        t_kill = datetime.fromtimestamp(time.time() + skew, timezone.utc)  # giờ theo đồng hồ của VM, để so với dòng poll và log
        t_kill_m = time.monotonic()
        sh("kill", "-s", "TERM", COMBINED)
        snaps = []
        exit_seen = None
        while time.monotonic() - t_kill_m < 40:
            rows = top()
            snaps.append({"t_s": round(time.monotonic() - t_kill_m, 2), "procs": [f"{r['pid']}/{r['stat']}/{r['comm']}" for r in rows]})
            if not running():
                exit_seen = time.monotonic() - t_kill_m
                break
        res["D_exit_seen_after_s"] = None if exit_seen is None else round(exit_seen, 2)
        res["D_snapshots"] = snaps
        res["D_sigterm_at"] = t_kill.isoformat(timespec="milliseconds")
        res["D_exit_code"] = sh("inspect", "-f", "{{.State.ExitCode}}", COMBINED, check=False).stdout.strip()
        logs = sh("logs", COMBINED, check=False)
        text = logs.stdout + logs.stderr
        res["cpu_pin_log"] = [l for l in text.splitlines() if '"CPU_PIN' in l]
        keep = ("SIGTERM_RECEIVED", "JOB_RELEASED_ON_DRAIN", "PROCESS_TABLE_AT_EXIT", "PROCESS_EXIT", "WORKER_LOOP_STOP", "JOB_START", "JOB_HANDLER_CRASHED", "DRAIN_HOOK_ERROR", "JOB_POLL_NOT_STOPPED")
        llm_calls = [json.loads(l) for l in (OUT / "llm.jsonl").read_text(encoding="utf-8").splitlines()] if (OUT / "llm.jsonl").exists() else []
        res["llm_server_calls"] = {n: sum(1 for c in llm_calls if c["call"] == n) for n in sorted({c["call"] for c in llm_calls})}
        res["llm_log_messages"] = sorted({re.search(r'"message":"([A-Z_0-9]+)"', l).group(1) for l in text.splitlines() if re.search(r'"message":"LLM_[A-Z_0-9]+"', l)})
        res["D_log_lines"] = [l for l in text.splitlines() if any(f'"{k}"' in l for k in keep)]
        time.sleep(1)
        res["D_job_after"] = jlast(tool(a.s3_env, "tools/combined-probe/combined_probe.py", "job", "--request", rid).stdout)
        sh("kill", POLL, check=False)
        poll = (OUT / "poll.jsonl").read_text(encoding="utf-8").splitlines() if (OUT / "poll.jsonl").exists() else []
        res["D_witness"] = witness(poll, t_kill)
    finally:
        (OUT / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        if not a.keep:
            tool(a.s3_env, "tools/combined-probe/combined_probe.py", "cleanup")
            for c in (COMBINED, LLM, POLL):
                sh("rm", "-f", c, check=False)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def vm_clock_skew() -> float:
    """Độ lệch đồng hồ máy ảo Docker so với máy chủ (giây; dương = VM đi trước), ước lượng bằng một `docker exec` ở giữa hai lần đọc giờ máy chủ."""
    t0 = time.time()
    r = sh("exec", LLM, "python", "-c", "import time;print(time.time())", check=False)
    t1 = time.time()
    return round(float(r.stdout.strip()) - (t0 + t1) / 2, 3)


def memory() -> dict:
    code = ("import json;r=lambda p:open(p).read().strip();"
            "s=dict(l.split(':',1) for l in open('/proc/1/status') if ':' in l);"
            "print(json.dumps({'cgroup_memory_peak_mib':round(int(r('/sys/fs/cgroup/memory.peak'))/2**20,1),'cgroup_memory_now_mib':round(int(r('/sys/fs/cgroup/memory.current'))/2**20,1),"
            "'oom_kill':[l for l in r('/sys/fs/cgroup/memory.events').splitlines() if l.startswith('oom_kill')],'pid1_vmhwm_mib':round(int(s['VmHWM'].split()[0])/1024,1),'pid1_vmrss_mib':round(int(s['VmRSS'].split()[0])/1024,1)}))")
    r = sh("exec", COMBINED, "python", "-c", code, check=False)
    try:
        return jlast(r.stdout)
    except RuntimeError:
        return {"error": (r.stderr or r.stdout)[-300:]}


def witness(lines: list[str], t_kill: datetime) -> dict:
    """Từ dòng poll của `s4_witness_poll.py --like 'bo19-combined%'`: lúc các kết nối của tiến trình biến mất (lần hỏi đầu tiên không còn dòng sau khi đã thấy), so với lúc gửi SIGTERM."""
    polls = []
    for l in lines:
        try:
            polls.append(json.loads(l))
        except ValueError:
            pass
    ts = lambda s: datetime.fromisoformat(s).timestamp()  # noqa: E731
    seen_rows = [p for p in polls if p.get("rows")]
    gone = next((p for p in polls if "rows" in p and not p["rows"] and ts(p["t"]) > ts(seen_rows[-1]["t"])), None) if seen_rows else None
    return {"polls": len(polls), "errors": sum("error" in p for p in polls), "last_seen_with_connections_s_after_sigterm": None if not seen_rows else round(ts(seen_rows[-1]["t"]) - t_kill.timestamp(), 2),
            "connections_gone_s_after_sigterm": None if gone is None else round(ts(gone["t"]) - t_kill.timestamp(), 2), "interval_s": 0.25}


if __name__ == "__main__":
    sys.exit(main())
