---
name: server-deploy
disable-model-invocation: true
description: "把项目部署到远程服务器：环境探测、服务部署、域名配置和部署脚本。"
metadata:
  category: engineering
  tags: [deploy, server, infrastructure]
  dependencies: []
---

# Server Deploy

将项目部署到远程 Linux 服务器的标准化流程。覆盖从环境探测到域名上线的全链路。

## 适用场景

- 首次部署一个新项目到服务器
- 为已部署的项目添加/修改域名
- 生成本地一键部署脚本
- 查看服务器现有部署布局以规划新服务

## 输入约定

- `ssh_target`：必填。`~/.ssh/config` 中已配置的 SSH alias。
- `project_name`：必填。项目名称，用于目录和服务命名。
- `repo_url`：必填。Git 仓库地址。
- `domain`：可选。目标域名，例如 `app.example.com`。
- `port`：可选。服务端口，未指定时自动分配。
- `service_type`：可选。`systemd`（默认）| `docker` | `pm2`。

## 输出约定

最终输出必须包含：

1. 服务器现状摘要（已有项目、端口、资源）
2. 部署方案（位置、端口、服务类型、域名）
3. 部署结果验证（服务状态、HTTP 响应码、域名可达性）
4. 日常运维命令速查表

---

## 阶段 1：环境探测

### 目标

摸清服务器现有部署布局，为新项目选择不冲突的位置和端口。

### 必须收集的信息

```bash
# 1. 项目目录（确定部署位置约定）
ssh <target> "ls -la /opt/projects/"

# 2. 已运行的服务和端口
ssh <target> "ss -tlnp | grep LISTEN"

# 3. Docker 容器
ssh <target> "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# 4. systemd 自定义服务
ssh <target> "ls /etc/systemd/system/*.service 2>/dev/null | grep -v dbus | grep -v syslog"

# 5. PM2 进程（如有）
ssh <target> "pm2 list 2>/dev/null"

# 6. 系统资源
ssh <target> "free -h | head -3; echo '---'; nproc; echo '---'; df -h / | tail -1"

# 7. 语言运行时
ssh <target> "python3 --version 2>/dev/null; node --version 2>/dev/null; go version 2>/dev/null"

# 8. cloudflared 隧道配置（域名路由）
ssh <target> "cat /etc/cloudflared/config.yml 2>/dev/null"

# 9. Git SSH 访问
ssh <target> "ssh -T git@github.com 2>&1 | head -3"
```

### 输出格式

```markdown
### 服务器现状

| 项目 | 位置 | 方式 | 端口 |
|------|------|------|------|
| xxx  | /opt/projects/xxx | Docker | 3000 |
| ...  | ...               | ...    | ...  |

**已用端口**: 3000, 3001, 8000, 8001, ...
**可用资源**: CPU x核, 内存 xGB(可用 xGB), 磁盘 xGB 剩余
**域名映射**:
- domain.example.com → localhost:3001
- ...

### 部署方案
| 项 | 值 |
|----|-----|
| 位置 | /opt/projects/<project_name> |
| 端口 | <自动选择未占用端口> |
| 方式 | systemd / docker / pm2 |
| 域名 | <domain> |
```

### 端口选择规则

1. 扫描 `ss -tlnp` 已占用端口
2. 从 8002 开始递增，找到第一个未占用端口
3. 向用户确认

### 服务类型选择规则

| 条件 | 推荐 |
|------|------|
| 内存 < 4GB | systemd（最轻量）|
| 项目有 Dockerfile / docker-compose | Docker |
| Node.js 项目，已有 PM2 | PM2 |
| Python 项目，无 Docker 配置 | systemd + venv |

---

## 阶段 2：部署执行

### 2.1 通用步骤

```bash
# 克隆代码
ssh <target> "cd /opt/projects && git clone <repo_url> <project_name>"
```

### 2.2 Python 项目（systemd）

```bash
ssh <target> "
  cd /opt/projects/<project_name>

  # 虚拟环境
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -e '.[data]'  # 或 pip install -r requirements.txt

  # 数据目录
  mkdir -p data

  # 环境变量
  cat > .env << 'EOF'
HOST=127.0.0.1
PORT=<port>
EOF
"
```

**systemd 服务文件模板**（`/etc/systemd/system/<project_name>.service`）：

```ini
[Unit]
Description=<项目描述>
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/projects/<project_name>
EnvironmentFile=/opt/projects/<project_name>/.env
ExecStart=/opt/projects/<project_name>/.venv/bin/uvicorn <module>:app --host 127.0.0.1 --port <port> --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# 安装并启动
ssh <target> "
  sudo cp deploy/<project_name>.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable <project_name>
  sudo systemctl start <project_name>
"
```

### 2.3 Node.js 项目（PM2）

```bash
ssh <target> "
  cd /opt/projects/<project_name>
  npm install  # 或 pnpm install
  pm2 start ecosystem.config.js
  pm2 save
"
```

### 2.4 Docker 项目

```bash
ssh <target> "
  cd /opt/projects/<project_name>
  docker compose up -d --build
"
```

---

## 阶段 3：域名配置（cloudflared）

### 前提

服务器已安装 cloudflared 并配置隧道。配置文件通常在 `/etc/cloudflared/config.yml`。

### 步骤

```bash
# 1. 读取当前配置
ssh <target> "cat /etc/cloudflared/config.yml"

# 2. 在 ingress 中添加新条目（在默认 404 规则之前）
# 注意：必须完整写入文件，不能只追加。先读取 → 插入新条目 → 写回。

# 3. 添加 DNS CNAME 记录
ssh <target> "cloudflared tunnel route dns <tunnel_name> <domain>"

# 4. 重启 cloudflared
ssh <target> "sudo systemctl restart cloudflared"

# 5. 验证
curl -s -o /dev/null -w '%{http_code}' https://<domain>/
```

### cloudflared ingress 条目模板

```yaml
  # <项目描述>
  - hostname: <domain>
    service: http://localhost:<port>
```

### 重要规则

- `ingress` 最后一条必须是 `- service: http_status:404`（默认兜底）
- 新条目插入到兜底规则之前
- 写入配置时必须保留所有已有条目，不能丢失
- 写入后先验证 cloudflared 能正常启动，再确认完成

### 可用域名查看

从 cloudflared 配置中提取已使用的域名，推断可用的域名后缀：

```bash
# 提取所有已用域名
ssh <target> "grep 'hostname:' /etc/cloudflared/config.yml | awk '{print \$2}'"
```

向用户展示已用域名表，建议新域名方案（同后缀子域名）。

---

## 阶段 4：生成本地部署脚本

在项目根目录生成 `deploy-server.sh`，包含以下子命令：

| 子命令 | 功能 |
|--------|------|
| `update`（默认）| git push + 服务器 git pull + 重启服务 |
| `init` | 首次部署全流程 |
| `status` | 查看服务状态 |
| `logs` | 实时查看日志 |
| `restart` | 重启服务 |

### 脚本模板要点

```bash
#!/bin/bash
set -e

REMOTE="<ssh_target>"
PROJECT_DIR="/opt/projects/<project_name>"
SERVICE="<project_name>"
REPO_URL="<repo_url>"

case "${1:-update}" in
  init)    # git clone + venv + deps + systemd + start ;;
  update)  # git push + ssh pull + restart ;;
  status)  # ssh systemctl status ;;
  logs)    # ssh journalctl -f ;;
  restart) # ssh systemctl restart ;;
esac
```

### 脚本位置

- 与 `start.sh` 同级（项目根目录）
- 文件名：`deploy-server.sh`
- 权限：`chmod +x`

---

## 阶段 5：验证

### 必须验证的项

```bash
# 1. 服务是否运行
ssh <target> "sudo systemctl status <project_name> --no-pager | head -8"

# 2. 端口是否监听
ssh <target> "ss -tlnp | grep <port>"

# 3. HTTP 是否可达（本地）
ssh <target> "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<port>/"

# 4. 域名是否可达（外网，如果配了域名）
curl -s -o /dev/null -w '%{http_code}' https://<domain>/
```

### 输出格式

```markdown
### 部署结果

| 项 | 状态 |
|----|------|
| 代码克隆 | /opt/projects/<name> |
| 依赖安装 | 成功 |
| 服务状态 | active (running) |
| 端口监听 | <port> |
| 本地 HTTP | 200 |
| 域名访问 | https://<domain>/ 200 |
```

---

## 安全规则

### 必须确认的操作

- 写入 cloudflared 配置（影响所有域名路由）
- 重启 cloudflared（影响所有域名）
- 安装系统包（如 `apt install python3-venv`）
- 创建 systemd 服务

### 禁止操作

- 不修改已有项目的配置文件
- 不删除已有 cloudflared ingress 条目
- 不修改其他服务的端口或配置
- 不在服务器上直接编辑项目代码（只能 git pull）

---

## 日常运维速查

部署完成后，向用户输出以下速查表：

```markdown
### 日常命令

| 操作 | 命令 |
|------|------|
| 部署更新 | `./deploy-server.sh` |
| 查看状态 | `./deploy-server.sh status` |
| 查看日志 | `./deploy-server.sh logs` |
| 重启服务 | `./deploy-server.sh restart` |
| 手动更新 | `ssh <target> "cd <dir> && git pull && sudo systemctl restart <svc>"` |
```
