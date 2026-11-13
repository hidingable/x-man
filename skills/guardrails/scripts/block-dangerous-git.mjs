#!/usr/bin/env node
// Claude Code PreToolUse hook：拦截会丢失工作或影响远端的 git 命令。
// 从标准输入读 hook 的 JSON，命中时以退出码 2 结束，stderr 的内容会作为原因交给模型。

// git 后面可能跟全局选项（-C <路径>、-c <配置>、--no-pager 等），先跳过它们再看子命令
const GIT = String.raw`\bgit\s+(?:-[Cc]\s+\S+\s+|--?[\w-]+(?:=\S+)?\s+)*`;
const rule = (sub, reason) => ({ pattern: new RegExp(GIT + sub), reason });

const RULES = [
  rule(String.raw`push\b`, 'git push 会影响远端仓库'),
  rule(String.raw`reset\s+(?:\S+\s+)*--hard\b`, 'git reset --hard 会丢弃未提交的改动'),
  rule(String.raw`clean\s+(?:\S+\s+)*-[a-zA-Z]*f`, 'git clean -f 会删除未跟踪的文件'),
  rule(String.raw`branch\s+(?:\S+\s+)*-D\b`, 'git branch -D 会强制删除分支'),
  rule(String.raw`checkout\s+(?:--\s+)?\.(?:\s|$)`, 'git checkout . 会丢弃工作区改动'),
  rule(String.raw`restore\s+(?:\S+\s+)*\.(?:\s|$)`, 'git restore . 会丢弃工作区改动'),
];

export function check(command) {
  const hit = RULES.find((rule) => rule.pattern.test(command));
  return hit ? hit.reason : null;
}

async function main() {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  let command = '';
  try {
    command = JSON.parse(input)?.tool_input?.command ?? '';
  } catch {
    return; // 读不懂输入时放行，不因 hook 自身问题卡住正常工作
  }
  const reason = check(String(command));
  if (reason) {
    process.stderr.write(`已拦截：${reason}。这类命令需要用户亲自执行；需要时请把命令告诉用户。\n`);
    process.exit(2);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) main();
