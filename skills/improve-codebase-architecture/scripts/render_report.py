#!/usr/bin/env python3
"""Render evidence supplied by the caller as one offline architecture report."""

import argparse
import html
import json
import sys
from pathlib import Path


RECOMMENDATIONS = {"优先验证", "值得探索", "证据不足"}
CSS = """
:root{color-scheme:light;--ink:#202a31;--muted:#5e6870;--line:#d6dbde;--paper:#f6f5f0;--accent:#275d55}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.7 system-ui,-apple-system,sans-serif}
main{max-width:1100px;margin:auto;padding:48px 24px 72px}header{border-bottom:2px solid var(--ink);padding-bottom:24px}
h1{font-size:clamp(28px,4vw,42px);line-height:1.25;letter-spacing:-.02em;margin:12px 0 20px}
h2{font-size:24px;line-height:1.4;margin:0 0 16px}h3{font-size:16px;margin:0 0 10px}p{margin:10px 0}
.eyebrow,.label{font-size:13px;color:var(--muted);letter-spacing:.04em}.summary{font-size:19px}.meta{color:var(--muted)}
.recommendation{margin:28px 0;padding:24px;border-left:4px solid var(--accent);background:#e9efeb}
nav{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}a{color:var(--accent);text-underline-offset:3px}
article{background:#fff;border:1px solid var(--line);border-radius:10px;margin:24px 0;padding:28px;break-inside:avoid}
.badge{display:inline-block;border:1px solid var(--line);border-radius:4px;font-size:13px;padding:2px 9px;margin-bottom:12px}
.comparison{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:22px 0}.panel{padding:18px;background:#f4f5f5;border-top:3px solid #a8b1b6;min-width:0}
.panel.proposed{border-color:var(--accent);background:#edf3ef}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
ul{padding-left:24px;margin:8px 0 20px}li{margin:6px 0;overflow-wrap:anywhere}details{border-top:1px solid var(--line);padding-top:14px}
summary{cursor:pointer;font-weight:600;margin-bottom:14px}footer{font-size:13px;color:var(--muted);margin-top:32px}section{overflow-wrap:anywhere}
@media(max-width:640px){main{padding:28px 16px}.comparison{grid-template-columns:1fr}article{padding:20px}}
@media print{body{background:#fff}main{max-width:none;padding:0}article{box-shadow:none}nav{display:none}details>*{display:block}}
"""


def require_text(obj, key, where):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}.{key} 必须是非空文本")
    return value


def require_list(obj, key, where, *, nonempty=False):
    value = obj.get(key)
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{where}.{key} 必须是{'非空' if nonempty else ''}文本数组")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{where}.{key} 中每项必须是非空文本")
    return value


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("输入必须是 JSON 对象")
    for key in ("title", "scope", "selection_basis", "summary", "recommendation_reason"):
        require_text(data, key, "report")
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("report.candidates 必须是数组")
    names = set()
    for index, candidate in enumerate(candidates):
        where = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            raise ValueError(f"{where} 必须是对象")
        for key in ("name", "recommendation", "rationale", "current", "proposed", "impact"):
            require_text(candidate, key, where)
        if candidate["name"] in names:
            raise ValueError("候选名称不能重复")
        names.add(candidate["name"])
        if candidate["recommendation"] not in RECOMMENDATIONS:
            raise ValueError(f"{where}.recommendation 必须使用约定的推荐强度")
        for key in ("evidence", "verification", "tradeoffs"):
            require_list(candidate, key, where, nonempty=True)
        require_list(candidate, "uncertainties", where)
    recommended = data.get("recommended_candidate")
    if recommended is not None and (not isinstance(recommended, str) or recommended not in names):
        raise ValueError("recommended_candidate 必须对应已有候选名称或为 null")


def text(value):
    return html.escape(value, quote=True)


def section_list(title, values):
    if not values:
        return ""
    items = "".join(f"<li>{text(value)}</li>" for value in values)
    return f"<section><h3>{title}</h3><ul>{items}</ul></section>"


def render(data):
    validate(data)
    navigation = []
    cards = []
    for index, candidate in enumerate(data["candidates"], 1):
        anchor = f"candidate-{index}"
        navigation.append(f'<a href="#{anchor}">{text(candidate["name"])}</a>')
        details = "".join(section_list(title, candidate[key]) for title, key in (
            ("依据", "evidence"), ("验证", "verification"),
            ("代价与取舍", "tradeoffs"), ("不确定性", "uncertainties"),
        ))
        cards.append(f'''
<article id="{anchor}">
<span class="badge">{text(candidate["recommendation"])}</span>
<h2>{text(candidate["name"])}</h2><p>{text(candidate["rationale"])}</p>
<div class="comparison"><section class="panel"><h3>现状</h3><pre>{text(candidate["current"])}</pre></section>
<section class="panel proposed"><h3>建议</h3><pre>{text(candidate["proposed"])}</pre></section></div>
<section><h3>预期影响</h3><p>{text(candidate["impact"])}</p></section>
<details open><summary>依据、验证与取舍</summary>{details}</details>
</article>''')
    recommendation = data.get("recommended_candidate") or "暂不选择候选"
    body = "".join(cards) or '<p class="meta">本次没有证据充分的架构改善候选。</p>'
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>{text(data["title"])}</title><style>{CSS}</style></head><body><main>
<header><p class="eyebrow">架构检查 · 只读扫描</p><h1>{text(data["title"])}</h1>
<p class="summary">{text(data["summary"])}</p><p class="meta">{text(data["scope"])}</p>
<p><span class="label">范围选择依据</span><br>{text(data["selection_basis"])}</p></header>
<section class="recommendation"><p class="label">下一步建议</p><h2>{text(recommendation)}</h2>
<p>{text(data["recommendation_reason"])}</p></section>
<nav aria-label="候选目录">{"".join(navigation)}</nav>{body}
<footer>推荐依据以本次记录为限；建议实施前需确认尚未闭合的约束。此报告可离线阅读。</footer>
</main></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="示例：render_report.py --input report.json --output report.html --dry-run")
    parser.add_argument("--input", required=True, type=Path, help="已完成证据核对的 JSON 输入")
    parser.add_argument("--output", required=True, type=Path, help="按项目 conventions 解析出的 HTML 路径")
    parser.add_argument("--dry-run", action="store_true", help="只校验与渲染到内存，不写文件；stdout 为 JSON")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        report = render(data)
        output = args.output.resolve()
        if not args.dry_run:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report, encoding="utf-8")
        print(json.dumps({"output": str(output), "candidates": len(data["candidates"]), "written": not args.dry_run}, ensure_ascii=False))
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
