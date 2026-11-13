#!/usr/bin/env node
/**
 * xman-verify — 验证用的三个探针，架在 web-access 的 CDP Proxy 上。
 *
 * 上游的 cdp-proxy 能开页、点、读、截图，但看不到「页面稳没稳」「有没有报错」
 * 「哪个请求挂了」——验证最需要的恰好是这三样。本文件全部走上游已有的 /eval 实现，
 * 不改上游一行代码，因此 `xman update --skill web-access` 不会冲突
 * （manifest 里已把 xman-*.mjs 排除在同步之外）。
 *
 * 用法看 --help。典型顺序：arm → 操作页面 → wait-settle → console / network
 */

const PORT = parseInt(process.env.CDP_PROXY_PORT || '3456', 10);
const BASE = `http://localhost:${PORT}`;

// ─── 注入页面的记录器：包一层 console / fetch / XHR，并盯 DOM 变动 ───
const RECORDER = `(() => {
  if (window.__xmanProbe) return { already: true };
  const p = { console: [], net: [], pending: 0, lastMutation: Date.now() };
  window.__xmanProbe = p;
  const flat = (a) => { try { return typeof a === 'string' ? a : JSON.stringify(a); } catch (e) { return String(a); } };
  for (const level of ['log', 'info', 'warn', 'error']) {
    const orig = console[level].bind(console);
    console[level] = (...args) => {
      try { p.console.push({ level, at: Date.now(), text: args.map(flat).join(' ').slice(0, 2000) }); } catch (e) {}
      orig(...args);
    };
  }
  addEventListener('error', (e) => p.console.push({ level: 'error', at: Date.now(), text: '[uncaught] ' + e.message + ' @ ' + e.filename + ':' + e.lineno }));
  addEventListener('unhandledrejection', (e) => p.console.push({ level: 'error', at: Date.now(), text: '[unhandled promise] ' + String(e.reason) }));
  const of = window.fetch;
  window.fetch = async (...args) => {
    const raw = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    const rec = { kind: 'fetch', url: String(raw).slice(0, 500), start: Date.now(), status: null, ok: null, error: null };
    p.net.push(rec); p.pending++;
    try { const r = await of(...args); rec.status = r.status; rec.ok = r.ok; return r; }
    catch (e) { rec.error = String(e); rec.ok = false; throw e; }
    finally { rec.ms = Date.now() - rec.start; p.pending--; }
  };
  const xopen = XMLHttpRequest.prototype.open, xsend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u, ...r) {
    this.__xm = { kind: 'xhr', method: m, url: String(u).slice(0, 500), status: null, ok: null, error: null };
    return xopen.call(this, m, u, ...r);
  };
  XMLHttpRequest.prototype.send = function (...a) {
    const rec = this.__xm || { kind: 'xhr', url: '?' };
    rec.start = Date.now(); p.net.push(rec); p.pending++;
    this.addEventListener('loadend', () => {
      rec.status = this.status; rec.ok = this.status >= 200 && this.status < 400;
      if (this.status === 0) rec.error = '请求未完成（网络错误、被拦截或跨域）';
      rec.ms = Date.now() - rec.start; p.pending--;
    });
    return xsend.apply(this, a);
  };
  new MutationObserver(() => { p.lastMutation = Date.now(); })
    .observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
  return { already: false };
})()`;

const PROBE_STATE = `(() => {
  const p = window.__xmanProbe;
  return {
    armed: !!p,
    readyState: document.readyState,
    pending: p ? p.pending : null,
    sinceMutation: p ? Date.now() - p.lastMutation : null,
    htmlLen: document.documentElement.innerHTML.length,
  };
})()`;

const READ_CONSOLE = `(() => (window.__xmanProbe ? window.__xmanProbe.console : null))()`;
const READ_NET = `(() => {
  const p = window.__xmanProbe;
  const perf = performance.getEntriesByType('resource').map((e) => ({
    kind: 'resource', url: String(e.name).slice(0, 500), ms: Math.round(e.duration), status: null, ok: null, error: null,
  }));
  return { armed: !!p, hooked: p ? p.net : [], observed: perf };
})()`;

// ─── 与 proxy 通信 ───
// 每个请求都带超时。proxy 进程活着但浏览器没开调试端口时，它会把连接一直挂着不回，
// 没有超时的话工具就永远卡在那里——给 agent 用的东西不能这样。
let NET_TIMEOUT = 8000;

async function request(url, init = {}) {
  try {
    return await fetch(url, { ...init, signal: AbortSignal.timeout(NET_TIMEOUT) });
  } catch (e) {
    if (e && (e.name === 'TimeoutError' || e.name === 'AbortError')) {
      fail(`CDP Proxy（${BASE}）在 ${NET_TIMEOUT}ms 内没回应，连接状态尚未确认。\n`
         + `先检查共享服务与浏览器连接：\n`
         + `  node "${scriptDir()}/proxy-maintenance.mjs" status\n`
         + `  node "${scriptDir()}/check-deps.mjs"\n`
         + `如需维护，等共享任务结束后按 migration-2.6.md 处理，不批量终止进程。\n`
         + `超时不够就加 --net-timeout <ms>。`);
    }
    fail(`连不上 CDP Proxy（${BASE}）。先起它：\n`
       + `  node "${scriptDir()}/check-deps.mjs"`);
  }
}

async function evaluate(target, expression) {
  const url = `${BASE}/eval${target ? `?target=${encodeURIComponent(target)}` : ''}`;
  const res = await request(url, { method: 'POST', body: expression });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    fail(`页面里执行失败：${body.error || res.status}\n`
       + `如果是「Cannot find context」这类，多半 target 不对。列一下当前标签页：\n`
       + `  curl -s ${BASE}/targets`);
  }
  return body.value;
}

function scriptDir() {
  return new URL('.', import.meta.url).pathname.replace(/\/$/, '');
}

function fail(msg) {
  process.stderr.write(`${msg}\n`);
  process.exit(1);
}

function out(json, data, human) {
  process.stdout.write(json ? `${JSON.stringify(data, null, 2)}\n` : `${human}\n`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ─── 子命令 ───
async function cmdArm({ target, json, dryRun }) {
  if (dryRun) {
    out(json, { wouldInject: true, bytes: RECORDER.length },
      `--dry-run：会往页面注入 ${RECORDER.length} 字节的记录器（包 console / fetch / XHR，装一个 MutationObserver），不改页面内容。`);
    return;
  }
  const r = await evaluate(target, RECORDER);
  out(json, { armed: true, already: !!(r && r.already) },
    r && r.already ? '已经装过了，跳过。' : '记录器已装。现在开始操作页面，之后再跑 console / network / wait-settle。');
}

async function cmdWaitSettle({ target, json, timeout, quiet }) {
  const started = Date.now();
  let last = null;
  let stableSince = null;
  while (Date.now() - started < timeout) {
    const s = await evaluate(target, PROBE_STATE);
    const domQuiet = s.armed
      ? s.sinceMutation >= quiet
      : last !== null && s.htmlLen === last.htmlLen;
    const netQuiet = s.armed ? s.pending === 0 : true;
    if (s.readyState === 'complete' && domQuiet && netQuiet) {
      if (stableSince === null) stableSince = Date.now();
      if (Date.now() - stableSince >= (s.armed ? 0 : quiet)) {
        const waited = Date.now() - started;
        return out(json, { settled: true, waitedMs: waited, ...s },
          `页面稳了（等了 ${waited}ms${s.armed ? '' : '；没装记录器，只看了 readyState 和 DOM 大小，未决请求看不到'}）。`);
      }
    } else {
      stableSince = null;
    }
    last = s;
    await sleep(150);
  }
  const s = await evaluate(target, PROBE_STATE);
  out(json, { settled: false, waitedMs: Date.now() - started, ...s },
    `等了 ${timeout}ms 还没稳：readyState=${s.readyState}，未决请求=${s.pending ?? '未知'}，`
    + `距上次 DOM 变动=${s.sinceMutation ?? '未知'}ms。\n`
    + `这本身就是证据——要么页面真的还在动，要么有请求挂着。别当成「大概好了」。`);
  process.exitCode = 2;
}

async function cmdConsole({ target, json, level }) {
  const entries = await evaluate(target, READ_CONSOLE);
  if (entries === null) {
    fail('页面没装记录器，console 是补不回来的。\n'
       + '先 arm，再操作页面，再回来读：\n'
       + `  node "${scriptDir()}/xman-verify.mjs" arm --target <ID>`);
  }
  const want = level === 'all' ? null : (level === 'error' ? ['error'] : ['error', 'warn']);
  const picked = want ? entries.filter((e) => want.includes(e.level)) : entries;
  out(json, { total: entries.length, level, entries: picked },
    picked.length === 0
      ? `没有 ${level === 'all' ? '任何' : level + ' 级'}输出（总共记录了 ${entries.length} 条）。`
      : picked.map((e) => `[${e.level}] ${e.text}`).join('\n'));
  if (picked.some((e) => e.level === 'error')) process.exitCode = 2;
}

async function cmdNetwork({ target, json, onlyFailed }) {
  const r = await evaluate(target, READ_NET);
  const merged = [...r.hooked];
  const seen = new Set(merged.map((x) => x.url));
  for (const e of r.observed) if (!seen.has(e.url)) merged.push(e);
  const failed = merged.filter((x) => x.ok === false || (x.status !== null && x.status >= 400));
  const list = onlyFailed ? failed : merged;
  const note = r.armed ? '' : '（没装记录器，只有浏览器自己记的资源列表：没有状态码，看不出失败）';
  out(json, { armed: r.armed, total: merged.length, failed: failed.length, requests: list },
    (list.length === 0 ? `没有请求记录${note}` : list.map((x) =>
      `${x.status ?? '---'} ${x.ok === false ? '✗' : ' '} ${x.url}${x.ms != null ? ` (${x.ms}ms)` : ''}${x.error ? ` — ${x.error}` : ''}`
    ).join('\n')) + (note && list.length ? `\n${note}` : ''));
  if (failed.length) process.exitCode = 2;
}

async function cmdDoctor({ json }) {
  const res = await request(`${BASE}/targets`);
  const targets = await res.json().catch(() => fail(
    `CDP Proxy 回了一个读不出来的响应（HTTP ${res.status}）。先检查共享服务：\n`
    + `  node "${scriptDir()}/proxy-maintenance.mjs" status\n`
    + `确认没有共享任务后再按 migration-2.6.md 维护。`));
  const n = Array.isArray(targets) ? targets.length : (targets?.length ?? 0);
  out(json, { proxy: BASE, ok: true, targets: targets },
    `Proxy 正常（${BASE}），当前 ${n} 个标签页。用 --target <ID> 指定要验证哪个。`);
}

// ─── 参数 ───
const HELP = {
  _: `xman-verify — 验证用的三个探针，架在 web-access 的 CDP Proxy 上

用法:
  node xman-verify.mjs <命令> [参数]

命令:
  arm           往页面注入记录器（console / fetch / XHR / DOM 变动）
  wait-settle   等页面真的稳下来，而不是猜它稳了
  console       读页面里的 console 输出（默认只给 error 和 warn）
  network       读请求列表，标出失败的
  doctor        看 Proxy 通不通、有哪些标签页

通用参数:
  --target <ID>       目标标签页，从 doctor 或 curl ${BASE}/targets 拿
  --json              机器可读输出
  --net-timeout <ms>  单次请求等多久算超时，默认 8000
  -h, --help      看某个命令的详细用法

典型顺序（复制就能用）:
  node xman-verify.mjs doctor
  node xman-verify.mjs arm --target ABC123
  # …在这中间用 curl 去点、去填、去跳转…
  node xman-verify.mjs wait-settle --target ABC123
  node xman-verify.mjs console --target ABC123
  node xman-verify.mjs network --target ABC123 --only-failed

注意: 页面跳转后注入的记录器会丢，跳转完要重新 arm。
退出码: 0 正常 / 1 用法或连接错误 / 2 发现了问题（有 error、有失败请求、没等稳）`,
  arm: `arm — 往页面注入记录器

console 和 network 的数据是注入之后才开始记的，补不回来，所以要先 arm 再操作页面。
重复 arm 不会装两遍。页面跳转后要重新 arm。

  --target <ID>   目标标签页
  --dry-run       只说会注入什么，不真注入
  --json          机器可读输出

例子:
  node xman-verify.mjs arm --target ABC123`,
  'wait-settle': `wait-settle — 等页面稳下来

判据三条同时成立才算稳: readyState=complete、没有未决请求、DOM 安静够久。
装过记录器的话三条都能看；没装只能看前一条加 DOM 大小，未决请求看不见。

  --target <ID>       目标标签页
  --timeout <ms>      最多等多久，默认 10000
  --quiet <ms>        DOM 安静多久算稳，默认 500
  --json              机器可读输出

超时不算失败，算证据: 退出码 2，并告诉你卡在哪一条。

例子:
  node xman-verify.mjs wait-settle --target ABC123 --timeout 15000`,
  console: `console — 读页面里的 console 输出

  --target <ID>            目标标签页
  --level error|warn|all   默认 warn（给 error + warn）
  --json                   机器可读输出

有 error 时退出码为 2。没 arm 过会直接报错并告诉你先 arm。

例子:
  node xman-verify.mjs console --target ABC123 --level error`,
  network: `network — 读请求列表

装过记录器的请求有状态码和失败原因；没装的话只有浏览器自己记的资源列表，
能看到发过什么、多久，但没有状态码，看不出失败。

  --target <ID>     目标标签页
  --only-failed     只列失败的
  --json            机器可读输出

有失败请求时退出码为 2。

例子:
  node xman-verify.mjs network --target ABC123 --only-failed`,
  doctor: `doctor — 看 Proxy 通不通、有哪些标签页

  --json   机器可读输出

例子:
  node xman-verify.mjs doctor`,
};

function parse(argv) {
  const opts = { json: false, dryRun: false, onlyFailed: false, level: 'warn', timeout: 10000, quiet: 500, help: false };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') opts.json = true;
    else if (a === '--dry-run') opts.dryRun = true;
    else if (a === '--only-failed') opts.onlyFailed = true;
    else if (a === '-h' || a === '--help') opts.help = true;
    else if (a === '--target') opts.target = argv[++i];
    else if (a === '--level') opts.level = argv[++i];
    else if (a === '--timeout') opts.timeout = parseInt(argv[++i], 10);
    else if (a === '--quiet') opts.quiet = parseInt(argv[++i], 10);
    else if (a === '--net-timeout') opts.netTimeout = parseInt(argv[++i], 10);
    else if (a.startsWith('-')) fail(`不认识的参数: ${a}\n看用法: node xman-verify.mjs --help`);
    else rest.push(a);
  }
  return { cmd: rest[0], opts };
}

const { cmd, opts } = parse(process.argv.slice(2));
if (opts.netTimeout) NET_TIMEOUT = opts.netTimeout;

if (!cmd || (opts.help && !HELP[cmd])) {
  process.stdout.write(`${HELP._}\n`);
  process.exit(cmd ? 0 : 1);
}
if (opts.help) {
  process.stdout.write(`${HELP[cmd]}\n`);
  process.exit(0);
}
if (!HELP[cmd]) fail(`不认识的命令: ${cmd}\n看用法: node xman-verify.mjs --help`);
if (cmd !== 'doctor' && !opts.target) {
  fail(`${cmd} 需要 --target <ID>。先看有哪些标签页:\n  node "${scriptDir()}/xman-verify.mjs" doctor`);
}

const run = { arm: cmdArm, 'wait-settle': cmdWaitSettle, console: cmdConsole, network: cmdNetwork, doctor: cmdDoctor }[cmd];
await run(opts);
