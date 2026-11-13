# 对接 GitHub / GitLab issue tracker

**是什么**：把 PRD、编码计划、任务拆分直接发布成 issue，用 issue 的阻塞关系表示依赖。

**为什么不做**：产物统一放在项目的 `.ai-configs/` 里，跟着代码走、离线可用，命名契约也已经围绕它建立。接入 tracker 要处理鉴权、内网地址和不同 tracker 的差异。

**什么时候重新评估**：团队要求需求和任务必须在 tracker 里流转，并且有统一的 tracker。
