# Site Patterns

操作中积累的特定网站经验按域名存储在本目录下，文件名 `{domain}.md`。

确定目标网站后，主流程会读取对应文件获取先验知识（平台特征、有效模式、已知陷阱）。经验内容标注了发现日期，当作可能有效的提示而非保证 — 按经验操作失败时，回退通用模式并更新经验文件。

## 文件格式

```markdown
---
domain: example.com
aliases: [示例, Example]
updated: YYYY-MM-DD
---

## 平台特征
架构、反爬行为、登录需求、内容加载方式等事实

## 有效模式
已验证的 URL 模式、操作策略、选择器

## 已知陷阱
什么会失败以及为什么
```

## 计划积累的站点

随实际使用补充。常见候选：

- `flights.ctrip.com` — 携程机票，反爬严，需 CDP
- `flights.google.com` — Google Flights，部分国家/地区可用性受限
- `xiaohongshu.com` — 小红书，反爬极严，CDP + 登录态
- `mafengwo.cn` — 马蜂窝，普通 fetch 可达
- `cs.mfa.gov.cn` — 中国领事服务网，纯静态，curl 可达
- `cn.emb-japan.go.jp` — 日本驻华大使馆，纯静态
- `open-meteo.com` — 公共 API，无反爬

CDP 操作成功完成后，如果发现新模式（URL 结构、选择器、风控特征），主动写入对应文件。**只写经过验证的事实，不写猜测**。
