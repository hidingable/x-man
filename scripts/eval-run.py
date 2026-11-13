#!/usr/bin/env python3
"""行为 eval 运行器：在临时项目里用 xman 安装本仓的 skill，用 claude -p 跑 evals/cases.json 里的用例，
记录「结果对不对」（硬指标）和「过程是否克制」（软指标）。

用例格式和指标与发行版的 scripts/eval-run.mjs 保持一致，两边结果可以直接对照。
每次运行都在新的临时目录里进行，不碰本仓工作区。

例子：
  scripts/eval-run.py --cases bug-fix --runs 1 --dry-run
  scripts/eval-run.py --out eval-results/baseline --json
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "evals"
MAC_APP_DIR = Path.home() / "Library/Application Support/Claude/claude-code"
IGNORED = (".claude/", ".agents/")

# 判据与 conventions〈表达与命名〉一致：读者需要翻回去查对照表才懂的标识
CODE_PATTERNS = [
    re.compile(r"\b(Phase|Step|Layer|Stage)\s*\d+", re.I),
    re.compile(r"方案\s*[A-F](?![A-Za-z])"),
    re.compile(r"(?<![A-Za-z])P[0-3](?![A-Za-z0-9])"),
    re.compile(r"步骤\s*\d+\.\d+"),
    re.compile(r"(?<![A-Za-z])(FR|CT|AC|Q|F|O)\d{1,3}(?![A-Za-z0-9])"),
]


class FatalError(Exception):
    """后续运行也必然失败的错误，比如 claude 未登录。"""


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", help="只跑指定用例，逗号分隔（默认全部）")
    p.add_argument("--runs", type=int, default=3, help="每个用例跑几次（默认 3）")
    p.add_argument("--model", default="claude-sonnet-5-5", help="固定模型 ID（默认 claude-sonnet-5-5）")
    p.add_argument("--concurrency", type=int, default=3, help="同时跑几个（默认 3）")
    p.add_argument("--budget", type=float, default=2, help="单次运行的花费上限，美元（默认 2）")
    p.add_argument("--timeout", type=float, default=20, help="单次运行的超时，分钟（默认 20）")
    p.add_argument("--out", help="结果目录（默认 eval-results/<时间戳>）")
    p.add_argument("--claude", help="claude 可执行文件（默认 $CLAUDE_BIN，其次 PATH，其次桌面版自带的）")
    p.add_argument("--keep", action="store_true", help="保留临时项目目录，便于排查")
    p.add_argument("--dry-run", action="store_true", help="只列出要跑的用例和命令，不调用模型")
    p.add_argument("--json", action="store_true", help="结束时把汇总以 JSON 打到标准输出")
    p.add_argument("--summarize", help="不跑用例，只重新汇总已有结果目录")
    return p.parse_args()


def find_claude(explicit):
    for c in (explicit, os.environ.get("CLAUDE_BIN")):
        if c and Path(c).exists():
            return c
    found = shutil.which("claude")
    if found:
        return found
    if MAC_APP_DIR.exists():
        for version in sorted(os.listdir(MAC_APP_DIR), reverse=True):
            binary = MAC_APP_DIR / version / "claude.app/Contents/MacOS/claude"
            if binary.exists():
                return str(binary)
    return None


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def git(cwd, *args):
    code, out = run(["git", *args], cwd)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{out}")
    return out.strip()


def copy_into(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def prepare(spec, case):
    """复制夹具 → 叠加 base 层 → 初始提交 → 用 xman 安装 → 叠加 commit / worktree 层。"""
    work = Path(tempfile.mkdtemp(prefix=f"xman-eval-{case['id']}-"))
    copy_into(EVALS / "fixtures" / spec["fixture"], work)
    overlays = case.get("overlays", [])
    for o in overlays:
        if o["mode"] == "base":
            copy_into(EVALS / "overlays" / o["name"], work)

    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.email", "eval@example.com")
    git(work, "config", "user.name", "eval")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "init")

    for cmd in (["install", "claude", "--project", str(work)], ["context", "init", str(work)]):
        code, out = run([str(REPO / "xman"), *cmd], REPO)
        if code != 0:
            raise RuntimeError(f"xman {' '.join(cmd)} 失败：{out[-2000:]}")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "install x-mansion")

    for o in overlays:
        if o["mode"] == "commit":
            copy_into(EVALS / "overlays" / o["name"], work)
            git(work, "add", "-A")
            git(work, "commit", "-q", "-m", o.get("message", o["name"]))
    for o in overlays:
        if o["mode"] == "worktree":
            copy_into(EVALS / "overlays" / o["name"], work)
    return work


def claude_args(case, opts):
    args = [
        "-p", case["prompt"],
        "--output-format", "stream-json", "--verbose",
        "--model", opts.model,
        "--permission-mode", "bypassPermissions",
        "--setting-sources", "project,local",
        "--max-budget-usd", str(opts.budget),
        "--no-session-persistence",
    ]
    if case.get("agent"):
        args += ["--agent", case["agent"]]
    return args


def invoke(binary, args, cwd, timeout_min, raw_file):
    events = []
    timed_out = threading.Event()
    with open(raw_file, "w", encoding="utf-8") as raw:
        proc = subprocess.Popen([binary, *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def kill():
            timed_out.set()
            proc.terminate()

        timer = threading.Timer(timeout_min * 60, kill)
        timer.start()
        try:
            for line in proc.stdout:
                raw.write(line)
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            stderr = proc.stderr.read()
            proc.wait()
        finally:
            timer.cancel()
    return {"code": proc.returncode, "stderr": stderr, "events": events, "timed_out": timed_out.is_set()}


def analyze(case, events):
    tool_uses = [
        block
        for e in events if e.get("type") == "assistant"
        for block in (e.get("message") or {}).get("content") or []
        if block.get("type") == "tool_use"
    ]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    final_text = result.get("result") if isinstance(result.get("result"), str) else ""

    skills = set()
    slash = re.match(r"^/([\w-]+)", case["prompt"])
    if slash:
        skills.add(slash.group(1))
    for t in tool_uses:
        inp = t.get("input") or {}
        if t.get("name") == "Skill":
            name = str(inp.get("skill") or inp.get("command") or "").split(":")[-1]
            if name:
                skills.add(name)
        m = re.search(r"skills/([\w-]+)/SKILL\.md$", str(inp.get("file_path") or inp.get("path") or ""))
        if m:
            skills.add(m.group(1))
        if t.get("name") == "Bash":
            skills.update(re.findall(r"skills/([\w-]+)/SKILL\.md", str(inp.get("command") or "")))

    ask_tool = sum(1 for t in tool_uses if t.get("name") == "AskUserQuestion")
    ask_text = sum(1 for line in final_text.split("\n") if re.search(r"[？?]\s*$", line.strip()))
    usage = result.get("usage") or {}
    total_tokens = sum(usage.get(k) or 0 for k in
                       ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return {
        "final_text": final_text,
        "tool_uses": tool_uses,
        "result_subtype": result.get("subtype"),
        "soft": {
            "skills_read": sorted(skills),
            "expected_skills_read": all(s in skills for s in case.get("expect_skills", [])),
            "code_names": sum(len(p.findall(final_text)) for p in CODE_PATTERNS),
            "questions": ask_tool + ask_text,
            "final_lines": sum(1 for line in final_text.split("\n") if line.strip()),
            "tool_calls": len(tool_uses),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": total_tokens or None,
            "cost_usd": result.get("total_cost_usd"),
            "turns": result.get("num_turns"),
        },
    }


def changed_files(work, base):
    status = []
    # 不能 strip：porcelain 每行前两列是状态码，首行开头的空格也是状态码的一部分
    _, out = run(["git", "-c", "core.quotePath=false", "status", "--porcelain", "--untracked-files=all"], work)
    for line in out.split("\n"):
        if len(line) <= 3:
            continue
        path = line[3:].strip('"')
        status.append(path.split(" -> ")[-1])
    committed = [p for p in git(work, "-c", "core.quotePath=false", "diff", "--name-only", base, "HEAD").split("\n") if p]
    return [p for p in dict.fromkeys(status + committed) if not p.startswith(IGNORED)]


def pass_fail_line(out):
    return " ".join(l for l in out.split("\n") if re.match(r"^# (pass|fail)", l))


def check(case, work, base, base_count, analysis):
    changed = changed_files(work, base)
    results = []
    for c in case["checks"]:
        kind, ok, detail = c["type"], False, ""
        if kind == "no_source_change":
            offenders = [p for p in changed if not p.startswith(".ai-configs/")]
            ok, detail = not offenders, ", ".join(offenders)
        elif kind == "no_commit":
            count = int(git(work, "rev-list", "--count", "HEAD"))
            ok, detail = count == base_count, f"提交数 {base_count} → {count}"
        elif kind == "changed_within":
            offenders = [p for p in changed if not any(p == a or p.startswith(a) for a in c["paths"])]
            ok = not offenders
            detail = f"范围外：{', '.join(offenders)}" if offenders else ", ".join(changed)
        elif kind == "visible_tests":
            code, out = run(["npm", "test", "--silent"], work)
            ok, detail = code == 0, "" if code == 0 else pass_fail_line(out)
        elif kind == "hidden_tests":
            target = work / "test/__hidden__"
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy(EVALS / "hidden" / c["file"], target / c["file"])
            code, out = run(["node", "--test", f"test/__hidden__/{c['file']}"], work)
            ok, detail = code == 0, pass_fail_line(out)
            shutil.rmtree(target, ignore_errors=True)
        elif kind == "output_matches":
            ok = re.search(c["pattern"], analysis["final_text"], re.I) is not None
        elif kind == "artifact_matches":
            # 落档路径由 conventions 决定（Ad-hoc 或 Task），按路径正则找本次新增或改动的产物；negate 表示一份都不能含
            docs = [p for p in changed if re.search(c["path"], p)]
            hits = [p for p in docs if re.search(c["pattern"], (work / p).read_text(encoding="utf-8"), re.I | re.M)]
            ok = bool(docs) and (not hits if c.get("negate") else bool(hits))
            if not docs:
                detail = f"没有落档：{c['path']}"
            elif c.get("negate"):
                detail = ", ".join(hits)
            elif not ok:
                detail = f"{', '.join(docs)} 不含 {c['pattern']}"
        elif kind == "skills_not_used":
            used = [n for n in c["skills"] if n in analysis["soft"]["skills_read"]]
            ok, detail = not used, ", ".join(used)
        elif kind == "ran_command":
            ok = any(t.get("name") == "Bash" and re.search(c["pattern"], str((t.get("input") or {}).get("command") or ""))
                     for t in analysis["tool_uses"])
        else:
            raise RuntimeError(f"未知检查类型 {kind}")
        results.append({"type": kind, "pass": ok, "detail": detail})
    return {"checks": results, "hard_pass": all(r["pass"] for r in results), "changed": changed}


def run_one(spec, case, n, opts, binary, out_dir):
    work = prepare(spec, case)
    base = git(work, "rev-parse", "HEAD")
    base_count = int(git(work, "rev-list", "--count", "HEAD"))
    started = time.time()
    proc = invoke(binary, claude_args(case, opts), work, opts.timeout, out_dir / f"{case['id']}-{n}.jsonl")
    analysis = analyze(case, proc["events"])
    if re.search(r"Not logged in|Invalid API key", analysis["final_text"], re.I):
        if not opts.keep:
            shutil.rmtree(work, ignore_errors=True)
        raise FatalError(f'claude 未登录：在终端运行 "{binary}"，输入 /login 完成登录后重跑')
    verdict = check(case, work, base, base_count, analysis)
    record = {
        "case": case["id"],
        "run": n,
        "model": opts.model,
        "seconds": round(time.time() - started),
        "exit_code": proc["code"],
        "timed_out": proc["timed_out"],
        "result_subtype": analysis["result_subtype"],
        "hard_pass": verdict["hard_pass"],
        "checks": verdict["checks"],
        "changed_files": verdict["changed"],
        "soft": analysis["soft"],
        "final_text": analysis["final_text"],
        "stderr": proc["stderr"][-2000:],
        "workdir": str(work) if opts.keep else None,
    }
    (out_dir / f"{case['id']}-{n}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    if not opts.keep:
        shutil.rmtree(work, ignore_errors=True)
    s = analysis["soft"]
    print(f"{'✓' if verdict['hard_pass'] else '✗'} {case['id']}#{n}  {record['seconds']}s  "
          f"工具 {s['tool_calls']}  提问 {s['questions']}  行数 {s['final_lines']}", file=sys.stderr)
    return record


def median(values):
    nums = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(nums) if nums else None


def summarize(records):
    by_case = {}
    for r in records:
        by_case.setdefault(r["case"], []).append(r)
    cases = []
    for cid, rs in by_case.items():
        cases.append({
            "case": cid,
            "runs": len(rs),
            "hard_pass": sum(1 for r in rs if r["hard_pass"]),
            "expected_skills_read": sum(1 for r in rs if r["soft"]["expected_skills_read"]),
            "median": {k: median([r["soft"][k] for r in rs]) for k in
                       ("code_names", "questions", "final_lines", "tool_calls", "total_tokens", "cost_usd", "turns")},
            "failed_checks": sorted({c["type"] for r in rs for c in r["checks"] if not c["pass"]}),
        })
    return {"model": records[0]["model"] if records else None, "total_runs": len(records), "cases": cases}


def print_table(summary):
    header = ["用例", "硬指标", "读对skill", "代号", "提问", "行数", "工具", "token", "花费", "未通过的检查"]
    print("\t".join(header))
    for c in summary["cases"]:
        m = c["median"]
        cost = f"{m['cost_usd']:.2f}" if m["cost_usd"] is not None else "-"
        row = [c["case"], f"{c['hard_pass']}/{c['runs']}", f"{c['expected_skills_read']}/{c['runs']}",
               m["code_names"], m["questions"], m["final_lines"], m["tool_calls"], m["total_tokens"], cost,
               ",".join(c["failed_checks"])]
        print("\t".join("-" if x is None else str(x) for x in row))


def main():
    opts = parse_args()
    if opts.summarize:
        d = Path(opts.summarize).resolve()
        records = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(d.glob("*-[0-9]*.json"))]
        summary = summarize(records)
        (d / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2)) if opts.json else print_table(summary)
        return

    spec = json.loads((EVALS / "cases.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in spec["cases"]]
    wanted = [s.strip() for s in opts.cases.split(",")] if opts.cases else ids
    unknown = [w for w in wanted if w not in ids]
    if unknown:
        sys.exit(f"没有这些用例：{', '.join(unknown)}；可用：{', '.join(ids)}")
    jobs = [(c, n) for c in spec["cases"] if c["id"] in wanted for n in range(1, opts.runs + 1)]

    binary = find_claude(opts.claude)
    if opts.dry_run:
        plan = [{"case": c["id"], "run": n, "args": claude_args(c, opts)} for c, n in jobs]
        print(json.dumps({"claude": binary, "jobs": plan}, ensure_ascii=False, indent=2))
        return
    if not binary:
        sys.exit("找不到 claude 可执行文件；用 --claude <路径> 或设置 CLAUDE_BIN 指定")

    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = Path(opts.out).resolve() if opts.out else REPO / "eval-results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"共 {len(jobs)} 次运行，模型 {opts.model}，结果写入 {out_dir}", file=sys.stderr)

    records, stop = [], threading.Event()

    def worker(job):
        case, n = job
        if stop.is_set():
            return
        try:
            records.append(run_one(spec, case, n, opts, binary, out_dir))
        except FatalError as err:
            stop.set()
            print(f"✗ {case['id']}#{n} 运行出错：{err}", file=sys.stderr)
        except Exception as err:  # noqa: BLE001 单次运行出错不影响其他用例
            print(f"✗ {case['id']}#{n} 运行出错：{err}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=max(1, opts.concurrency)) as pool:
        list(pool.map(worker, jobs))

    if not records:
        sys.exit("没有成功完成的运行，见上方报错")
    summary = summarize(records)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)) if opts.json else print_table(summary)


if __name__ == "__main__":
    main()
