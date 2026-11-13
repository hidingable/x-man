# 决策日志 Schema

决策日志记难以撤回、当时有过真实取舍的决定，让后来的人知道为什么这样做。什么决定值得记，判据在 `domain-terms` skill 的〈决策日志〉。

一个决定一个文件，YAML 格式，路径按 `context/conventions.md`：`.ai-configs/decisions/YYYY-MM-DD-{slug}.yaml`。

## 字段

```yaml
date: string        # YYYY-MM-DD，做出决定的日期
decision: string    # 定了什么，一句话，用实际名称
context: string     # 当时要解决的问题和约束
options:            # 认真考虑过的备选，至少一个没选的
  - name: string
    rejected_because: string
rationale: string   # 为什么选这个
evidence: [string]  # 依据的位置：需求、契约、代码、用户裁定
revisit_when: string  # 什么条件变了就该重新考虑；想不出就写「无」
task: string        # 关联的 task-id；没有就省略
```

`date`、`decision`、`options`、`rationale` 必填。决定被推翻时新建一个文件，在 `context` 里写明它取代哪一个，旧文件保留。
