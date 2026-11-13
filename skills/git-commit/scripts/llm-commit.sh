#!/usr/bin/env bash
# llm-commit.sh — 通过 OpenAI 兼容 API 用外部模型生成 Conventional Commits 提交信息
#
# 配置（三项齐全才启用，否则 exit 2，由 skill 回退到 Claude 自带模型）：
#   COMMIT_LLM_BASE_URL   如 https://api.deepseek.com
#   COMMIT_LLM_MODEL      如 deepseek-chat
#   COMMIT_LLM_API_KEY    密钥，只从环境或本地 env 文件读取，不入库
# 可选：
#   COMMIT_LLM_API_FORMAT   openai（默认，/chat/completions）或 anthropic（/v1/messages，
#                           如火山方舟 coding 端点 https://ark.cn-beijing.volces.com/api/coding）
#   COMMIT_LLM_TIMEOUT      总超时秒数，默认 30
#   COMMIT_LLM_MAX_DIFF_KB  diff 超过该大小降级为 stat 模式，默认 100
#   COMMIT_LLM_SKIP_SCAN=1  跳过外发前的密钥扫描
#
# 配置来源优先级：shell 环境变量 > 同目录 llm-commit.env（已 gitignore，模板见 llm-commit.env.example）
#
# 退出码：0 成功（stdout 为纯 commit message）
#         2 未配置外部模型   3 API 调用失败/超时   4 暂存区为空   5 diff 疑似含密钥，拒绝外发
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/llm-commit.env"

# ---------- 参数 ----------
OPT_TYPE="" OPT_SCOPE="" OPT_EMOJI=0 OPT_LANG="auto" DIFF_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type)      OPT_TYPE="$2"; shift 2 ;;
    --scope)     OPT_SCOPE="$2"; shift 2 ;;
    --emoji)     OPT_EMOJI=1; shift ;;
    --lang)      OPT_LANG="$2"; shift 2 ;;
    --diff-file) DIFF_FILE="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done

# ---------- 配置解析：env 文件只填补 shell 环境中未设置的变量 ----------
ZWSP=$(printf '\xe2\x80\x8b')   # 零宽空格，网页复制常见杂质
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^(COMMIT_LLM_[A-Z_]+)=(.*)$ ]] || continue
    key="${BASH_REMATCH[1]}"; val="${BASH_REMATCH[2]}"
    val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
    val="${val//$ZWSP/}"; val="${val//$'\r'/}"
    [[ -z "${!key:-}" ]] && export "$key=$val"
  done < "$ENV_FILE"
fi

if [[ -z "${COMMIT_LLM_BASE_URL:-}" || -z "${COMMIT_LLM_MODEL:-}" || -z "${COMMIT_LLM_API_KEY:-}" ]]; then
  echo "llm-commit: 外部模型未配置（需 COMMIT_LLM_BASE_URL / COMMIT_LLM_MODEL / COMMIT_LLM_API_KEY），回退本地生成" >&2
  exit 2
fi

TIMEOUT="${COMMIT_LLM_TIMEOUT:-30}"
MAX_DIFF_KB="${COMMIT_LLM_MAX_DIFF_KB:-100}"
API_FORMAT="${COMMIT_LLM_API_FORMAT:-openai}"

command -v jq >/dev/null || { echo "llm-commit: 缺少依赖 jq" >&2; exit 3; }

# ---------- 收集 diff ----------
if [[ -n "$DIFF_FILE" ]]; then
  DIFF_CONTENT="$(cat "$DIFF_FILE")"
  LOG_SUBJECTS=""
else
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "llm-commit: 不在 git 仓库内" >&2; exit 4; }
  DIFF_CONTENT="$(git diff --cached)"
  LOG_SUBJECTS="$(git log -n 20 --pretty=%s 2>/dev/null || true)"
fi
[[ -n "$DIFF_CONTENT" ]] || { echo "llm-commit: 暂存区为空" >&2; exit 4; }

# ---------- 外发前密钥扫描 ----------
if [[ "${COMMIT_LLM_SKIP_SCAN:-}" != "1" ]]; then
  SECRET_PATTERNS='AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|(api[_-]?key|secret|token|password)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_\-]{20,}'
  if MATCHED=$(printf '%s' "$DIFF_CONTENT" | grep -nEio "$SECRET_PATTERNS" | head -3); then
    echo "llm-commit: diff 中检出疑似密钥，已拒绝外发（COMMIT_LLM_SKIP_SCAN=1 可跳过）：" >&2
    echo "$MATCHED" >&2
    exit 5
  fi
fi

# ---------- 大 diff 降级 ----------
DIFF_BYTES=${#DIFF_CONTENT}
if (( DIFF_BYTES > MAX_DIFF_KB * 1024 )); then
  STAT="$(git diff --cached --stat 2>/dev/null || true)"
  DIFF_CONTENT="[diff 过大（$((DIFF_BYTES/1024))KB），以下为变更统计与截断后的 diff]
${STAT}

$(printf '%s' "$DIFF_CONTENT" | head -c $((MAX_DIFF_KB * 1024 / 4)))"
fi

# ---------- 语言判定 ----------
LANG_RULE="Match the language of the recent commit subjects; if unclear, use English."
case "$OPT_LANG" in
  zh) LANG_RULE="Write the commit message in Chinese." ;;
  en) LANG_RULE="Write the commit message in English." ;;
  auto)
    if printf '%s' "$LOG_SUBJECTS" | grep -q '[一-龥]'; then
      LANG_RULE="Write the commit message in Chinese."
    fi ;;
esac

# ---------- Prompt ----------
EMOJI_RULE="Do NOT include any emoji."
if [[ "$OPT_EMOJI" == "1" ]]; then
  # 与 SKILL.md 的 Type/Emoji 映射表保持一致，改表时两处同步
  EMOJI_RULE='Prefix the subject with the matching emoji: ✨ feat, 🐛 fix, 📝 docs, 🎨 style, ♻️ refactor, ⚡️ perf, ✅ test, 🔧 chore, 👷 ci, ⏪️ revert, 💥 breaking feat, ⬆️/⬇️ chore deps.'
fi
TYPE_RULE=""; [[ -n "$OPT_TYPE" ]] && TYPE_RULE="The commit type MUST be: ${OPT_TYPE}."
SCOPE_RULE=""; [[ -n "$OPT_SCOPE" ]] && SCOPE_RULE="The scope MUST be: (${OPT_SCOPE})."

SYSTEM_PROMPT="You generate git commit messages in Conventional Commits format.
Output ONLY the raw commit message: a subject line, then a blank line, then an optional body. No markdown, no code fences, no explanations.
Rules:
- Format: <type>(<scope>)?: <subject> ; allowed types: feat fix docs style refactor perf test chore ci revert
- Subject <= 72 chars, imperative mood
- Body explains motivation and key changes; add a BREAKING CHANGE: section only if applicable
- Use literal, purpose-based wording. Never use metaphors or opaque sequence labels such as 第一刀, 第二刀, 第一批, 第二批, commit 1, or commit 2
- ${LANG_RULE}
- ${EMOJI_RULE}
${TYPE_RULE}
${SCOPE_RULE}"

USER_PROMPT="Recent commit subjects (for style reference):
${LOG_SUBJECTS:-<none>}

Staged diff:
${DIFF_CONTENT}"

if [[ "$API_FORMAT" == "anthropic" ]]; then
  # Anthropic Messages 格式；max_tokens 放宽，thinking 类模型会先消耗推理 token
  PAYLOAD=$(jq -n --arg model "$COMMIT_LLM_MODEL" --arg sys "$SYSTEM_PROMPT" --arg usr "$USER_PROMPT" \
    '{model:$model, temperature:0.2, max_tokens:2048, system:$sys, messages:[{role:"user",content:$usr}]}')
  ENDPOINT="${COMMIT_LLM_BASE_URL%/}/v1/messages"
  EXTRA_HEADER="anthropic-version: 2023-06-01"
  JQ_EXTRACT='[.content[]? | select(.type=="text") | .text] | join("")'
else
  PAYLOAD=$(jq -n --arg model "$COMMIT_LLM_MODEL" --arg sys "$SYSTEM_PROMPT" --arg usr "$USER_PROMPT" \
    '{model:$model, temperature:0.2, max_tokens:512, messages:[{role:"system",content:$sys},{role:"user",content:$usr}]}')
  ENDPOINT="${COMMIT_LLM_BASE_URL%/}/chat/completions"
  EXTRA_HEADER="x-llm-commit: openai"
  JQ_EXTRACT='.choices[0].message.content // empty'
fi

# ---------- 调用 API（key 经 curl 配置流传入，不出现在进程参数） ----------
RESPONSE=$(curl -sS -m "$TIMEOUT" --connect-timeout 5 \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$COMMIT_LLM_API_KEY") \
  -H "Content-Type: application/json" \
  -H "$EXTRA_HEADER" \
  -d "$PAYLOAD" \
  "$ENDPOINT") || { echo "llm-commit: API 请求失败" >&2; exit 3; }

MESSAGE=$(printf '%s' "$RESPONSE" | jq -r "$JQ_EXTRACT" 2>/dev/null || true)
if [[ -z "$MESSAGE" ]]; then
  echo "llm-commit: 响应解析失败：" >&2
  printf '%s' "$RESPONSE" | head -c 500 >&2; echo >&2
  exit 3
fi

# 清理可能的 markdown 围栏与首尾空行
printf '%s\n' "$MESSAGE" | sed '/^```/d' | sed -e '/./,$!d' -e :a -e '/^\n*$/{$d;N;ba' -e '}'
