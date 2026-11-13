# Data Sources

travel-planner 的所有数据源清单。**强一手优先，二手仅作避坑参考**。

## 网络环境分级

按 `network` 探测结果决定走哪套源（详见 SKILL.md「网络环境探测与降级」）：

- **global**：海外+国内源都用，海外官方为主
- **cn-only**：国内可达的替代源，海外官方降级为不可用
- **global-only**：海外为主（罕见，海外用户）
- **offline**：停止流程

下表中带「🌐」表示需海外网络，带「🇨🇳」表示国内可达，无标记表示两边都行（CDN/全球）。

## 签证 / 入境

| 数据源 | URL | 用途 |
|------|-----|------|
| 🇨🇳 中国领事服务网 | https://cs.mfa.gov.cn/ | 出境签证政策、安全提醒（中国普通护照基线） |
| 🇨🇳 中国领事服务网 - 国家页 | https://cs.mfa.gov.cn/zggmcg/ldgj/ | 各国对华签证政策汇总 |
| 🇨🇳 国家移民管理局 | https://www.nia.gov.cn/ | 国内出入境政策（外籍来华、口岸通行） |
| 🇨🇳 中国驻外使领馆名录 | http://cs.mfa.gov.cn/zggmzhw/zgzwsljg/ | 紧急联系电话 |
| 🇨🇳 携程签证频道 | https://huodong.ctrip.com/visa/ | **cn-only 降级用**：政策摘要 + 办理服务，发布日期可能滞后 |
| 🇨🇳 飞猪签证 | https://lvyou.fliggy.com/visa/ | **cn-only 降级用**：同上 |

各国驻华大使馆 / 领事馆官网（按需检索，常用列举）：

| 国家 | 大使馆官网 | 备注 |
|------|----------|------|
| 日本 | https://www.cn.emb-japan.go.jp/ | 多次签证 / 单次签证 / 三年五年签 |
| 美国 | https://china.usembassy-china.org.cn/zh/ | B1/B2 旅游签 |
| 申根国（任一） | https://www.schengenvisainfo.com/ | 二手聚合，主要用于交叉验证；具体国家以该国大使馆为准 |
| 韩国 | https://overseas.mofa.go.kr/cn-zh/index.do | C-3 短期访问 |
| 泰国 | https://www.thaiembbeij.org/ | 落地签 / 电子签 |
| 英国 | https://www.gov.uk/standard-visitor-visa | 标准访客签证 |
| 澳大利亚 | https://immi.homeaffairs.gov.au/ | 600 类访客签证 |
| 新加坡 | https://www.ica.gov.sg/ | 电子签 e-Visa |
| 马来西亚 | https://www.imi.gov.my/ | 电子签 |
| 越南 | https://evisa.xuatnhapcanh.gov.vn/ | 官方电子签 |
| 阿联酋 | https://smartservices.icp.gov.ae/ | 旅游签 / 过境签 |
| 俄罗斯 | https://www.visa.kdmid.ru/ | 电子签 |

签证政策**变化非常快**，每条结论必须看清来源页面的发布日期。超过 6 个月的政策默认标“可能过期”。

## 天气

| 数据源 | URL | 备注 |
|------|-----|------|
| Open-Meteo Forecast API | https://api.open-meteo.com/v1/forecast | 公共 API，无 key，全球覆盖，16 天预报，国内一般可达 |
| Open-Meteo Geocoding | https://geocoding-api.open-meteo.com/v1/search | 地名 → 经纬度 |
| Open-Meteo Climate API | https://climate-api.open-meteo.com/v1/climate | 历史同期 / 气候参考（超出 16 天用） |
| 🇨🇳 中国气象局 | https://www.cma.gov.cn/ | 国内权威 |
| 🇨🇳 中央气象台 | http://www.nmc.cn/ | 国内灾害天气预警 |
| 🌐 日本気象庁 JMA | https://www.jma.go.jp/ | 日本台风、樱花、红叶 |
| 🌐 Met Office (UK) | https://www.metoffice.gov.uk/ | 英国及部分欧洲 |
| 🌐 NOAA / National Weather Service | https://www.weather.gov/ | 美国 |

**Open-Meteo 调用示例**：

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=35.68&longitude=139.69&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode&timezone=auto&start_date=2026-07-15&end_date=2026-07-22"
```

返回 JSON 直接解析，不需要 web-access。

## 治安 / 安全提醒

| 数据源 | URL | 备注 |
|------|-----|------|
| 中国领事服务网 - 安全提醒 | https://cs.mfa.gov.cn/gyls/lsgz/lsbb/ | 中文用户基线 |
| US State Dept Travel Advisories | https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html | 全球四级评级 |
| UK FCDO Foreign Travel Advice | https://www.gov.uk/foreign-travel-advice | 英国版本，措辞细 |
| Smartraveller (AU) | https://www.smartraveller.gov.au/ | 澳大利亚版本 |

## 货币 / 汇率

| 数据源 | URL | 备注 |
|------|-----|------|
| 中国银行外汇牌价 | https://www.boc.cn/sourcedb/whpj/ | 国内官方汇率（可作为人民币换算基准） |
| XE | https://www.xe.com/currencyconverter/ | 国际通用，实时汇率 |
| Open Exchange Rates | https://openexchangerates.org/ | API 形式，需 free key |

支付习惯（现金 vs 卡 vs 移动支付）需结合具体目的地，没有统一权威源；可参考各国央行 / 旅游局发布的“游客指南”。

## 插头 / 电压

| 数据源 | URL | 备注 |
|------|-----|------|
| World Standards | https://www.worldstandards.eu/electricity/plugs-and-sockets/ | 全球插头标准对照表 |
| IEC | https://www.iec.ch/world-plugs | 国际电工委员会官方版本 |

中国常见插头：A/C/I 三脚扁；电压 220V / 50Hz。

## SIM / 网络

| 数据源 | URL | 备注 |
|------|-----|------|
| 各国主要运营商官网 | — | 现地 SIM 套餐 |
| Airalo | https://www.airalo.com/ | 全球 eSIM，价格透明 |
| Holafly | https://esim.holafly.com/ | 不限量 eSIM |
| 中国移动境外漫游 | https://www.10086.cn/aboutus/news/zaixianyingye/ | 国内三大运营商对照 |

## 机票

| 数据源 | URL | 备注 |
|------|-----|------|
| 🌐 Google Flights | https://www.google.com/travel/flights | 全球航线综合，反爬中等，**cn-only 不可达** |
| 🌐 Skyscanner | https://www.skyscanner.com/ | 全球航线对比，**cn-only 不可达** |
| 🇨🇳 携程国际机票 | https://flights.ctrip.com/international/ | 中文用户主流，反爬严，建议 CDP，**cn-only 主力** |
| 🇨🇳 携程国内机票 | https://flights.ctrip.com/online/ | 国内 |
| 🇨🇳 去哪儿 | https://flight.qunar.com/ | 价格对比 |
| 🇨🇳 飞猪 | https://www.fliggy.com/ | 价格对比 |
| 各航司官网 | — | 退改签政策、行李额度以官网为准 |

**降级注意（cn-only 模式下）**：

- 国内 OTA 国际机票价格通常比 Google Flights / Skyscanner 高 **5-15%**，原因是国内 OTA 有服务费、汇率换算损耗、独家代理加价
- 部分**小众航司、超低成本航司**（如 Wizz Air、Ryanair、AirAsia 部分航线）在国内 OTA 不一定上架
- 部分**联程/换乘组合**国内 OTA 不支持，只能各段单买
- 必须在结果顶部标注降级提示，让用户知道这些差异

## 景点 / 票务

景点信息没有统一聚合源，**优先景点官网或目的地国官方旅游局**：

| 类型 | 推荐来源 |
|------|---------|
| 景点开放时间 / 票价 | 景点官网 / 官方公众号 / 官方小程序 |
| 国家级景区 | 各国旅游局官网（如 JNTO、KTO、TAT、Tourism Australia） |
| 票务（预约制） | 景点官方预约系统（如东京迪士尼、卢浮宫、长城慕田峪） |
| 国内景区 | 美团 / 大众点评 / 携程门票（可作为价格参考，最终以景区官方为准） |

## 真实体验补充（强制标二手）

以下来源用于挖掘”避坑/小众点/真实体验”，**不进事实层**，HTML/MD 中必须用 ⚠️ 标注为”二手参考”：

| 平台 | URL | 适用 |
|------|-----|------|
| 🇨🇳 小红书 | https://www.xiaohongshu.com/ | 中文目的地、亲子游、网红打卡（反爬严，CDP）。**搜索链接模式**：`https://www.xiaohongshu.com/search_result?keyword={景点名}` |
| 🇨🇳 大众点评 | https://www.dianping.com/ | 国内餐厅、景点、按摩 SPA 等评分。**搜索模式**：`https://www.dianping.com/search/keyword/{cityId}/0_{keyword}` |
| 🇨🇳 马蜂窝 | https://www.mafengwo.cn/ | 中文深度攻略 |
| 🇨🇳 知乎 | https://www.zhihu.com/ | 中文长文经验贴 |
| 🌐 Reddit r/travel | https://www.reddit.com/r/travel/ | 英文综合 |
| 🌐 Reddit 子版（按目的地） | r/JapanTravel / r/europetravel / 等 | 目的地针对性 |
| 🌐 TripAdvisor | https://www.tripadvisor.com/ | 全球景点评价（评分有水分，注意） |
| 🌐 Google Maps Reviews | https://www.google.com/maps/search/{景点名}+reviews | 海外景点最新评价。**搜索模式**：URL 直接搜 |
| 🌐 Lonely Planet | https://www.lonelyplanet.com/ | 老牌攻略，结构化好 |
| 🌐 Tabelog（日本） | https://tabelog.com/ | 日本餐厅本地评分（含中文版） |
| 🌐 Yelp（北美） | https://www.yelp.com/ | 北美餐厅 |

## 紧急 / 医疗

| 数据源 | URL | 备注 |
|------|-----|------|
| 🇨🇳 中国领事服务网 - 紧急联系 | https://cs.mfa.gov.cn/wgrlh/lhqz/ | 中国驻外使领馆 24h 电话 |
| 🌐 IAMAT 全球医院列表 | https://www.iamat.org/ | 旅行医学协会，列出可信医院 |
| 🌐 Joint Commission International | https://www.jointcommissioninternational.org/ | JCI 认证医院（国际标准） |
| WHO 国际旅行卫生 | https://www.who.int/health-topics/travel-and-health | 疫苗、疾病、健康提醒 |
| 🇨🇳 中国疾控中心 - 出国指南 | https://www.chinacdc.cn/ | 流行病和疫苗建议 |

**常用药品**（根据目的地适配，HTML 速览卡里要给清单 + 用途）：

| 类别 | 常见药品（举例） | 适用场景 |
|-----|---------------|---------|
| 止泻 | 蒙脱石散、洛哌丁胺、口服补液盐 | 东南亚、南亚、墨西哥水土不服 |
| 退烧/止痛 | 对乙酰氨基酚（泰诺）、布洛芬 | 通用 |
| 防蚊 | DEET / 派卡瑞丁驱蚊液 | 东南亚、南美雨季 |
| 高反 | 红景天、乙酰唑胺（处方）、便携氧 | >2500m 海拔目的地 |
| 晕车 | 茶苯海明（晕海宁） | 山路、邮轮、长途车 |
| 胃酸 | 奥美拉唑、铝镁加 | 暴食重口刺激 |
| 烫伤/外伤 | 烫伤膏、创可贴、碘伏棉签 | 通用 |
| 感冒 | 感冒灵、连花清瘟、鼻通 | 温差大目的地 |
| 滑雪/冬季 | 冻疮膏、保湿霜 | 雪季 |

⚠️ **重点提醒**：处方药出境要带处方/英文说明（特别是含麻黄素、阿片类的国内 OTC 药在某些国家是违禁品，如新加坡对常见感冒药管制）。

**急救用语**（HTML 速览卡里给当地语言中英对照表）：
- 我需要医生 / I need a doctor
- 救护车 / Ambulance
- 我对 X 过敏 / I'm allergic to X
- 这里痛 / It hurts here
- 报警 / Call the police

## 信息时效性

每个字段都要标“查询时间”：

- 签证政策、机票价格 — 极短时效（小时级）
- 天气 — 短时效（天级）
- 景点开放、票价 — 中时效（季节级）
- 插头、紧急号码、货币 — 长时效（年级）

HTML/MD 末尾的风险声明覆盖所有字段。
