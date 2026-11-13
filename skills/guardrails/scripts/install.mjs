#!/usr/bin/env node
// 把 git 拦截 hook 装进 Claude Code 的 settings.json（项目级或全局），可重复运行，可卸载。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HOOK_SOURCE = path.join(path.dirname(fileURLToPath(import.meta.url)), 'block-dangerous-git.mjs');
const HOOK_NAME = 'wf-block-dangerous-git.mjs';

const HELP = `用法: node install.mjs --scope <project|global> [选项]

把拦截危险 git 命令的 PreToolUse hook 装进 Claude Code 设置。重复运行不会重复添加。

选项:
  --scope project      装到项目：<项目>/.claude/settings.json，hook 脚本放 <项目>/.claude/hooks/
  --scope global       装到全局：~/.claude/settings.json，hook 脚本放 ~/.claude/hooks/
  --project <目录>     项目根目录（默认当前目录，只在 --scope project 时使用）
  --uninstall          移除 hook 配置和脚本
  --dry-run            只显示将要做的改动，不写文件
  --json               以 JSON 输出结果
  -h, --help           显示帮助

例子:
  node install.mjs --scope project --dry-run
  node install.mjs --scope global --json`;

function parseArgs(argv) {
  const opts = { project: process.cwd() };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = () => {
      const value = argv[++i];
      if (value === undefined) throw new Error(`${arg} 缺少参数值，运行 --help 查看用法`);
      return value;
    };
    if (arg === '--scope') opts.scope = next();
    else if (arg === '--project') opts.project = path.resolve(next());
    else if (arg === '--uninstall') opts.uninstall = true;
    else if (arg === '--dry-run') opts.dryRun = true;
    else if (arg === '--json') opts.json = true;
    else if (arg === '-h' || arg === '--help') opts.help = true;
    else throw new Error(`未知参数 ${arg}，运行 --help 查看用法`);
  }
  if (!opts.help && !['project', 'global'].includes(opts.scope)) {
    throw new Error('缺少 --scope，取值 project 或 global；运行 --help 查看用法');
  }
  return opts;
}

function targets(opts) {
  const base = opts.scope === 'global' ? path.join(os.homedir(), '.claude') : path.join(opts.project, '.claude');
  const hookFile = path.join(base, 'hooks', HOOK_NAME);
  const command = opts.scope === 'global'
    ? `node "${hookFile}"`
    : `node "$CLAUDE_PROJECT_DIR"/.claude/hooks/${HOOK_NAME}`;
  return { settingsFile: path.join(base, 'settings.json'), hookFile, command };
}

function readSettings(file) {
  if (!fs.existsSync(file)) return {};
  const text = fs.readFileSync(file, 'utf8');
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${file} 不是合法的 JSON，先修好它再运行（本脚本不会覆盖无法解析的设置文件）`);
  }
}

const isOurs = (entry) => (entry.hooks || []).some((h) => String(h.command || '').includes(HOOK_NAME));

function apply(opts) {
  const { settingsFile, hookFile, command } = targets(opts);
  const settings = readSettings(settingsFile);
  const pre = settings.hooks?.PreToolUse || [];
  const present = pre.some(isOurs);
  const actions = [];

  if (opts.uninstall) {
    if (present) actions.push(`从 ${settingsFile} 移除 hook 配置`);
    if (fs.existsSync(hookFile)) actions.push(`删除 ${hookFile}`);
  } else {
    if (!present) actions.push(`在 ${settingsFile} 的 hooks.PreToolUse 加入 Bash 拦截`);
    const same = fs.existsSync(hookFile) && fs.readFileSync(hookFile, 'utf8') === fs.readFileSync(HOOK_SOURCE, 'utf8');
    if (!same) actions.push(`写入 ${hookFile}`);
  }

  if (!opts.dryRun) {
    if (opts.uninstall) {
      if (present) {
        settings.hooks.PreToolUse = pre.filter((entry) => !isOurs(entry));
        if (!settings.hooks.PreToolUse.length) delete settings.hooks.PreToolUse;
        if (!Object.keys(settings.hooks).length) delete settings.hooks;
        fs.writeFileSync(settingsFile, JSON.stringify(settings, null, 2) + '\n');
      }
      fs.rmSync(hookFile, { force: true });
    } else {
      fs.mkdirSync(path.dirname(hookFile), { recursive: true });
      fs.copyFileSync(HOOK_SOURCE, hookFile);
      fs.chmodSync(hookFile, 0o755);
      if (!present) {
        settings.hooks ||= {};
        settings.hooks.PreToolUse = [...pre, { matcher: 'Bash', hooks: [{ type: 'command', command }] }];
        fs.mkdirSync(path.dirname(settingsFile), { recursive: true });
        fs.writeFileSync(settingsFile, JSON.stringify(settings, null, 2) + '\n');
      }
    }
  }
  return { scope: opts.scope, settings_file: settingsFile, hook_file: hookFile, dry_run: !!opts.dryRun, uninstall: !!opts.uninstall, actions };
}

try {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    console.log(HELP);
  } else {
    const result = apply(opts);
    if (opts.json) console.log(JSON.stringify(result, null, 2));
    else if (!result.actions.length) console.log('已是目标状态，没有需要改动的地方');
    else console.log(`${result.dry_run ? '将要执行' : '已执行'}：\n${result.actions.map((a) => `- ${a}`).join('\n')}`);
  }
} catch (err) {
  console.error(err.message);
  process.exit(1);
}
