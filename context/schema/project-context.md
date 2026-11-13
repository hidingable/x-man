# project-context.md Schema

项目上下文文件的字段定义。用于 `xman context init` 的自动探测和校验。

## 字段状态标记

字段值有三种非最终态，含义和校验行为各不相同：

| 标记 | 含义 | `xman context check` |
|---|---|---|
| `[待填写]` | 未填写 | exit 2，skill 拒绝执行 |
| `[不适用]` | 按项目形态判定与本项目无关（如后端项目的主色调） | 视为已完成 |
| `⟨待确认⟩` | 自动探测填入、尚未人工核对 | exit 2，`xman context confirm` 清除 |

`[不适用]` 由 `scripts/detect-project.py` 推断的项目形态决定，且**只在探测器未给出值时**才标记——探测到的事实优先于形态推断。

## 子工程（monorepo）

多工程同仓时，「子工程」一节列出每个子工程的路径、形态和技术栈；技术栈字段本身取各子工程的并集。单工程仓库该节为 `[不适用]`。

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| 子工程 | table | 否 | workspaces / pnpm-workspace.yaml / lerna.json / nx.json / turbo.json，或根下带构建清单的子目录 |

## 字段定义

### 基础信息（必填）

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| 项目名称 | string | 是 | package.json name / 目录名 |
| 项目描述 | string | 是 | package.json description / README |
| 仓库地址 | string | 是 | git remote |
| 当前版本 | string | 是 | package.json version |

### 技术栈（必填）

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| 语言 | string | 是 | 文件扩展名 / tsconfig.json / pyproject.toml |
| 前端框架 | string | 否 | package.json dependencies |
| UI 组件库 | string | 否 | package.json dependencies |
| 状态管理 | string | 否 | package.json dependencies |
| 后端框架 | string | 否 | package.json / pom.xml / go.mod |
| 数据库 | string | 否 | docker-compose / 配置文件 |
| 构建工具 | string | 否 | vite.config / webpack.config |
| 包管理器 | string | 否 | lock 文件类型 |

### 项目结构（推荐）

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| 关键目录 | text | 否 | ls src/ / app/ / lib/ |

### 设计规范（可选）

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| 设计系统 | string | 否 | 手动填写 |
| 主色调 | string | 否 | 手动填写 |
| 字体 | string | 否 | 手动填写 |
| 响应式断点 | string | 否 | 手动填写 |

### 编码规范（推荐）

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| 代码风格 | string | 否 | .eslintrc / .prettierrc |
| 命名约定 | string | 否 | 手动填写 |
| Git 分支策略 | string | 否 | 手动填写 |
| 提交规范 | string | 否 | commitlint.config |

### 业务领域（推荐）

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| 产品类型 | string | 否 | 手动填写 |
| 核心业务 | string | 否 | README |
| 目标用户 | string | 否 | 手动填写 |

### 领域术语与歧义裁定（可选）

本节在现有 `project-context.md` 内按需维护，不自动探测，不要求另建文件。

| 字段 | 说明 |
|---|---|
| 规范名称或歧义事项 | 项目选用的业务名称，或已经实际出现的歧义问题 |
| 定义、结论与适用边界 | 已确认的含义与范围；待定时写清尚未确定的内容 |
| 易混淆叫法、其他理解及实际区别 | 区分同义叫法与不同概念；没有已知混淆时可留空 |
| 事实或裁定依据 | 可定位的需求、契约、代码事实或用户裁定；注明适用版本或场景 |
| 状态 | 普通文本 `已确认` 或 `待定`；只有相关证据或用户裁定明确后才能改为已确认 |

读写条件按 `domain-terms` skill 执行。旧项目缺少本节、空表或含待定条目均不影响 `context check`；待定事项是否影响当前任务由其实际范围决定。
状态不使用自动探测标记；`context init --auto` 和 `context confirm` 不裁定业务歧义，`context check` 通过也不代表表中结论已确认。

### 团队约束（可选）

| 字段 | 类型 | 必填 | 探测源 |
|------|------|------|--------|
| Review 流程 | string | 否 | .github / 手动填写 |
| 测试要求 | string | 否 | 手动填写 |
| 部署方式 | string | 否 | CI 配置 / Dockerfile |

## 完整性校验规则

`xman context check` 的退出码语义：

- project-context.md 不存在，或 `.ai-configs/conventions.md` 缺失 / 软链不可达 → exit code 1
- 文件存在但包含 `[待填写]` 占位符或 `⟨待确认⟩` 标记（探测结果未经 `xman context confirm` 确认）→ exit code 2
- 文件存在、conventions.md 可达，且无 `[待填写]` / `⟨待确认⟩` → exit code 0
