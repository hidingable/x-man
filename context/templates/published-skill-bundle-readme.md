# x-mansion Skill Bundle

这是从 x-mansion 母仓发布的独立 Skill 子集，只包含选中的 `skills/`、裁剪后的治理清单、团队/职能软链视图和平台同步脚本。

本发布物不包含 `xman`、Agent、Context、Task、Spec 或完整 Workflow Runtime；不要使用母仓的 `xman ...` 命令。

## 安装

直接运行发布物中的平台同步脚本：

```bash
./scripts/sync-claude.sh
./scripts/sync-codex.sh
./scripts/sync-cursor.sh
```

安装指定 Skill：

```bash
./scripts/sync-claude.sh --skill <skill-name>
./scripts/sync-codex.sh --skill <skill-name>
```

`skills/` 是发布物中的内容事实源，`team/skills/` 和 `plugins/*/` 是软链视图，不要直接编辑软链目标。
