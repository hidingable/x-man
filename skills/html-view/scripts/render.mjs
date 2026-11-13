#!/usr/bin/env node
// 把 .ai-configs 里给人看的 Markdown 产物渲染成同名的离线 HTML。
// 只用 Node 标准库；输出不引用任何外部资源（CSS 内联，CSP 禁止脚本和网络请求）。
// md 是唯一事实源，HTML 每次整份重写，不要手改。

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HELP = `用法: node render.mjs <file.md> [更多 .md ...]

在每个 .md 旁边生成同名 .html（离线可打开，无外部请求）。
成功时每个文件输出一行生成的路径；任何文件失败时退出码为 1。`;

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// 等宽字体大多不带中文字形，中文会退回到比例字体，宽度不是英文的整两倍，代码块里的框线图就会错位。
// 把东亚宽字符逐个包进 2ch 宽的盒子，不依赖读者装了什么字体。
const WIDE = /[\u1100-\u115F\u2E80-\u303E\u3041-\u33FF\u3400-\u4DBF\u4E00-\u9FFF\uA000-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE4F\uFF00-\uFF60\uFFE0-\uFFE6\u{20000}-\u{3FFFD}]/gu;
const fixWide = (s) => s.replace(WIDE, (c) => `<span class="w">${c}</span>`);

// 行内格式：先把代码段抽出来保护，再处理链接、粗体、斜体
function inline(text) {
  const codes = [];
  let s = text.replace(/`([^`]+)`/g, (_, c) => `\u0000${codes.push(c) - 1}\u0000`);
  s = esc(s);
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, (_, alt, src) => safeUrl(src) ? `<img alt="${alt}" src="${src}">` : alt);
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (_, label, href) => safeUrl(href) ? `<a href="${href}">${label}</a>` : label);
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?!\w)/g, '$1<em>$2</em>');
  s = s.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[Number(i)])}</code>`);
}

// 拦掉会执行代码的协议；外部图片由页面的 CSP（img-src 'self'）挡住，打开页面不会发起网络请求
function safeUrl(url) {
  const decoded = url.replace(/&amp;/g, '&');
  if (/^(javascript|data|vbscript):/i.test(decoded)) return false;
  return true;
}

const isTableSep = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
const splitRow = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'));
const listItem = (line) => line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);

function renderList(lines, start) {
  const first = listItem(lines[start]);
  const indent = first[1].length;
  const ordered = /\d/.test(first[2]);
  const items = [];
  let i = start;
  while (i < lines.length) {
    const m = listItem(lines[i]);
    if (m && m[1].length === indent && /\d/.test(m[2]) !== ordered) break;
    if (m && m[1].length === indent) {
      items.push({ text: m[3], children: [] });
      i++;
    } else if (m && m[1].length > indent) {
      const nested = renderList(lines, i);
      items[items.length - 1].children.push(nested.html);
      i = nested.next;
    } else if (!m && lines[i].trim() && /^\s+/.test(lines[i]) && items.length) {
      items[items.length - 1].text += ' ' + lines[i].trim();
      i++;
    } else break;
  }
  const lis = items.map(({ text, children }) => {
    const task = text.match(/^\[([ xX])\]\s+(.*)$/);
    const body = task
      ? `<input type="checkbox" disabled${task[1] === ' ' ? '' : ' checked'}> ${inline(task[2])}`
      : inline(text);
    return `<li${task ? ' class="task"' : ''}>${body}${children.join('')}</li>`;
  });
  const tag = ordered ? 'ol' : 'ul';
  return { html: `<${tag}>${lis.join('')}</${tag}>`, next: i };
}

export function renderMarkdown(md) {
  const lines = md.replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  const toc = [];
  const slugs = new Map();
  let title = '';
  let i = 0;

  // YAML frontmatter 不展示
  if (lines[0] === '---') {
    const end = lines.indexOf('---', 1);
    if (end > 0) i = end + 1;
  }

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) { i++; continue; }

    if (/^<!--/.test(line.trim())) {
      while (i < lines.length && !lines[i].includes('-->')) i++;
      i++;
      continue;
    }

    const fence = line.match(/^(\s*)(`{3,}|~{3,})\s*([\w+-]*)/);
    if (fence) {
      const body = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence[2])) body.push(lines[i++]);
      i++;
      const lang = fence[3] ? ` data-lang="${esc(fence[3])}"` : '';
      out.push(`<pre${lang}><code>${fixWide(esc(body.join('\n')))}</code></pre>`);
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2];
      if (level === 1 && !title) { title = text.replace(/[`*]/g, ''); out.push(`<h1>${inline(text)}</h1>`); i++; continue; }
      const base = text.replace(/[`*[\]()]/g, '').trim().toLowerCase().replace(/\s+/g, '-').replace(/[^\p{L}\p{N}-]/gu, '') || 'section';
      const n = slugs.get(base) || 0;
      slugs.set(base, n + 1);
      const id = n ? `${base}-${n}` : base;
      if (level === 2) toc.push({ id, text: inline(text) });
      out.push(`<h${level} id="${esc(id)}">${inline(text)}</h${level}>`);
      i++;
      continue;
    }

    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { out.push('<hr>'); i++; continue; }

    if (line.includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = splitRow(line);
      const aligns = splitRow(lines[i + 1]).map((c) => (/^:-+:$/.test(c) ? 'center' : /-+:$/.test(c) ? 'right' : ''));
      const cell = (tag, c, k) => `<${tag}${aligns[k] ? ` style="text-align:${aligns[k]}"` : ''}>${inline(c)}</${tag}>`;
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(splitRow(lines[i++]));
      out.push(`<div class="table"><table><thead><tr>${head.map((c, k) => cell('th', c, k)).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${head.map((_, k) => cell('td', r[k] ?? '', k)).join('')}</tr>`).join('')}</tbody></table></div>`);
      continue;
    }

    if (/^\s*>/.test(line)) {
      const body = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ''));
      out.push(`<blockquote>${renderMarkdown(body.join('\n')).body}</blockquote>`);
      continue;
    }

    if (listItem(line)) {
      const list = renderList(lines, i);
      out.push(list.html);
      i = list.next;
      continue;
    }

    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*>|\s*(`{3,}|~{3,})|\s*<!--|\s*([-*_])(\s*\3){2,}\s*$)/.test(lines[i]) && !listItem(lines[i])
      && !(lines[i].includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
      para.push(lines[i++]);
    }
    out.push(`<p>${para.map(inline).join('<br>')}</p>`);
  }

  return { title, toc, body: out.join('\n') };
}

const CSS = `
:root{color-scheme:light dark;--paper:#faf9f5;--card:#ffffff;--ink:#141413;--muted:#6b6a65;--line:#e5e3da;--accent:#c96442;--accent-soft:#f5e9e2;--code:#f0eee6}
@media (prefers-color-scheme:dark){:root{--paper:#1f1e1b;--card:#262624;--ink:#ecebe6;--muted:#a3a29b;--line:#3a3935;--accent:#d97757;--accent-soft:#3a2a23;--code:#30302d}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Segoe UI",sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:48px 24px 80px}
header.meta{color:var(--muted);font-size:13px;letter-spacing:.02em;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:8px;overflow-wrap:anywhere}
h1,h2,h3,h4{font-family:ui-serif,Georgia,"Songti SC","Noto Serif CJK SC",serif;font-weight:600;line-height:1.35;letter-spacing:-.01em}
h1{font-size:clamp(28px,4vw,38px);margin:24px 0 16px}
h2{font-size:24px;margin:48px 0 12px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:19px;margin:32px 0 8px}h4{font-size:16px;margin:24px 0 8px}
p{margin:12px 0}a{color:var(--accent);text-underline-offset:3px}
strong{font-weight:600}
nav.toc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:24px 0}
nav.toc b{display:block;font-size:13px;color:var(--muted);font-weight:500;margin-bottom:6px}
nav.toc ol{margin:0;padding-left:20px}nav.toc li{margin:2px 0}
ul,ol{padding-left:24px;margin:10px 0}li{margin:4px 0}li.task{list-style:none;margin-left:-20px}
li.task input{margin-right:6px;accent-color:var(--accent)}
blockquote{margin:16px 0;padding:4px 18px;border-left:3px solid var(--accent);background:var(--accent-soft);border-radius:0 8px 8px 0}
code{font:13.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code);padding:1px 6px;border-radius:5px;overflow-wrap:anywhere}
pre{background:var(--code);border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow-x:auto}
pre code{background:none;padding:0;overflow-wrap:normal;white-space:pre}
pre .w{display:inline-block;width:2ch;text-align:center}
.table{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--code);font-weight:600}tr:last-child td{border-bottom:none}
hr{border:none;border-top:1px solid var(--line);margin:32px 0}
img{max-width:100%}
@media print{body{background:#fff}nav.toc{display:none}h2{break-after:avoid}pre,.table{break-inside:avoid}}
`;

export function renderPage(md, sourceName) {
  const { title, toc, body } = renderMarkdown(md);
  const pageTitle = title || sourceName;
  const tocHtml = toc.length >= 3
    ? `<nav class="toc"><b>目录</b><ol>${toc.map((t) => `<li><a href="#${esc(t.id)}">${t.text}</a></li>`).join('')}</ol></nav>`
    : '';
  // 标题后面插入目录：h1 在最前时放在它后面，否则放在正文最前
  const withToc = body.startsWith('<h1>') ? body.replace(/<\/h1>/, `</h1>\n${tocHtml}`) : tocHtml + body;
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self'">
<title>${esc(pageTitle)}</title>
<style>${CSS}</style></head>
<body><div class="wrap">
<header class="meta">${esc(sourceName)} · 由同名 Markdown 生成，修改请改 md 后重新生成</header>
${withToc}
</div></body></html>
`;
}

function main(argv) {
  if (!argv.length || argv.includes('-h') || argv.includes('--help')) {
    console.log(HELP);
    return argv.length ? 0 : 1;
  }
  let failed = 0;
  for (const file of argv) {
    try {
      if (!file.endsWith('.md')) throw new Error('只接受 .md 文件');
      const md = fs.readFileSync(file, 'utf8');
      const target = file.replace(/\.md$/, '.html');
      fs.writeFileSync(target, renderPage(md, path.basename(file)));
      console.log(target);
    } catch (err) {
      failed++;
      console.error(`${file}: ${err.message}`);
    }
  }
  return failed ? 1 : 0;
}

// 通过软链运行时（如 .claude/skills 指向 .agents/skills），argv[1] 是软链路径，要比较真实路径
const isMain = () => {
  try { return fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url)); } catch { return false; }
};

if (process.argv[1] && isMain()) {
  process.exitCode = main(process.argv.slice(2));
}
