---
name: html-view
disable-model-invocation: true
description: "把 .ai-configs 里的 Markdown 产物渲染成同名的离线 HTML，给人用浏览器看。"
metadata:
  category: workflow
  tags: [html, docs, render]
  dependencies: []
  requires_context: []
---

# 生成 HTML

哪些产物自动生成 HTML、什么时候生成，按 `.ai-configs/conventions.md`〈人读产物的 HTML〉。本 skill 用于用户手动要求：重新生成、给其他 md 也生成一份、或者批量补齐。

1. 确定要渲染的 md：用户点名的文件；说「全部」「补齐」时，按〈人读产物的 HTML〉的左列类型在 `.ai-configs/` 下找缺少同名 `.html` 或 `.html` 比 md 旧的文件。
2. 运行本 skill 目录下的 `scripts/render.mjs`，一次传入全部路径：`node <本 skill 目录>/scripts/render.mjs <a.md> <b.md>`。脚本每生成一份输出一行路径，有失败时退出码为 1 并在 stderr 写原因。
3. 回复里列出生成的 HTML 路径；失败的写文件和原因。没有 Node.js 时说明需要先安装 Node.js，md 不受影响。

HTML 由脚本整份重写，内容有误时改 md 再重新生成。
