---
name: server-ops-safe
disable-model-invocation: true
description: "安全登录 Linux 服务器做有限排障，确认后执行单一受控修复。"
metadata:
  category: engineering
  tags: [server, ops, troubleshooting]
  dependencies: []
---

# Server Ops Safe

用于需要登录服务器、查看状态、定位常见故障、并在严格边界内执行有限修复的场景。

## 适用范围

- 目标环境为 Linux + systemd + Docker。
- 登录方式优先使用 `~/.ssh/config` 中已有的 SSH host 别名。
- 默认任务是诊断和有限修复，不是通用运维代理。

## 输入约定

调用时按以下输入组织上下文：

- `ssh_target`：必填。优先使用 `~/.ssh/config` 中已配置的 SSH alias。
- `problem_summary`：必填。用户描述的故障现象。
- `service_name`：可选。目标 `systemd` 服务名。
- `container_name`：可选。目标 Docker 容器名。
- `health_check_command`：可选。用户明确给出的健康检查命令。

## 输出约定

输出必须包含以下结构：

1. `目标主机校验结果`
2. `诊断证据摘要`
3. `根因判断或待确认项`
4. `建议动作`
5. `若已修复则给出修复前后对比`

## 默认流程

1. 复述问题和目标主机，确认使用哪个 `ssh_target`。
2. 登录后先执行身份校验：
   - `hostname`
   - `whoami`
   - `date`
3. 执行只读诊断：
   - 系统负载、内存、磁盘
   - 目标服务状态
   - 最近日志
   - Docker 容器状态
   - 端口监听
   - 健康检查
4. 根据证据形成结论，不猜测性修复。
5. 若需要有限修复，必须先拿到用户明确确认。
6. 执行单一修复动作后立即复检，并输出修复前后差异。

## 推荐命令入口

- 只读诊断：`scripts/collect_diagnostics.sh <ssh_target> [service_name] [container_name]`
- 受控动作：`scripts/safe_service_action.sh <ssh_target> <service|container> <target_name> <status|logs|health-check|restart>`

## 安全规则

### 必须确认的动作

出现以下动作时，必须先明确确认：

```text
⚠️ 危险操作检测！
操作类型：[具体操作]
影响范围：[详细说明]
风险评估：[潜在后果]

请确认是否继续？[需要明确的"是"、"确认"、"继续"]
```

需要确认的动作包括：

- 使用 `sudo`
- 重启 `systemd` 服务
- 重启 Docker 容器
- 执行用户提供的写操作命令
- 扩大日志窗口到大范围历史日志
- 连接第二台服务器或通过跳板继续横向访问

### 明确禁止的动作

以下操作默认禁止，除非用户重新定义 skill 目标并单独授权：

- 修改 `~/.ssh/config`
- 编辑生产配置文件
- 安装、升级、卸载软件包
- 数据库写操作、结构变更、批量更新
- `rm`、批量删除、清理目录
- `reboot`、`shutdown`
- 批量 `kill` 进程
- 未指定目标的服务或容器重启
- 向外部系统发送敏感数据

## SSH 配置兼容说明

本 skill 兼容用户当前本地 SSH 配置现状，不自动加固或改写配置。已知存在以下宽松项，使用时必须显式意识到风险：

- `ForwardAgent yes`
- `PasswordAuthentication yes`
- `StrictHostKeyChecking no`

这些配置不是安全默认值。skill 只能兼容使用，不能把它们当作推荐配置。

## 诊断顺序

### 1. 主机与会话校验

- `ssh "<ssh_target>" "hostname && whoami && date"`

如果主机身份和预期不符，立即停止。

### 2. 基础资源检查

- `uptime`
- `free -h`
- `df -h`

### 3. 服务与容器状态

如果提供了 `service_name`：

- `systemctl status "<service_name>" --no-pager`

如果提供了 `container_name`：

- `docker ps -a --filter "name=<container_name>"`

### 4. 日志

如果提供了 `service_name`：

- `journalctl -u "<service_name>" -n 200 --no-pager`

如果提供了 `container_name`：

- `docker logs --tail 200 "<container_name>"`

### 5. 网络与健康检查

- `ss -ltnp`
- 仅当用户给出 `health_check_command` 时执行该命令

## 有限修复原则

- 一次只允许一个修复动作。
- 修复动作只能是单个服务重启或单个容器重启。
- 如果既没有 `service_name` 也没有 `container_name`，只能诊断，不能修复。
- 如果根因仍不明确，只能给出下一步建议，不能试探性操作。

## 结果表达要求

- 不要只贴原始命令输出，要提炼结论。
- 引用关键证据时说明命令来源。
- 对不确定结论必须标明"待确认"。
- 修复后必须说明服务状态、日志变化或健康检查变化。
