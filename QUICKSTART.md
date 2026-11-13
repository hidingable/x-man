# x-mansion Quickstart

## 首次设置

```bash
git clone https://github.com/hidingable/x-man.git
cd x-man
./xman setup         # 检查依赖 + 构建 plugin + 校验仓库
```

## 升级老项目到 task 模式

如果项目已经在使用 ad-hoc 路径（`.ai-configs/plan/...`、`.ai-configs/analysis/...` 等），升级到支持 task 模式只需两步，**老产物文件不需要迁移**——ad-hoc 路径仍是一等公民，永久并存。

```bash
cd /path/to/old-project

# 1. 重装 skill 软链，拉取去硬编码后的 SKILL.md
./xman install claude --project .       # 或 codex / cursor / gemini / all

# 2. 幂等补 task/workspace 骨架（不覆盖已填字段；仍为 [待填写] 的字段会被探测值预填并标 ⟨待确认⟩）
./xman context init
```

验证升级：

```bash
./xman context status                    # 应能看到 tasks/ 和 journal.md 状态
./xman task new test --title "迁移验证"  # 在项目根目录跑
./xman task current                       # 应输出 2026-MM-test
```

可选：在项目自己的 `.gitignore` 加一行 `.ai-configs/.current-task`，避免本地 task 切换状态被推到远程。

`.ai-configs/conventions.md` 默认以真实文件落到项目中，应随项目提交；母仓更新后重跑 `xman context init` 刷新。只有母仓维护者临时调试约定时才用 `xman context init --link`，该软链是本机绝对路径，不能提交。

> 路径约定的单一事实源是母仓的 `context/conventions.md`；业务项目通过 `.ai-configs/conventions.md` 访问它，包含 task / ad-hoc 双轨决策树和 join key 规则。

## 安装 skill

安装通过软链实现，skill 目录不会被复制，本地修改即时生效。

### 安装到全局

```bash
# 安装全部 skill
./xman install claude

# 只安装团队共享的 skill
./xman install claude --status team-shared

# 安装到其他平台
./xman install codex --status team-shared
./xman install cursor --status team-shared
./xman install gemini --status team-shared

# 一次安装到所有平台
./xman install all --status team-shared
```

各平台的全局和项目级安装目录以 `context/platforms.md` 为准。

### 安装到项目根目录

```bash
# 安装到项目级 skill 目录
./xman install claude --project /path/to/my-project

# 安装到其他平台的项目级 skill 目录
./xman install codex --project /path/to/my-project

# 只安装团队共享的到项目
./xman install claude --project /path/to/my-project --status team-shared
```

### 安装单个 skill

```bash
# 安装单个 skill 到全局
./xman install claude --skill review

# 安装单个 skill 到项目根目录
./xman install claude --skill review --project /path/to/my-project

# 安装多个指定 skill
./xman install claude --skill tdd-guard --skill bug-fix --skill review

# 安装某个 plugin 分组下的所有 skill
./xman install claude --plugin engineering
```

### 其他安装选项

```bash
# 仅预览，不实际写入
./xman install claude --dry-run

# 清理目标中不在本次选择内的旧软链
./xman install claude --status team-shared --clean

# 覆盖默认目标目录（优先级最高）
./xman install claude --target /custom/path
```

## 全局精简策略（推荐）

为了控制 AI 工具启动时的上下文占用，建议**全局只装跨项目高频的工作流 skill**，特化能力（设计、文档、服务器、公司内网）按项目按需安装到项目级 skill 目录。

### 全局基线（16 个 skill）

```bash
./xman install claude \
  --skill brainstorm --skill req-analyze --skill prd --skill design \
  --skill create-plan --skill code-by-plan --skill bug-fix --skill review \
  --skill git-commit --skill find-skills --skill skill-creator \
  --skill web-access --skill reflect --skill docx \
  --skill claude-api --skill ui-ux-pro-max \
  --clean
```

预期全局基线的 Skills 部分上下文 ~1.5k tokens。

### 项目级按需挂载

不同类型项目挂不同 plugin，进项目即用：

```bash
# 前端项目
./xman install claude --project ~/path/frontend-app --plugin design \
  --skill vercel-react-best-practices --skill webapp-testing --clean

# 后端 / 全栈
./xman install claude --project ~/path/api-app --plugin engineering --clean

# 服务器运维项目（按需挑单个）
./xman install claude --project ~/path/ops --skill server-ops-safe

# 文档处理项目
./xman install claude --project ~/path/docs --skill pdf --skill docx --skill xlsx --skill pptx
```

### 可用 plugin 分组

| Plugin | 用途 |
|---|---|
| `product` | 产品工作流（brainstorm/prd/req-analyze/...） |
| `engineering` | 工程工作流（bug-fix/review/code-by-plan/...） |
| `design` | 设计/前端 |
| `general` | 通用工具 |
| `infra` | 通用服务器部署与运维 |

## 浏览 skill

```bash
./xman list                          # 全部 skill 分组概览
./xman list --status team-shared     # 只看团队共享
./xman list --plugin engineering     # 只看工程组
./xman list --compact                # 纯名字（适合管道）
./xman source list                   # 查看本地 / 外部来源
```

## 新增 skill

```bash
./xman new my-skill --plugin engineering    # 创建脚手架 + CSV + 软链
# 编辑 skills/my-skill/SKILL.md
./xman validate                             # 确认一致性
```

## 校验

```bash
./xman validate              # 完整校验
./xman validate --fix        # 自动修复（team 软链、CSV 排序）
./xman check-team            # 只检查 team 软链一致性
./xman audit                 # 对账本机与仓库
./xman update --skill docx    # 预览单个 external skill 的更新
./xman update --apply        # 应用全部 external skill 更新
```

## 发布

```bash
./xman publish team --target /path/to/team-skills
./xman publish personal --target /path/to/personal-skills
```

## 完整帮助

```bash
./xman                       # 查看所有命令
./xman <命令> --help          # 查看子命令详细帮助
```
