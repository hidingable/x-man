#!/bin/bash
# 给 bash 脚本用的 JSON 输出helper。
#
# 为什么不在 bash 里手拼 JSON：字段里出现引号、反斜杠、换行、中文都会把手拼的字符串搞坏，
# 而这些恰好是 title、note 这类字段的常客。这里统一在 bash 里产 TSV，交给 python 转 JSON，
# 转义的事一次做对。

# tsv_safe <值> —— 把制表符和换行换成空格。TSV 用它们当分隔符，值里再出现就会把字段冲串。
# title、note 这类字段是用户随手写的，什么都可能有。
tsv_safe() {
  local v="${1:-}"
  v="${v//$'\t'/ }"
  v="${v//$'\n'/ }"
  v="${v//$'\r'/ }"
  printf '%s' "${v}"
}

# json_rows <字段名>... —— 从 stdin 读 TSV（每行一条记录，字段顺序同参数），输出 JSON 数组
json_rows() {
  python3 -c '
import json, sys
fields = sys.argv[1:]
def coerce(v):
    return {"true": True, "false": False}.get(v, v)
rows = []
for line in sys.stdin.read().splitlines():
    if not line:
        continue
    parts = line.split("\t")
    parts += [""] * (len(fields) - len(parts))
    rows.append({k: coerce(v) for k, v in zip(fields, parts[:len(fields)])})
print(json.dumps(rows, ensure_ascii=False, indent=2))
' "$@"
}

# json_object <k> <v> <k> <v>... —— 输出 JSON 对象；值里带 \t 或换行也安全
json_object() {
  python3 -c '
import json, sys
args = sys.argv[1:]
print(json.dumps(dict(zip(args[::2], args[1::2])), ensure_ascii=False, indent=2))
' "$@"
}

# json_wrap <键> <字段名>... —— 同 json_rows，但包一层 {"<键>": [...]}
json_wrap() {
  local key="$1"; shift
  python3 -c '
import json, sys
key = sys.argv[1]
fields = sys.argv[2:]
def coerce(v):
    return {"true": True, "false": False}.get(v, v)
rows = []
for line in sys.stdin.read().splitlines():
    if not line:
        continue
    parts = line.split("\t")
    parts += [""] * (len(fields) - len(parts))
    rows.append({k: coerce(v) for k, v in zip(fields, parts[:len(fields)])})
print(json.dumps({key: rows}, ensure_ascii=False, indent=2))
' "$key" "$@"
}
