# 第三方来源与许可

x-mansion 自有内容使用 [MIT](LICENSE)。下表中的 skill 来自其他项目，按各自的许可证分发；许可证全文在对应 skill 目录里，同步规则在 [governance/sources/](governance/sources/)。

标「已修改」的条目在本仓做过中文化或适配，与上游内容不同。

| Skill | 上游 | 许可证 | 本仓改动 |
| --- | --- | --- | --- |
| claude-api | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 已修改：保留本地触发范围与授权适配 |
| docx | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 按上游同步 |
| pdf | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 按上游同步 |
| pptx | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 按上游同步 |
| xlsx | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 按上游同步 |
| mcp-builder | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 按上游同步 |
| skill-creator | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 按上游同步 |
| webapp-testing | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 按上游同步 |
| codex-security | [openai/codex-security](https://github.com/openai/codex-security) | Apache-2.0 | 已修改：取自发行包 0.10.0，加本地入口与防御性约束 |
| cloudflare-deploy | [openai/skills](https://github.com/openai/skills) | Apache-2.0 | 已修改：中文化 front-matter |
| openai-docs | [openai/skills](https://github.com/openai/skills) | Apache-2.0 | 已修改：中文化 front-matter |
| archify | [tt-a1i/archify](https://github.com/tt-a1i/archify) v3.2.0 | MIT | 已修改：SKILL.md 为中文适配层，上游入口保留为 UPSTREAM.md |
| hv-analysis | [KKKKhazix/khazix-skills](https://github.com/KKKKhazix/khazix-skills) | MIT | 已修改：输出改为 markdown，产物路径走本仓约定 |
| i-have-adhd | [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) | MIT | 已修改：全量中文化，上游原文在 references/ |
| ui-ux-pro-max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | MIT | 按上游同步 |
| web-access | [eze-is/web-access](https://github.com/eze-is/web-access) v2.6.0，作者 一泽Eze | MIT（上游在 SKILL.md front-matter 声明） | 已修改：保留宿主工具选择与本地探针，上游入口保留为 UPSTREAM.md |
| find-skills | [vercel-labs/skills](https://github.com/vercel-labs/skills) | MIT | 已修改：中文化 |
| vercel-react-best-practices | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | MIT（上游在 SKILL.md front-matter 声明） | 已修改：中文化 front-matter |

各 skill 目录里可能还带有它自己依赖的第三方声明，例如 `skills/archify/THIRD_PARTY_NOTICES.md` 和 `skills/ui-ux-pro-max/data/google-font-licenses.json`。

发现遗漏或标注有误，请提 issue。
