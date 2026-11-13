# x-mansion

一个集中管理 AI skill 的仓库。用一条 `xman` 命令，把研发流程、文档处理、设计、部署等 skill 装到 Claude Code、Codex、Cursor 和 Gemini CLI 里，改一处所有工具同步生效。

> **English**: x-mansion is a single home for your AI agent skills. One `xman` command installs a curated set of skills (requirements, PRD, planning, coding, review, docs, design, deployment) into Claude Code, Codex, Cursor and Gemini CLI through symlinks, so one edit takes effect everywhere. Skill content is mostly written in Chinese.

仓库里有 30 多个 skill，都是本仓自己写的。文档处理（docx / pdf / pptx / xlsx）、联网浏览（web-access）这类第三方 skill 不随仓库分发，需要时从各自的上游安装。

## 它能帮你做什么

- **研发流程**：从想清楚需求、写 PRD、写计划、照计划写代码，到审查、验收、提交，每一步都有对应的 skill，也可以交给 `xman-flow` 一次串起来。
- **不说空话**：说「完成了」要附本次运行的证据；审查只报有证据、会造成业务后果的问题。
- **不自作主张**：写文档、改代码、动 git、部署这类动作，只有你输入命令才会开始。
- **其他常用能力**：服务器部署和排障、旅行规划、向上汇报等。

## 快速开始

```bash
git clone https://github.com/hidingable/x-man.git
cd x-man
./xman setup                                  # 检查依赖、构建 plugin、校验仓库
./xman install claude --status team-shared    # 把稳定的 skill 装到 Claude Code
```

需要 Python 3.9+ 和 PyYAML；`./xman doctor` 会检查环境，缺什么告诉你怎么装。

装到某个项目里，并生成项目上下文：

```bash
./xman install claude --project /path/to/project
./xman context init /path/to/project
```

然后打开项目里的 `.ai-configs/project-context.md`，把 `[待填写]` 的地方补上。更多上手细节见 [QUICKSTART.md](QUICKSTART.md)。

## 装好之后怎么用

**不知道该用哪个命令时，输入 `/ask-xman`**，说一下处境，它会推荐一个。

常见场景：

| 我想…… | 输入 |
| --- | --- |
| 把一个模糊的想法想清楚 | `/brainstorm` |
| 分析需求，或者只把想法磨清楚 | `/req-analyze`（只想追问时说「只追问」） |
| 写 PRD / 改 PRD | `/prd`（改的时候说「更新 PRD」） |
| 先定接口、类型和模块边界 | `/architect` |
| 写编码计划 / 按计划写代码 | `/create-plan` / `/code-by-plan` |
| 提交代码、写 PR / MR 描述 | `/git-commit` |
| 从需求到交付整条交出去 | 用 `xman-flow` agent，直接说「完整流程做一下 xxx」 |

报 bug、「review 一下」、「上线前检查一下」、「用 TDD 做」这类，直接说就行，AI 会自己用上对应的 skill。

## 有哪些 skill

运行 `./xman list` 看完整清单和说明。按用途大致分成：

| 类别 | 主要 skill |
| --- | --- |
| 研发流程 | brainstorm、req-analyze、prd、design、architect、create-plan、code-by-plan、git-commit |
| 质量与验证 | review、bug-fix、harness、tdd-guard、spec-query、code-archaeology |
| 收尾与记忆 | reflect、neat-freak |
| 设计与原型 | apple-ui-motion-system |
| 文档与沟通 | technical-writing、xiangshang-huibao、to-questionnaire |
| 工程与部署 | server-deploy、server-ops-safe、resolving-merge-conflicts |
| 小工具 | ask-xman、handoff、human-speak、explain、html-view、guardrails、ascii-card、writing-for-agents、domain-terms、wizard |

每个 skill 有一个状态：

- **team-shared**：已经稳定，推荐默认安装，`--status team-shared` 装的就是这一批。
- **experimental**：还在试验，行为可能调整，按需单独装（`--skill <名称>`）。
- **personal-only**：绑定你自己的服务器或账号。仓库里不带这类 skill；你可以在本地加，并在 `.gitignore` 里列出，它们不会进入提交。

另外有一个 agent：`xman-flow`（研发流程编排）。

## 安装选项

```bash
./xman install claude                          # 全部 skill 装到 Claude Code（全局）
./xman install all --status team-shared        # 稳定的装到所有工具
./xman install claude --skill review --skill bug-fix   # 只装指定的几个
./xman install claude --agent xman-flow        # 装编排 agent
./xman install claude --project .              # 装到当前项目
./xman install claude --dry-run                # 只预览，不写文件
```

安装用的是软链：改了仓库里的 skill，装过的地方立刻生效。

也可以用 plugin 方式装，在仓库目录下运行：

```bash
./xman plugin build
claude plugin marketplace add ./
claude plugin install x-mansion@x-mansion-lab
```

plugin 打包 registry 里全部未废弃的 skill 和 agent。

## 项目里会多出什么

`./xman context init` 会在项目里建 `.ai-configs/`，**建议整个提交进 Git**：

- `project-context.md`：项目背景，各 skill 都会读。
- `conventions.md`：文档放哪、怎么命名的约定。本仓库更新后，用 `./xman context init --refresh-conventions` 刷新。
- 各阶段文档：默认按类型和月份归档；一条需求跨好几天时，先 `./xman task new <名称>` 建 task，再按提示 `./xman task use <id>` 切换过去，之后的文档会集中到 `.ai-configs/tasks/<id>/`。

## 参与贡献

欢迎提 issue 和 PR。改动前先看这几条：

- 维护规则见 [CLAUDE.md](CLAUDE.md)，skill 写法见 [docs/SKILL-SPEC.md](docs/SKILL-SPEC.md) 和 `writing-for-agents` skill，状态和来源管理见 [governance/README.md](governance/README.md)，考虑过但不做的事见 [.out-of-scope/](.out-of-scope/)。
- 新建 skill：`./xman new <名称> --plugin <分组>`，然后在 `governance/skills-registry.csv` 登记。
- 改完运行：

  ```bash
  ./xman validate
  python3 -B -m unittest discover -s tests
  ```

- 改动影响 skill 行为时，用 `scripts/eval-run.py` 跑行为对照。

## 许可证

本项目使用 [MIT](LICENSE) 许可证。
