# web-access（x-mansion 适配）

当前采纳 [上游 v2.6.0 源码](https://github.com/eze-is/web-access/tree/d173a75978ceb2c63fa0b27f7408cd2bf7fe4310)，继续跟踪 `main`。本地入口是 [SKILL.md](SKILL.md)；[UPSTREAM.md](UPSTREAM.md) 是固定提交的原文对照，供升级时核对。

## 安装与调用

在母仓运行 `./xman install <platform> --skill web-access`。从本次实际加载的 skill 目录解析脚本，示例变量 `WEB_ACCESS_DIR` 由调用者设为该目录的绝对路径。

先按任务选择宿主工具、连接器、API 或浏览器。搜索与静态读取不检查 CDP；宿主浏览器能完成目标时直接使用。只有选择本 skill 的 CDP Proxy 分支才需要 Node.js 22+，并运行：

```bash
node "${WEB_ACCESS_DIR:?先设置实际加载的 web-access 目录}/scripts/check-deps.mjs"
```

浏览器由用户数据目录识别，配置与站点经验位于 `~/.web-access/`。首次检查会复用健康的共享服务；确需新选择时才探测浏览器并沿用用户选择。升级、用户数据迁移和旧实例维护先读 [v2.6 迁移说明](references/migration-2.6.md)，API 细节见 [CDP 参考](references/cdp-api.md)。源码更新本身不迁移用户数据或重启浏览器。

## 本地适配

- `SKILL.md` 保留工具选择、实际加载路径解析与用户授权边界；没有把“继续操作”视为用户接受风险。
- `scripts/xman-*.mjs` 是本仓验证探针，不参与上游覆盖。`arm`、`wait-settle`、`console`、`network` 用于页面稳定、控制台和网络失败观测；页面导航后需重新安装记录器。恢复建议遵守新版共享服务维护规则。
- 上游运行脚本、参考与配置模板按来源清单同步；旧配置与站点经验由上游迁移模块复制，目标已有文件保留。

## 离线验证

```bash
node --test "${WEB_ACCESS_DIR:?先设置实际加载的 web-access 目录}"/scripts/*.test.mjs
```

测试使用临时 HOME、脚本副本、假 HTTP/WebSocket 服务，覆盖用户数据迁移、浏览器发现、共享连接、维护与 iframe 操作，不访问真实浏览器。母仓另有 `tests/test_verify_probe.py` 覆盖本地探针。
