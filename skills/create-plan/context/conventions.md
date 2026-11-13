# create-plan 路径约定入口

本 skill 不复制路径规则，避免与项目级唯一事实源发生漂移。

完整约定见**项目内**的 `.ai-configs/conventions.md`——由 `xman context init` 软链到母仓 `context/conventions.md`（或以 `--copy` 落为本地副本）。使用 `create-plan` 前必须完整读取该文件，并以其 task 解析、join key 命名和计划落盘规则为准。

若该文件不存在或软链已断，说明项目未初始化上下文，先运行 `xman context init`——缺了它，产物路径与 task-id 前缀都无从解析。
