---
name: codex-security
description: "OpenAI Codex Security 防御性代码审查。覆盖仓库及变更的源码安全审查、威胁建模、漏洞分诊、修复和跟踪。触发词：安全扫描、安全审查、威胁建模、漏洞验证、漏洞分诊、攻击路径分析、SECURITY.md 策略。"
metadata:
  category: engineering
  tags: [security, code-review, threat-modeling, appsec, vulnerability]
  dependencies: []
  requires_context: []
---

# Codex Security

使用本地运行包审查授权范围内的代码、修复安全问题和跟踪结果。导入自 [Codex Security SDK 0.10.0](https://github.com/openai/codex-security/releases/tag/npm-v0.10.0)，包内插件版本为 `0.1.95`。

漏洞发现和验证以源码证据、配置核对和合法行为的回归测试为依据。修复验证使用静态模式或普通回归测试。禁止生成、执行或分发漏洞利用代码与复现载荷，也禁止对目标执行入侵操作或自动化攻击。报告写受影响位置、影响、修复和证据缺口。

## 子 skill 路由

根据用户意图读取对应子 skill，沿用上面的防御性范围。路径相对本文件所在目录。

| 用户意图 | 子 skill |
|---|---|
| 整个仓库或某个目录/包的标准安全扫描（默认入口） | `skills/security-scan/SKILL.md` |
| PR / commit / 分支 diff / 工作区补丁的安全审查 | `skills/security-diff-scan/SKILL.md` |
| 深度、多轮、穷尽式全仓库或指定路径扫描 | `skills/deep-security-scan/SKILL.md` |
| 威胁建模 | `skills/threat-model/SKILL.md` |
| 候选漏洞发现 | `skills/finding-discovery/SKILL.md` |
| 漏洞验证 | `skills/validation/SKILL.md` |
| 攻击路径分析与严重度校准 | `skills/attack-path-analysis/SKILL.md` |
| 外部导入 findings（扫描器/advisory/工单）的分诊 | `skills/triage-finding/SKILL.md` |
| 修复并验证已确认的漏洞 | `skills/fix-finding/SKILL.md` |
| 只核对现有修复是否有效 | `skills/verify-fix/SKILL.md`（静态模式） |
| 评估现有补丁的回归风险 | `skills/assess-patch-risk/SKILL.md` |
| 排查依赖告警及可用升级 | `skills/resolve-dependency-alert/SKILL.md` |
| 定义 / 更新 SECURITY.md 安全策略 | `skills/define-security-policy/SKILL.md` |
| 基于证据的结构化安全加固建议 | `skills/propose-security-hardening/SKILL.md` |
| 漏洞报告撰写 | `skills/vulnerability-writeup/SKILL.md` |
| 将已验证 findings 跟踪到 Linear / Jira / GitHub | `skills/track-findings/SKILL.md` |

共享资源：`references/`、`scripts/`、`schemas/`、`shared/`、`examples/`。

## 路径与引用约定（重要）

- **`<plugin_dir>`**：子 skill 与共享 references 中出现的 `<plugin_dir>` 一律指**本 skill 根目录**（本 SKILL.md 所在目录），例如 `<plugin_dir>/scripts/finalize_scan_contract.py`。
- **`$skill-name` / `$codex-security:skill-name`**：子 skill 中的这类引用是 Codex 插件的 skill 调用语法。在本环境中改为读取 `skills/<skill-name>/SKILL.md` 并按其执行。
- **`$linear` / `$github` / `$atlassian`**：Codex 原生 app connector。当前环境没有这些 connector 时，GitHub 可经用户明确确认后改用已认证的 `gh` CLI；Linear / Jira 按子 skill 自身规则停止，不回退到未授权通道。

## 运行时说明

通过 x-mansion 插件安装时，Codex 从外层插件清单注册 Codex Security MCP。直接安装 skill 时，按包内 `.mcp.json` 配置 MCP，并从本 skill 的目录运行启动器。使用 Node.js 22.13+（22.x）或上游支持的 24.x、26.x。

标准、diff 和深度托管扫描使用 MCP 或 SDK 已提供的扫描上下文。缺少所需工具时，报告连接缺口，可继续进行对话内源码审查，并注明实际覆盖范围。托管扫描产物位置由 MCP 或 SDK 返回，保存约定见 `references/artifact-storage.md` 和 `references/scan-artifacts.md`。

## 来源与同步

发行包、校验和和更新策略见 `governance/sources/codex-security.json`。升级时保留本入口和验证、修复、报告中的本地防御性约束。
