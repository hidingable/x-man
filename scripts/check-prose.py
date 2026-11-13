#!/usr/bin/env python3
"""面向人的产物里，找出违反 conventions.md〈输出〉的四类常见说法。

〈输出〉用正向写法规定该怎么写（第一行给动作或结论、报错写现象原因修法、不确定时写缺哪条证据、
没有未完成的事就直接结束），不在规则里罗列反例。能机械识别的反例由这个脚本维护，
规则文字和检查各管一边，文风才不会在下一次改文档时静默退化：

  开场预告：预告自己将要做什么，而不是直接给动作。
  客套收尾：不携带信息、需要读者再问一轮才推进的结尾。
  报错语气：把失败说成「好像出了点问题」，读者拿不到现象/原因/修法。
  含糊堆砌：「应该没问题」这类用语气替代证据的说法。

文风命中只报告，不阻断，退出码为 0；读取等执行错误仍以非零状态退出。
判定文风是主观的——把主观判断接成红灯，下次有人为了过校验改写措辞，
规则就失效了。这里只把候选摆出来给人看。

扫描范围默认是 .ai-configs/ 下的产物，也就是"给人看的文档"。规则源文件
（.ai-configs/conventions.md 软链到 context/conventions.md）本身写着这些词，
跳过；围栏代码块和行内反引号里的内容是对规则的引用或示例，同样跳过。

用法：
  scripts/check-prose.py [目录 ...]

输出首行是制表符分隔的判定标记（OK / WARN），供 validate.sh 渲染。
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCOPE = REPO_ROOT / ".ai-configs"
RULE_SOURCE = REPO_ROOT / "context" / "conventions.md"

# 每类都对应〈输出〉里的一条正向规则；新增类别前先确认〈输出〉里有对应的规则。
RULES = (
    (
        "开场预告",
        re.compile(r"让我来看看|让我来看|为了回答这个问题|为了回答你的问题|让我先看看"),
    ),
    (
        "客套收尾",
        re.compile(r"还有什么需要帮忙|还需要什么吗|希望有帮助|希望能帮到你|随时问我|随时告诉我|Let me know if you need"),
    ),
    (
        "报错语气",
        re.compile(r"好像出了点问题|好像有点问题|哎呀|糟了"),
    ),
    (
        "含糊堆砌",
        re.compile(r"应该没问题|应该可以|大概可能|可能也许"),
    ),
)

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")


def strip_inline_code(line):
    """行内反引号里的内容是对规则的引用或示例，不参与匹配。"""
    return INLINE_CODE.sub("`…`", line)


def scan_file(path):
    """返回 (规则名, 行号, 命中片段) 列表；跳过围栏代码块。"""
    findings = []
    in_fence = False
    text = path.read_text(encoding="utf-8")
    for lineno, raw in enumerate(text.splitlines(), 1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = strip_inline_code(raw)
        for name, pattern in RULES:
            match = pattern.search(line)
            if match:
                start = max(0, match.start() - 20)
                excerpt = line[start : match.end() + 30].strip()
                findings.append((name, lineno, excerpt))
                break
    return findings


def collect_targets(scopes):
    targets = []
    notices = []
    for scope in scopes:
        if scope.is_file():
            targets.append(scope)
            continue
        if not scope.is_dir():
            notices.append(f"提示：{scope} 不存在，跳过")
            continue
        targets.extend(sorted(scope.rglob("*.md")))
    # 规则源文件写着全部禁用词，必须排除；用 resolve 比较以穿透软链。
    rule_source = RULE_SOURCE.resolve()
    targets = [
        t
        for t in targets
        if not t.resolve() == rule_source and not t.name.startswith(".")
    ]
    return targets, notices


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("paths", nargs="*", type=Path, default=None)
    args = parser.parse_args()

    scopes = args.paths or [DEFAULT_SCOPE]
    targets, notices = collect_targets(scopes)

    lines = []
    hit_files = 0
    for target in targets:
        findings = scan_file(target)
        if not findings:
            continue
        hit_files += 1
        for name, lineno, excerpt in findings:
            rel = target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target
            lines.append(f"PROSE_WARN  {rel}:{lineno}  [{name}]  {excerpt}")

    # 判定始终在提示之前，避免缺失或空目录打断 validate.sh 的首行协议。
    if lines:
        print(f"WARN\t{hit_files} 份产物共 {len(lines)} 处需要人看一眼（只报告，不阻断）")
    elif notices:
        print(f"WARN\t{len(notices)} 个路径不存在，已跳过（只报告，不阻断）")
    elif not targets:
        print("OK\t0 份产物，没有可检查的产物，跳过")
    else:
        print(f"OK\t{len(targets)} 份产物，〈输出〉的四类禁用表达无命中")

    for notice in notices:
        print(notice)
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
