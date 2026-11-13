# 记录结构

## 事件文件

路径：
` .ai-configs/evolution/YYYY/MM/YYYYMMDD-HHMMSS-slug.md `

必填字段：

- `summary`：一句话描述错误
- `trigger`：是什么信号触发了这次记录
- `category`：错误分类
- `symptom`：外部看到的现象
- `wrong_decision`：错误做法、错误假设、错误路径
- `better_approach`：更好的方法或技术
- `guardrail`：以后默认遵守的规则

建议字段：

- `impact`：返工、风险、性能、正确性或用户体验影响
- `evidence`：测试输出、日志、文档、review 结论
- `related_files`：受影响文件
- `tags`：便于检索的关键词

推荐分类：

- `wrong-understanding`：误读需求、误解上下文
- `wrong-assumption`：未验证就假设
- `wrong-method`：采用了次优或错误方案
- `missing-verification`：未验证即交付
- `repeat-bug`：同类问题再次出现
- `better-tech-available`：已有更优技术替代旧路径

质量要求：

- 直接写出“错在哪里”，不要写“有待优化”
- 直接写出“以后怎么做”，不要写“下次注意”
- 如果说“更优”，必须说明优在什么维度

## 模式文件

路径：
` .ai-configs/evolution/patterns/slug.md `

模式用于长期规则，不记录瞬时噪音。建议字段：

- `problem`：反复出现的核心问题
- `avoid`：默认避免的做法
- `replace_with`：默认替代方案
- `decision_rule`：以后如何判断何时用新方案
- `verification`：以后如何证明规则生效
- `related_incidents`：关联的事件文件
- `tags`：稳定标签

升级条件：

- 同类问题出现 2 次及以上
- 已出现明确的更优替代技术
- 这个规则值得成为默认方法论

更新原则：

- 新方案推翻旧方案时，更新原模式文件，不要制造并列冲突规则
- 只保留仍然成立的指导，不要累积历史垃圾
