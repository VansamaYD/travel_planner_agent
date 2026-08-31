# 智能旅游规划平台 API、MCP 与智能体架构调研规格

> 文档状态：调研基线草案 v0.1
> 调研日期：2026-08-30
> 适用范围：国内优先、个人/家庭小规模自托管、Docker Compose、AMD64 NAS
> 关联文档：[软件需求规格说明书](./software-requirements-specification.md)、[国内数据源与 API 调研](./domestic-travel-agent-integration-research.md)、[自托管小型系统设计](./self-hosted-small-system-design.md)

## 1. 文档目的

本文档用于回答以下问题：

1. 系统需要哪些外部 API、开放平台、本地能力和 MCP 服务；
2. 每类平台能提供什么、不能可靠提供什么、首版是否应依赖；
3. 外部平台格式不一致时，内部接口如何归一化；
4. 模型 API 如何统一接入 DeepSeek、OpenAI-compatible 和其他模型；
5. MCP 服务如何注册、鉴权、授权、隔离、审计和降级；
6. 智能体如何进行计划、调研、求解、复核、确认和落库，而不是只让模型自由调用工具；
7. 前端如何持续接收规划进度、结构化状态和待确认动作；
8. 如何在空闲内存低于 512 MB、正常峰值不超过 2 GB 的约束下实现。

本文不是任何第三方平台的商务授权承诺。第三方接口的配额、价格、资质、可用字段和服务条款可能变化，正式开发前必须在开发者控制台进行账号级实测。

## 2. 调研结论摘要

### 2.1 推荐技术基线

| 层次 | 首版推荐 | 说明 |
|---|---|---|
| 业务 API | REST/JSON + OpenAPI 3.1.1 | 手机端、管理端和导出工具共用 |
| 实时进度 | HTTP SSE | 比 WebSocket 更易部署、恢复和反向代理 |
| 数据 Schema | JSON Schema 2020-12 + Pydantic | 业务对象、工具输入输出和模型结构化输出共源 |
| 错误格式 | RFC 9457 Problem Details | 不自创多套错误结构 |
| 智能体编排 | LangGraph 低层 StateGraph 候选基线 | 状态、检查点、中断恢复、人工确认和子图能力完整 |
| 类型与验证 | Pydantic v2 | 所有模型输出、工具参数和外部响应二次验证 |
| 模型连接 | 自有 `ModelProvider` 接口 | DeepSeek 首发，兼容 OpenAI Chat/Responses；保留原生适配器 |
| MCP | 官方 MCP Python SDK | 远程使用 Streamable HTTP，本地可信服务使用 stdio/in-process |
| 地图 | 高德 Web Service v5 + JS API | 主地图、POI、路线和移动端唤起 |
| 地图补充 | 百度 Place/Direction | 数据补充和影子校验，不直接混用坐标和 POI ID |
| 天气 | 和风天气优先，高德天气降级 | 小时级、日级、预警和空气质量需要和风能力 |
| OCR | 本地轻量 OCR Profile + 视觉模型复核 | 默认不常驻加载；用户确认后入账 |
| 网页资料 | 静态抓取优先，Playwright/Firecrawl 可选 | 浏览器按任务启动、并发 1、使用后退出 |
| 可观测性 | 本地结构化日志 + OpenTelemetry 语义 | 默认不上传含隐私的模型内容 |

### 2.2 最重要的架构约束

1. **模型不能直接写业务表。** 模型只能生成 `TripPatchProposal`，经过 Schema、权限、版本和业务规则校验后才能确认提交。
2. **外部结果不是事实本身。** 路线、价格、评价和天气均保存来源、采集时间、置信度、适用人数和过期时间。
3. **MCP 不是绕过内部接口的快捷方式。** MCP 工具也必须转换为内部标准对象并经过同样的授权、审计和校验。
4. **规划是工作流，不是一次聊天。** 需求结构化、证据收集、候选生成、路线求解、预算、冲突检测、复核和确认是不同节点。
5. **聊天记录不是当前行程状态。** 每次模型运行只注入当前数据库快照、有效约束和必要摘要。
6. **价格必须标注类型。** 至少区分官方/实时、平台展示、历史估算、攻略引用和用户输入。
7. **高风险与有副作用动作必须确认。** 首版不下单、不支付；写行程、导入订单、覆盖用户修改、调用外部写操作均需要策略控制。

## 3. 调研依据与标准

### 3.1 接口标准

- HTTP API 使用 [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)。
- JSON Schema 使用 [Draft 2020-12](https://json-schema.org/draft/2020-12)。
- HTTP 错误使用 [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html)，媒体类型为 `application/problem+json`。
- 异步消息如果未来独立出消息总线，再使用 [AsyncAPI](https://www.asyncapi.com/docs)；首版不为此引入消息中间件。
- 日期时间使用 RFC 3339/ISO 8601 字符串，并同时保存 IANA 时区名。
- 币种使用 ISO 4217 三字母代码；人民币内部金额优先使用整数分，避免浮点误差。
- 日历导出使用 iCalendar（RFC 5545）文件，不依赖 Apple 私有 API。

### 3.2 MCP 标准

[MCP 2026-07-28 规范](https://modelcontextprotocol.io/specification/2026-07-28)定义了 Tools、Resources、Prompts，以及客户端能力和可选扩展。当前协议使用无会话、自包含请求和每请求能力协商；标准传输包括 stdio 和 Streamable HTTP。参考[当前 Transport 规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)。旧协议仍需通过 SDK 协商兼容，但旧 HTTP+SSE 传输不用于新接入。

MCP Python SDK 正在持续演进。官方仓库已经同时维护 1.x 和 2.x，2.x 面向更新的协议修订并支持向旧版本协商；实现时必须锁定依赖版本并运行协议兼容测试，不能仅写 `mcp>=...`。参考：[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)、[版本策略](https://github.com/modelcontextprotocol/python-sdk/blob/main/VERSIONING.md)。

### 3.3 智能体框架参考

| 框架 | 借鉴点 | 对本项目的判断 |
|---|---|---|
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) | Durable execution、检查点、状态图、人工中断、恢复、子图、时间回溯 | 最适合行程这种长生命周期可编辑工作流；建议 PoC 后作为编排基线 |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/agents/) | Manager-as-tools、handoff、输入/输出/工具 Guardrails、会话和 Trace | 设计模式优秀；首版不直接绑定，避免以 OpenAI Responses/Trace 为中心 |
| [Pydantic AI](https://pydantic.dev/docs/ai/overview/) | 类型化工具、结构化输出、依赖注入、多模型、MCP、Evals | 与 FastAPI/Pydantic 技术栈高度匹配，可作为专业智能体实现候选 |
| [AutoGen](https://microsoft.github.io/autogen/stable/index.html) | 多智能体 Teams、事件驱动 Core、MCP Workbench | 更适合研究型多智能体协作；本项目不需要自由群聊式团队 |
| [Google ADK](https://google.github.io/adk-docs/) | Sequential/Parallel/Loop Workflow Agent、多语言和工具生态 | 模式可参考；首版不依赖 Google Cloud 运行时 |
| CrewAI 等高层框架 | Role/Task 快速原型 | 对状态一致性、精确恢复和业务事务控制不够直接，不作为基线 |

最终建议不是堆叠多个框架，而是：

```text
LangGraph（工作流与恢复）
  + Pydantic（状态与契约）
  + 自有 ModelProvider（模型可替换）
  + 官方 MCP SDK（外部插件）
  + 纯 Python 规则/预算/路线校验器（确定性计算）
```

Pydantic AI 是否进入首版运行依赖，由 PoC 比较后确认。若引入，仅用于图节点内的类型化专业智能体，不接管业务事务和行程版本。

## 4. 外部平台总清单

### 4.1 接入优先级定义

| 级别 | 定义 |
|---|---|
| P0 | MVP 必需，必须有可用实现和降级路径 |
| P1 | 首版推荐，可配置后启用 |
| P2 | 后续扩展或需要商务/资质合作 |
| R | 仅调研/参考，不应成为首版依赖 |

### 4.2 平台矩阵

| 领域 | 平台/能力 | 优先级 | 接入形式 | 首版定位 |
|---|---|---:|---|---|
| 地图 | 高德 Web Service v5 | P0 | HTTPS REST | POI、地理编码、路线、距离 |
| 地图展示 | 高德 JS API | P0 | 浏览器 SDK | 移动端地图与标记联动 |
| 地图智能体 | 高德 MCP | P1 | Streamable HTTP / Node stdio | 专属地图和补充工具，不替代 REST |
| 地图补充 | 百度 Web API | P1 | HTTPS REST | Place/Direction 补充与影子校验 |
| 天气 | 和风天气 | P1 | HTTPS REST/JWT | 小时/日预报、预警、空气质量 |
| 天气降级 | 高德天气 | P0 | HTTPS REST | 城市级实况和短期预报 |
| 模型 | DeepSeek 官方 API | P0 | OpenAI/Anthropic compatible | 默认主模型候选 |
| 模型 | 任意 OpenAI-compatible | P0 | Chat/Responses | 用户自定义模型入口 |
| 模型 | OpenAI/Anthropic/Gemini 原生 | P1 | 原生 API | 视觉、结构化输出或备用模型 |
| OCR | PaddleOCR 轻量模型 | P1 | 本地按需任务 | 中文截图/票据文字提取 |
| OCR | 百度 OCR | P1 | HTTPS REST | 票据/高精度识别降级 |
| 网页 | HTTP 静态读取 + 正文抽取 | P0 | HTTPS | 用户粘贴链接与公开页面 |
| 网页 | Playwright | P1 | 本地进程 | JS 页面、用户授权会话，可选 Profile |
| 网页 | Firecrawl | P1 | API/MCP/自托管 | 搜索、抓取、结构化提取可选 |
| 搜索 | 模型提供商内置 Web Search | P1 | 模型原生工具 | 有引用的网页检索，能力探测后启用 |
| 攻略 | 用户粘贴文本/链接/截图 | P0 | 上传/URL | 最稳定合规的主入口 |
| 攻略增强 | 自有小红书只读 Worker | P1/R | 内部 REST + 可选 MCP | 默认关闭、按需 Chromium、并发 1；详见[独立规格](./xiaohongshu-guide-search-tool-spec-and-feasibility.md) |
| 餐饮 | 高德/百度 POI | P0 | REST | 餐厅位置、类别、营业等基础信息 |
| 餐饮 | 美团生态开放平台 | P2 | 合作 OpenAPI/H5 | 需要合作申请，不作为 MVP 依赖 |
| 酒店/机票 | 携程开放/商旅平台 | P2 | 合作 OpenAPI | 合作导向，不作为公开价格保证 |
| 酒店/门票 | 飞猪开放平台 | P2 | 合作 OpenAPI | 预留 Provider，不作为 MVP 依赖 |
| 铁路 | 12306 用户查询/订单导入 | P0 | 链接/OCR/人工确认 | 不依赖非公开购票 API |
| 航班动态 | 航旅纵横/飞常准类合作能力 | P2 | 合作 API/链接 | 可选动态提醒，不作为计划生成前提 |
| 邮件 | 管理员 SMTP | P1 | SMTP | 提醒、导出、邀请 |
| 日历 | ICS 文件 | P1 | 文件/系统唤起 | Apple/Android/桌面日历通用导入 |
| 导航 | 高德/百度 URL Scheme/Universal Link | P0 | 点击跳转 | 移动端一键导航 |

## 5. 地图与路线 API 规格调研

### 5.1 高德地图

高德 [路径规划 2.0](https://lbs.amap.com/api/webservice/guide/api/newroute)提供驾车、公交、步行、骑行、电动车路线；驾车支持多方案、途经点、车牌限行和策略。高德 [MCP Server](https://lbs.amap.com/api/mcp-server/summary)目前覆盖地理编码、逆地理编码、天气、步行/骑行/驾车/公交规划、距离、关键词和周边搜索等，并能生成高德专属地图和唤端链接。

首版应直接调用 Web Service API，而不是仅调用 MCP，原因如下：

- REST 返回字段更稳定，便于缓存、回归测试和预算计算；
- 路线结果需要保留原始响应、字段映射版本和证据时间；
- MCP 工具清单可能变动，且模型调用路径不适合作为唯一数据入口；
- 专属地图、导航和打车唤起属于高德 MCP 的增值补充场景。

建议接入能力：

| 能力 | 内部操作 | 要点 |
|---|---|---|
| 地理编码 | `maps.geocode` | 保存候选、adcode、原始坐标系和置信度 |
| 逆地理编码 | `maps.reverse_geocode` | 地址仅作展示，不覆盖用户确认地址 |
| POI 关键词检索 | `places.search` | 城市、分类、中心点、半径和分页 |
| POI 周边检索 | `places.nearby` | 餐厅、景点、酒店候选 |
| POI 详情 | `places.get` | 使用 provider POI ID，不跨平台复用 |
| 驾车路线 | `routes.plan` | 距离、时长、收费、策略、限行提示 |
| 公交路线 | `routes.plan` | 步行段、公交/地铁段、换乘和票价提示 |
| 步行/骑行 | `routes.plan` | 体力和天气合理性输入 |
| 距离矩阵 | `routes.matrix` | 候选排序和日内路线优化 |
| 天气 | `weather.get_basic` | 作为和风不可用时的城市级降级 |
| 唤端 | `maps.deep_link` | 前端点击，不由模型自动打开 |
| 专属地图 | `maps.publish_personal_map` | 用户确认后调用，保留返回链接 |

路线返回的收费、公交票价和预计出租车价格只能记录为 `provider_estimate`，不能标记为最终成交价。

### 5.2 百度地图

百度地图 Web API 提供 [地点检索 3.0](https://lbsyun.baidu.com/docs/webapi?title=placev3%2Fguide%2Fwebservice-placeapiV3%2FinterfaceDocumentV3)、[路线规划](https://lbsyun.baidu.com/docs/webapi?title=directionv2%2Fdirection-api-v2)、坐标转换、天气、路况、AOI 等能力。首版定位为：

1. 用户明确要求使用百度数据时的可选 Provider；
2. 高德 POI 搜索无结果或歧义时的补充候选；
3. 关键路线的影子校验；
4. 百度地图移动端跳转。

禁止事项：

- 不把百度 POI UID 当作高德 POI ID；
- 不直接比较不同坐标系坐标；
- 不把两个平台的同名地点自动合并为一个地点；
- 不将影子校验结果静默覆盖用户已经确认的路线。

### 5.3 内部坐标规范

```json
{
  "latitude": 39.908722,
  "longitude": 116.397499,
  "crs": "WGS84",
  "provider": "user_gps",
  "provider_place_id": null,
  "accuracy_m": 15,
  "observed_at": "2026-08-30T10:00:00+08:00"
}
```

规范要求：

- 内部标准交换坐标使用 WGS84；
- Provider Adapter 负责 WGS84、GCJ-02、BD-09 转换；
- 同时保存原始坐标、原始坐标系和转换版本；
- 前端绘制时使用地图 SDK 要求的坐标系；
- 涉及中国境内地图展示与坐标处理时遵循地图平台服务条款和适用法规；
- 坐标精度不得虚构，地址解析结果需标记来源和候选序号。

### 5.4 路线统一输出

```json
{
  "route_id": "rte_...",
  "mode": "DRIVING",
  "origin": {"place_ref": "plc_..."},
  "destination": {"place_ref": "plc_..."},
  "distance_m": 18600,
  "duration_s": 2520,
  "segments": [],
  "costs": [
    {
      "category": "TOLL",
      "amount_minor": 1200,
      "currency": "CNY",
      "price_type": "PROVIDER_ESTIMATE"
    }
  ],
  "provider": "amap",
  "provider_route_id": null,
  "strategy": "TIME_FIRST",
  "fetched_at": "2026-08-30T10:00:00+08:00",
  "expires_at": "2026-08-30T10:30:00+08:00",
  "warnings": [],
  "raw_ref": "blob://provider-response/..."
}
```

## 6. 天气 API 规格调研

### 6.1 推荐来源

[和风天气](https://dev.qweather.com/en/docs/api/weather/)提供实时、小时、日级、分钟降水、预警、生活指数和空气质量等能力。日预报可按经纬度查询，[天气预警](https://dev.qweather.com/docs/api/warning/weather-alert/)具有生命周期、严重程度和有效时间字段。

高德天气只提供基于 adcode 的城市级实况/短期预报，适合作为轻量降级，参考[高德天气 API](https://lbs.amap.com/api/webservice/guide/api/weatherinfo)。

### 6.2 天气影响策略

天气智能体只能默认生成建议，不得因普通天气自动大幅改写攻略：

| 风险 | 默认动作 |
|---|---|
| 小雨、轻度降温 | 提示携带物品，给出室内备选，不自动替换 |
| 高温、空气质量不佳 | 调整提示、休息频率建议，等待用户选择 |
| 暴雨、台风、暴雪、官方高等级预警 | 明确风险，给出当天替代方案并请求确认 |
| 用户启用“天气优先自动调整” | 可生成 Patch，但仍展示差异和依据 |

### 6.3 天气统一输出

必须包含坐标、时区、预报区间、发布时间、采集时间和来源。预警不能只保存文本，必须保存 `issued/effective/onset/expires` 和状态变化关系。

## 7. 餐饮、酒店、门票和交通价格

### 7.1 可行性结论

公开、低门槛、同时覆盖实时库存与成交价格的国内综合旅行 API 并不存在。美团生态开放平台的公开接入流程包括申请合作、商务评估、开发测试和上线；[携程商旅开发者平台](https://openapi.ctripbiz.com/)同样以企业差旅集成为主。这些平台可以预留 Adapter，但不能作为个人自托管 MVP 的硬依赖。

### 7.2 首版价格来源优先级

1. 用户订单、票据、截图中确认的实际价格；
2. 用户粘贴的当前平台页面或套餐信息；
3. 可公开调用的地图/天气/交通 Provider 返回估价；
4. 官方景区、酒店、餐厅网页公开价格；
5. 多篇攻略中的近期价格区间；
6. 内置规则和历史估算。

### 7.3 价格观察对象

```json
{
  "observation_id": "pob_...",
  "subject_type": "RESTAURANT_MEAL",
  "subject_ref": "plc_...",
  "amount_min_minor": 12000,
  "amount_max_minor": 18000,
  "currency": "CNY",
  "unit": "PER_TABLE",
  "applies_to_people": 4,
  "price_type": "GUIDE_ESTIMATE",
  "source_ref": "evd_...",
  "observed_at": "2026-08-30T10:00:00+08:00",
  "valid_for_date": "2026-10-03",
  "confidence": 0.62,
  "notes": "节假日可能上浮"
}
```

`price_type` 枚举：

- `ACTUAL_PAID`
- `USER_CONFIRMED`
- `OFFICIAL_QUOTE`
- `PROVIDER_REALTIME`
- `PROVIDER_ESTIMATE`
- `GUIDE_ESTIMATE`
- `HISTORICAL_ESTIMATE`
- `RULE_ESTIMATE`
- `UNKNOWN`

### 7.4 计价单位

必须支持：`PER_PERSON`、`PER_ROOM_NIGHT`、`PER_VEHICLE`、`PER_TABLE`、`PER_TICKET`、`PER_SEGMENT`、`PER_DAY`、`FIXED_GROUP`。

任何价格在参与预算前都必须明确：人数、儿童/老人规则、房间数、入住夜数、车辆数、日期和是否含税/服务费。

## 8. 攻略、评价和网页资料接入

### 8.1 首版合规路径

1. 用户粘贴公开链接；
2. 用户粘贴文本；
3. 用户上传截图/PDF；
4. 系统读取无需登录的公开页面；
5. 用户主动启用浏览器 Profile 后，在其授权会话中读取可见内容；
6. 不绕过验证码、访问控制、反爬机制和平台限制。

小红书等无通用公开内容 API 的平台，P0 主链路保留“分享链接/截图/文本导入 + 点击回原文”的方式，不依赖非公开接口。用户授权浏览器查询仅作为默认关闭的 P1/R 增强能力，其边界和 Go/No-Go 门见[小红书旅游攻略查询工具规格与可行性研究](./xiaohongshu-guide-search-tool-spec-and-feasibility.md)。

### 8.2 网页工具选择

| 工具 | 用途 | 常驻内存策略 |
|---|---|---|
| HTTPX + 正文抽取 | 静态 HTML、官方网页、博客 | 主服务内使用 |
| Playwright | JS 页面、授权会话、截图 | crawler Profile，任务时启动，完成即退出 |
| [Firecrawl](https://docs.firecrawl.dev/introduction) | 搜索、抓取、crawl、结构化提取、MCP | 可用云 API；自托管版不进入最小默认 Compose |
| PaddleOCR | 截图和文档文字 | 单任务子进程，模型懒加载 |

Playwright 浏览器二进制本身占用数百 MB 磁盘且运行时会显著增加内存，因此只安装 Chromium/headless shell，并将浏览任务并发限制为 1。参考 [Playwright 浏览器说明](https://playwright.dev/python/docs/browsers)。

### 8.3 Evidence 统一对象

```json
{
  "evidence_id": "evd_...",
  "source_type": "WEB_PAGE",
  "source_url": "https://example.com/article",
  "canonical_url": "https://example.com/article",
  "title": "...",
  "publisher": "...",
  "published_at": null,
  "fetched_at": "2026-08-30T10:00:00+08:00",
  "content_hash": "sha256:...",
  "excerpt": "...",
  "claims": [],
  "access_method": "USER_PROVIDED_URL",
  "visibility": "PRIVATE_TRIP",
  "quality_score": 0.75,
  "stale_after": "2026-09-29T10:00:00+08:00"
}
```

系统生成的每项关键建议应能够指回一个或多个 Evidence；无法找到来源时必须标记为模型建议或规则估算。

## 9. OCR 与订单识别平台

### 9.1 推荐流程

```text
上传图片/PDF
  → 文件安全检查
  → 图片预处理
  → 本地轻量 OCR
  → 结构化字段抽取智能体
  → 规则校验（金额、日期、城市、订单号掩码）
  → 用户确认/修正
  → 写入订单或消费记录
```

[PaddleOCR PP-StructureV3](https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-StructureV3/PP-StructureV3.html)支持版面、表格、阅读顺序和 Markdown 转换，但完整流水线较重。首版应优先使用轻量 PP-OCR 文本识别；复杂文档解析作为可选 Profile。百度 OCR 可作为高精度或票据类云端降级，参考[百度 OCR 文档](https://ai.baidu.com/ai-doc/index/OCR)。

### 9.2 视觉模型复核

- OCR 首次结果低置信度时先请用户确认；
- 用户标记不准确后才发送给已配置的视觉模型；
- 视觉模型只输出候选字段，不直接记账；
- 原图、OCR 文本、模型候选、用户最终值和每次修改均保留审计关联；
- 订单号、手机号等敏感内容进入模型前按配置脱敏。

## 10. 模型 API 接入规范

### 10.1 DeepSeek

DeepSeek 官方 API 兼容 OpenAI/Anthropic 格式，OpenAI 格式基础地址为 `https://api.deepseek.com`。官方文档确认支持 Tool Calls，并要求应用自行执行工具；Thinking 模式和工具交互时对 `reasoning_content` 的回传有特定要求。参考：[首次调用](https://api-docs.deepseek.com/guides/function_calling)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

接入要求：

- 将 DeepSeek 视为独立 Provider，不假设所有 OpenAI 字段都完全等价；
- Provider 声明其支持 Chat Completions、Responses、结构化输出、工具、视觉、流式和推理参数的能力；
- Thinking + Tools 的中间 `reasoning_content` 只在当前运行所需范围内原样回传；
- 不把模型思维链保存为业务审计内容，只保存步骤摘要、工具调用、输入版本和结果；
- 所有工具参数仍须本地验证，官方 Responses 文档也提醒参数可能无效或包含未定义字段；
- 模型名称不可硬编码，通过配置和能力探测获得。

### 10.2 OpenAI-compatible 不是完整能力标准

系统不能只保存 `base_url + api_key + model`。每个模型配置需要以下能力描述：

```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com",
  "model": "configured-by-admin",
  "api_style": "OPENAI_CHAT",
  "capabilities": {
    "streaming": true,
    "tools": true,
    "parallel_tools": true,
    "json_object": true,
    "json_schema_strict": false,
    "vision": false,
    "reasoning": true,
    "native_web_search": false,
    "native_mcp": false
  },
  "limits": {
    "context_tokens": null,
    "max_output_tokens": null,
    "max_tools": 32
  }
}
```

管理员保存配置时运行小型能力探测：普通回复、流式、JSON、单工具、并行工具、长 Schema 和视觉。探测结果可人工覆盖，但必须记录覆盖原因。

### 10.3 内部 ModelProvider 接口

```python
class ModelProvider(Protocol):
    async def probe(self, config) -> ModelCapabilities: ...
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
    async def count_tokens(self, request: ModelRequest) -> TokenEstimate: ...
```

`ModelRequest` 必须包含：

- `run_id`、`trip_id`、`user_id`；
- `purpose`：规划、抽取、复核、记忆、视觉等；
- system instructions 版本；
- 当前业务快照引用；
- 消息和附件；
- 可用工具的内部定义；
- 输出 JSON Schema；
- token、时间、工具次数和费用预算；
- 数据处理策略和敏感字段标记。

`ModelResponse` 必须归一化：文本、结构化输出、工具调用、拒绝、使用量、模型标识、结束原因、Provider 请求 ID 和原始响应引用。

### 10.4 结构化输出策略

1. 优先使用 Provider 原生 strict JSON Schema；
2. 不支持 strict 时使用工具调用返回结构化对象；
3. 再降级为 JSON Object + Pydantic 验证；
4. 允许最多一次“仅修复格式”的廉价重试；
5. 仍失败则返回可解释错误，不猜测补齐关键金额、日期或地点。

Google Gemini 也明确区分 Structured Outputs 与 Function Calling，并仅支持 JSON Schema 子集，证明内部必须维护 Provider Schema 降级器，而不能把完整 2020-12 Schema 原样发给所有模型。参考 [Gemini Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output)。

## 11. 智能体总体设计

> 节点级输入输出、完整规划、局部修改、行中调整、质量门、上下文裁剪、恢复和评估的详细规格见：[旅游规划智能体详细流程规格](./agent-workflow-detailed-spec.md)。本节保留总体架构摘要。

### 11.1 设计原则

本系统采用“确定性外壳包围概率性智能体”：

```text
用户意图
  → 确定性权限/版本检查
  → 结构化需求智能体
  → 可持久化工作流图
  → 专业智能体与确定性求解器协作
  → 规则与证据复核
  → 结构化差异提案
  → 用户确认或策略自动通过
  → 事务落库
  → 前端卡片与解释更新
```

模型负责：理解、生成候选、综合证据、解释权衡、提出修改。

程序负责：权限、事务、金额运算、时间运算、坐标转换、Schema 校验、版本冲突、配额、审批和审计。

### 11.2 智能体角色

| 智能体 | 输入 | 输出 | 是否可写库 |
|---|---|---|---|
| Intake Agent | 用户对话、预设表单 | `TripRequirementsDraft`、待确认问题 | 否 |
| Research Planner | 需求、已有证据 | `ResearchPlan` | 否 |
| Evidence Synthesizer | 攻略、网页、POI、天气 | `EvidenceDigest`、冲突与置信度 | 否 |
| Itinerary Designer | 确认需求、候选地点 | 候选日程结构 | 否 |
| Route Specialist | 地点和时间窗 | 路线请求、路线比较与风险 | 否 |
| Venue Specialist | POI/攻略/偏好 | 景点、餐厅、酒店候选 | 否 |
| Budget Specialist | 价格观察、人数、规则 | 预算明细与区间 | 否 |
| Constraint Critic | 完整候选计划 | 冲突、缺口、修复建议 | 否 |
| Patch Planner | 用户修改请求、当前版本 | `TripPatchProposal` | 否 |
| Order Extractor | OCR/视觉结果 | `OrderDraft`/`ExpenseDraft` | 否 |
| Memory Curator | 评价、显式偏好 | `MemoryProposal` | 否 |
| Coordinator | 工作流状态 | 节点路由、汇总和用户说明 | 否 |

只有 Application Service 能调用事务仓储。它接受已经验证且获批的 Command，不接受自然语言 SQL 或任意 JSON。

### 11.3 新旅行规划工作流

```text
START
  → load_context
  → understand_request
  → resolve_hard_constraints
  → [需要确认?] ─yes→ await_user_confirmation
  → build_research_plan
  → gather_places ┐
  → gather_guides ├─ bounded parallel
  → gather_weather┘
  → normalize_and_deduplicate
  → generate_candidate_skeletons
  → route_and_time_solve
  → budget_calculate
  → constraint_audit
  → evidence_critic
  → [不合格且可修复?] ─yes→ revise_candidate（最多 2 轮）
  → compare_options
  → produce_trip_patch
  → await_user_approval
  → commit_transaction
  → summarize_and_render
END
```

### 11.4 局部修改工作流

1. 读取当前 `trip_version`；
2. 从对话解析修改范围和不可变区域；
3. 默认锁定已完成、已支付、用户手工锁定的项目；
4. 计算受影响图：行程项、前后路线、餐饮时间、预算、提醒；
5. 只对受影响子图重新规划；
6. 运行全局一致性检查；
7. 输出 before/after/diff、预算差异和依据；
8. 用户确认后以 optimistic lock 提交；
9. 如果版本已变化，重新基于新版本生成提案，禁止静默覆盖。

### 11.5 行中调整工作流

- 优先调整当天未完成项目；
- 已完成和已记账项目不可由模型修改；
- 先给最小改动方案，再给备选方案；
- 天气和延误只作为建议触发，除非用户开启自动调整策略；
- 所有提醒和路线链接基于提交后的行程版本生成。

### 11.6 计划—执行—复核模式

每个复杂节点使用以下循环，但有明确预算：

```text
Plan：列出需要的数据和工具，不产生最终事实
Act：执行白名单工具，最多 N 次
Observe：标准化结果，记录来源和过期时间
Reflect：检查缺口、冲突和是否需要另一来源
Decide：产出结构化节点结果或请求用户输入
```

限制：

- 单节点最多 6 次外部工具调用；
- 单次完整规划默认最多 24 次外部调用；
- Critic 修订最多 2 轮；
- 同一 Provider 相同参数由缓存去重；
- 达到预算后输出“数据不足”的降级结果，不能无限自主循环。

## 12. 智能体状态规范

### 12.1 `PlanningState`

```json
{
  "run_id": "run_...",
  "workflow_version": "trip-plan@1.0.0",
  "trip_id": "trp_...",
  "base_trip_version": 12,
  "actor": {"user_id": "usr_...", "role": "MEMBER"},
  "requirements": {},
  "hard_constraints": [],
  "soft_preferences": [],
  "locked_entities": [],
  "research_plan": {},
  "evidence_refs": [],
  "place_candidates": [],
  "route_candidates": [],
  "price_observation_refs": [],
  "candidate_plans": [],
  "violations": [],
  "pending_approval": null,
  "budgets": {
    "model_tokens_remaining": 50000,
    "tool_calls_remaining": 24,
    "wall_time_s_remaining": 180
  },
  "status": "RUNNING",
  "last_completed_node": "gather_places"
}
```

### 12.2 状态持久化原则

- 每个节点输入输出必须 JSON 可序列化；
- 节点完成后保存检查点；
- 外部调用结果先写 Evidence/Observation，再引用 ID；
- 任何副作用节点必须幂等；
- 人工确认点可以跨进程重启恢复；
- 状态中不保存明文密钥、完整支付凭证或无必要的模型思维链；
- 工作流版本升级时提供状态迁移或继续使用旧版本完成。

LangGraph 的检查点可支持人工中断、恢复、记忆和故障恢复；其 `interrupt()` 恢复时会从节点开头重新执行，因此确认点之前的副作用必须幂等。参考 [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 和 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

## 13. 工具设计规范

### 13.1 工具不是业务 API 的直接镜像

模型看到的是稳定、少量、业务语义明确的工具；Provider 的几十个参数由 Adapter 隐藏。

推荐工具集：

| 工具名 | 类型 | 说明 |
|---|---|---|
| `trip.get_snapshot` | READ | 获取指定版本结构化快照 |
| `trip.propose_patch` | COMPUTE | 验证并生成差异，不提交 |
| `places.search` | READ | 跨 Provider 归一化地点候选 |
| `places.get_details` | READ | 详情和来源 |
| `routes.plan` | READ/COMPUTE | 多模式路线与成本提示 |
| `routes.compare` | COMPUTE | 纯程序路线比较 |
| `weather.get` | READ | 天气和预警 |
| `guides.search` | READ | 搜索公开攻略或资料库 |
| `guides.fetch` | READ | 读取用户授权 URL |
| `prices.observe` | READ | 获取/记录价格观察草稿 |
| `budget.calculate` | COMPUTE | 确定性多人预算引擎 |
| `constraints.audit` | COMPUTE | 时间、距离、体力、闭馆等检查 |
| `orders.extract` | COMPUTE | OCR 结果转订单草稿 |
| `memory.propose` | COMPUTE | 生成偏好记忆提案 |

模型默认不获得 `trip.commit_patch`、删除、发送邮件、发布公开分享等有副作用工具。这些动作由应用层根据确认结果调用。

### 13.2 工具 Schema 规则

- 名称使用小写命名空间和动词；
- 输入对象 `additionalProperties: false`；
- 每个字段写清单位、坐标系、时区和枚举；
- 关键参数不提供危险默认值；
- 输出具有 `status`、`data`、`warnings`、`provenance`；
- 输出体积超限时保存为资源并返回引用；
- 工具超时和业务无结果分开表达；
- 工具结果禁止夹带新的系统指令。

### 13.3 风险分级

| 等级 | 示例 | 策略 |
|---|---|---|
| R0 | 预算计算、约束检查 | 自动执行 |
| R1 | 地图、天气、公开网页读取 | 自动执行，受域名/配额限制 |
| R2 | 使用用户私有凭据读取订单/日历 | 首次或按会话确认 |
| R3 | 修改行程、导入消费、发送邮件、发布分享 | 展示差异并明确确认 |
| R4 | 下单、支付、删除备份、执行任意代码 | 首版禁止 |

## 14. MCP 接入规范

### 14.1 MCP 在系统中的位置

```text
MCP Server
  → MCP Client/Gateway
  → Trust & Policy Filter
  → Tool Schema Normalizer
  → Internal Tool Registry
  → Agent Workflow
  → Domain Validator
```

模型不直接持有 MCP 连接对象。MCP Gateway 管理生命周期、凭据、工具发现、超时、审计、Schema hash 和结果大小。

### 14.2 支持的传输

| 传输 | 首版 | 适用范围 |
|---|---|---|
| Streamable HTTP | 支持 | 远程高德、Firecrawl、用户明确配置的服务 |
| stdio | 支持但仅管理员 | 随系统安装的可信本地 MCP；禁止用户输入任意命令 |
| in-process | 支持 | 自有 MCP 服务和测试，减少网络开销 |
| 旧 HTTP+SSE | 兼容读取 | 仅迁移旧服务，不新增配置 |

### 14.3 MCP Server 配置

```json
{
  "id": "mcp_amap",
  "name": "Amap Maps",
  "enabled": true,
  "transport": "STREAMABLE_HTTP",
  "endpoint": "https://mcp.amap.com/mcp",
  "auth": {
    "type": "QUERY_SECRET",
    "secret_ref": "secret://mcp/amap/key",
    "parameter": "key"
  },
  "trust_level": "VERIFIED_VENDOR",
  "allowed_tools": ["maps_*", "search_*"],
  "blocked_tools": ["*order*", "*pay*"],
  "tool_prefix": "amap",
  "timeout_s": 20,
  "max_result_bytes": 262144,
  "approval_policy": "READ_AUTO_WRITE_CONFIRM",
  "egress_hosts": ["mcp.amap.com"]
}
```

如果第三方要求把 Key 放在 URL 查询参数中，系统仍应把 endpoint 和 secret 分离保存，运行时拼接，并在日志、错误和 UI 中进行脱敏。

### 14.4 工具发现与变更

首次连接和定期健康检查时：

1. 获取 server info、协议版本和 capabilities；
2. 获取工具列表；
3. 规范化并计算每个工具的 Schema hash；
4. 与上次版本比较；
5. 新工具默认禁用；
6. 输入 Schema 出现破坏性变化时暂停该工具；
7. 管理员确认后更新 allowlist；
8. 记录变更审计。

MCP 工具 annotations 必须视为不可信提示，不能据此自动授予权限；这一点由 MCP 规范明确要求，参考 [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)。

### 14.5 MCP 鉴权

- 远程 HTTP 无认证：仅允许公开只读服务；
- API Key：存入加密 Secret Store，按系统/家庭/用户作用域管理；
- OAuth：遵循 MCP HTTP 授权规范、PKCE、精确 redirect URI 和短期 token；
- stdio：通过受控环境变量注入密钥；
- 禁止把一个用户的 OAuth token 共享给家庭其他成员；
- 不支持的认证方式显示为“需要管理员适配”，不允许用户粘贴脚本绕过。

参考 [MCP Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)。OAuth access token 必须通过 Authorization Header 发送，不得放入查询参数；第三方自定义 API Key 查询参数不应被误当作 OAuth token。

### 14.6 MCP 安全边界

- Server、工具描述、资源和结果均可能包含 Prompt Injection；
- 外部文本标记为 `UNTRUSTED_CONTENT`，只作为数据，不拼接为系统指令；
- 工具返回的 URL 需执行 SSRF 检查；
- 默认禁止访问 NAS 内网、metadata 地址、localhost 和文件系统；
- 结果限制大小、MIME 类型和重定向次数；
- 工具超时后发送取消并熔断；
- 每个调用记录用户、运行、工具、Schema hash、输入摘要、结果摘要、延迟和状态；
- 不默认启用 MCP Sampling、Roots、Elicitation；如后续启用，需要独立权限开关；
- MCP Prompts 只能作为用户可选择模板，不能覆盖系统安全策略。

## 15. 内部 REST API 规范

### 15.1 基本约定

- Base path：`/api/v1`；
- Content-Type：`application/json; charset=utf-8`；
- 认证：同源 HttpOnly Session Cookie；程序化访问后续支持 Bearer token；
- 资源 ID：不可枚举随机 ID；
- 并发控制：`ETag`/`If-Match` 或显式 `base_version`；
- 幂等：创建任务、导入订单和提交 Patch 使用 `Idempotency-Key`；
- 分页：cursor-based；
- 时间：RFC 3339，必须含时区偏移；
- 语言：`Accept-Language`，首版只返回 `zh-CN`；
- Trace：响应返回 `X-Request-ID`，不暴露内部堆栈。

### 15.2 成功响应

成功响应直接返回资源对象，不额外包裹无意义的 `{code,data,message}`。列表使用：

```json
{
  "items": [],
  "next_cursor": null,
  "total_estimate": null
}
```

### 15.3 错误响应

```json
{
  "type": "https://travel-agent.local/problems/version-conflict",
  "title": "行程版本冲突",
  "status": 409,
  "detail": "该行程已在其他位置更新，请基于最新版本重新生成修改。",
  "instance": "/api/v1/trips/trp_123/patches/pat_456",
  "request_id": "req_...",
  "current_version": 13,
  "submitted_base_version": 12
}
```

### 15.4 关键端点草案

```text
POST   /api/v1/trips
GET    /api/v1/trips/{trip_id}
PATCH  /api/v1/trips/{trip_id}
GET    /api/v1/trips/{trip_id}/versions
POST   /api/v1/trips/{trip_id}/agent-runs
GET    /api/v1/agent-runs/{run_id}
GET    /api/v1/agent-runs/{run_id}/events
POST   /api/v1/agent-runs/{run_id}/decisions
POST   /api/v1/trips/{trip_id}/patch-proposals
POST   /api/v1/trips/{trip_id}/patch-proposals/{patch_id}/commit
POST   /api/v1/trips/{trip_id}/evidence
POST   /api/v1/trips/{trip_id}/orders:extract
POST   /api/v1/trips/{trip_id}/expenses
GET    /api/v1/trips/{trip_id}/budget
POST   /api/v1/trips/{trip_id}/exports
GET    /api/v1/providers
POST   /api/v1/providers/{provider_id}:probe
GET    /api/v1/mcp-servers
POST   /api/v1/mcp-servers/{server_id}:test
```

## 16. Agent—前端事件协议

首版采用 SSE，并参考 [AG-UI](https://github.com/ag-ui-protocol/ag-ui)的运行、步骤、文本、工具和状态事件设计。为减少依赖，先实现兼容思想的内部子集，不承诺完整 AG-UI 兼容。

### 16.1 事件封装

```json
{
  "event_id": "evt_...",
  "event_version": "1.0",
  "run_id": "run_...",
  "sequence": 42,
  "type": "STEP_FINISHED",
  "timestamp": "2026-08-30T10:00:00.123+08:00",
  "data": {}
}
```

事件类型：

- `RUN_STARTED`
- `RUN_STATUS_CHANGED`
- `STEP_STARTED`
- `STEP_PROGRESS`
- `STEP_FINISHED`
- `TOOL_CALL_STARTED`
- `TOOL_CALL_FINISHED`
- `EVIDENCE_ADDED`
- `STATE_PATCH`
- `MESSAGE_DELTA`
- `APPROVAL_REQUIRED`
- `RUN_COMPLETED`
- `RUN_FAILED`

### 16.2 隐私展示

- 前端显示“正在查询路线/天气/攻略”，不显示隐藏思维链；
- 工具输入输出只展示经过脱敏的摘要；
- 管理员高级模式可以查看 Provider、耗时、Token 和错误码；
- 客户端断线后通过 `Last-Event-ID` 恢复；
- 服务端保留有限事件历史，完整审计进入数据库。

## 17. Provider Adapter 规范

### 17.1 能力清单

每个 Adapter 实现：

```python
class ProviderAdapter(Protocol):
    provider_id: str
    async def capabilities(self) -> ProviderCapabilities: ...
    async def healthcheck(self) -> HealthStatus: ...
    async def invoke(self, operation: str, request: BaseModel) -> ProviderResult: ...
```

`ProviderResult`：

```json
{
  "status": "OK",
  "data": {},
  "warnings": [],
  "provenance": {
    "provider": "amap",
    "operation": "direction_v5_driving",
    "fetched_at": "2026-08-30T10:00:00+08:00",
    "request_id": null,
    "cache": "MISS",
    "raw_ref": "blob://..."
  }
}
```

### 17.2 网络策略

| 类型 | 连接超时 | 总超时 | 重试 |
|---|---:|---:|---|
| 地图/天气 | 3 s | 10 s | 429/5xx 最多 2 次，抖动退避 |
| 模型普通 | 5 s | 90 s | 建连/429/5xx 按幂等性处理 |
| 模型规划 | 5 s | 180 s | 不自动重复有工具副作用的完整运行 |
| 网页静态 | 5 s | 20 s | 最多 1 次 |
| 浏览器 | 10 s | 60 s | 默认不重试交互动作 |
| MCP | 5 s | 30 s | 只读工具按策略重试 |

必须识别 `Retry-After`，设置 Provider 级限流、熔断和缓存；地图、天气、OCR、抓取等外部数据 Provider 还必须设置每日/月度免费配额预算。DeepSeek 只执行峰谷费用统计和异常循环保护。

### 17.3 缓存建议

| 数据 | 建议 TTL |
|---|---:|
| 地理编码/POI 基础信息 | 7–30 天 |
| POI 营业、票价类动态字段 | 6–24 小时 |
| 路线 | 15–60 分钟；远期规划可更长 |
| 城市天气 | 30–60 分钟 |
| 天气预警 | 5–10 分钟 |
| 攻略正文 | 按 URL+内容 hash，7–30 天 |
| 模型最终规划 | 不按文本缓存；保存运行结果 |

缓存命中也必须返回原采集时间，不能伪装成实时查询。

### 17.4 配额、用量与成本控制

所有 REST、SDK、MCP、模型、浏览器和本地 OCR 调用必须进入统一用量账本。MCP 只是一种传输方式，调用高德 MCP 或 Firecrawl MCP 时仍按底层 Provider 的操作和配额计量，不能与 REST 分开计算。

首版必须支持：

- 外部数据 Provider 支持 `free_first` 和 `free_only` 两种策略；DeepSeek 使用 `meter_only`，只按峰谷定价统计，不参与免费额度阻断；
- Provider、凭据、用户、家庭、行程和 Agent Run 六个维度的调用量；
- 模型输入、输出、缓存命中和推理 Token；
- 地图搜索、路线、编码、天气、JS 初始化的独立配额组；
- Firecrawl credits、OCR 次数、浏览器分钟及 SMTP 发送量；
- 外部数据 API 的单次行程、用户月度和系统月度软预算/硬预算；
- 50%、75%、90% 和 100% 配额告警；
- 本地估算与 Provider 控制台/账单对账；
- 达到硬上限后缓存、降级、请求确认或阻止，不允许模型绕过。

价格、免费额度、默认调用预算、数据模型和验收标准见：[API 定价、免费额度与用量控制规格](./api-pricing-quota-and-cost-control.md)。

## 18. 数据来源与可信度

### 18.1 来源等级

| 等级 | 来源 |
|---|---|
| A | 用户确认订单、官方公告、官方景区/交通页面 |
| B | 高德/百度/和风等正式开放 API |
| C | 主流平台公开展示页、近期多来源攻略共识 |
| D | 单一攻略、自媒体、历史数据 |
| E | 模型常识、无来源估算 |

### 18.2 冲突处理

- 不以“多数票”覆盖更高等级来源；
- 同等级来源冲突时展示区间和差异；
- 价格冲突默认使用较保守上界进入预算；
- 营业时间冲突提示出发前复核；
- 模型必须说明使用了哪个来源和为什么；
- 用户确认值优先，但保留与外部来源的差异提示。

## 19. 安全、隐私与审计

### 19.1 Secret 管理

- API Key、OAuth token、SMTP 密码全部加密存储；
- 配置页面只能显示掩码，不能回显明文；
- 支持系统级、家庭级和用户级作用域；
- 导出备份时 Secret 默认排除，可单独加密导出；
- 日志统一执行 URL query、Header 和正文敏感字段清洗。

### 19.2 外部数据发送策略

模型运行前生成 Data Disclosure 摘要：

- 将发送哪些旅行地点和日期；
- 是否包含成员年龄/饮食偏好；
- 是否包含订单截图或消费信息；
- 发送给哪个 Provider；
- 用户是否允许该 Provider 用于视觉/记忆任务。

证件号码首版不存储。儿童、老人等信息只保留规划所需的年龄段和注意事项。

### 19.3 审计事件

至少记录：

- 登录和权限变化；
- Provider/MCP 配置和探测；
- 模型运行开始、结束、模型和用量；
- 工具调用及风险等级；
- 用户确认/拒绝；
- 行程 Patch 提交和回滚；
- 订单、消费、退款变更；
- 分享、导出、备份和恢复。

## 20. 可观测性与评估

### 20.1 Trace

采用 OpenTelemetry 风格的 trace/span：

```text
agent.run
  ├─ workflow.node.intake
  ├─ workflow.node.research
  │    ├─ provider.amap.places.search
  │    └─ provider.qweather.forecast
  ├─ model.generate.itinerary
  ├─ solver.route_and_time
  ├─ solver.budget
  └─ workflow.commit_patch
```

默认记录元数据和耗时，不记录含隐私的完整 Prompt/Response。OpenTelemetry 已提供统一语义约定体系，可参考[语义约定](https://opentelemetry.io/docs/specs/semconv/)。

### 20.2 Agent Evals

建立固定测试集：

- 北京 3 日家庭游；
- 上海亲子雨天计划；
- 成都老人慢节奏美食游；
- 跨城高铁 + 自驾接驳；
- 航班取消后的当天重排；
- 预算不足的多方案权衡；
- 用户锁定酒店后的局部调整；
- OCR 错误金额和退款识别；
- 恶意网页 Prompt Injection；
- MCP 工具 Schema 突然变化。

指标：

| 指标 | 目标方向 |
|---|---|
| 硬约束违反率 | 0 |
| 未引用实时事实率 | 持续降低 |
| 路线不可达率 | 0 |
| 预算算术误差 | 0 |
| Patch 越界修改率 | 0 |
| 用户确认前副作用率 | 0 |
| 工具参数 Schema 通过率 | 100% |
| 规划任务成功恢复率 | >99%（受控故障测试） |

## 21. 资源与性能设计

### 21.1 默认常驻组件

```text
reverse proxy（可合并）
FastAPI 单进程
SQLite WAL
前端静态文件
轻量后台任务循环
```

默认不常驻：Chromium、PaddleOCR 模型、向量数据库、Redis、Celery、PostgreSQL、MCP stdio 子进程和本地大模型。

### 21.2 重任务策略

- OCR：子进程并发 1，完成释放模型和进程；
- 浏览器：并发 1，任务结束关闭 Browser；
- PDF：并发 1，按页处理，设置页数/像素限制；
- Agent：同时最多 2 个普通规划，重研究任务 1 个；
- 外部 MCP stdio：按需启动，空闲回收；
- 大结果：写磁盘 Blob，状态只保存引用。

### 21.3 框架 PoC 性能门槛

LangGraph、Pydantic AI 等候选进入主线前，必须测量：

1. FastAPI 空闲 RSS 增量；
2. 100 个检查点序列化耗时和 SQLite 大小；
3. 单个规划工作流峰值内存；
4. MCP 客户端连接空闲资源；
5. 中断后恢复正确性；
6. 依赖数量、镜像大小和冷启动时间。

如果 LangGraph 对资源或 SQLite 集成不满足要求，保留相同 `WorkflowRuntime` 接口，改用自有显式状态机；业务 Schema、节点和事件协议不变。

## 22. 首版接入决策

### 22.1 必须实现

- 高德 Web API Adapter；
- 高德 JS 地图和导航跳转；
- 高德天气降级；
- DeepSeek/OpenAI-compatible ModelProvider；
- HTTP 静态网页读取；
- 用户文本、截图、PDF 导入；
- 内部预算与约束求解器；
- MCP Client/Gateway 基础能力；
- SSE Agent 事件；
- Trip Patch 提案、确认、提交和审计。

### 22.2 可配置实现

- 和风天气；
- 百度地图补充；
- 高德 MCP；
- PaddleOCR 本地 Profile；
- 百度 OCR；
- Playwright crawler Profile；
- Firecrawl API/MCP；
- OpenAI/Anthropic/Gemini 原生模型；
- SMTP 和 ICS。

### 22.3 仅预留接口

- 携程、飞猪、美团交易/价格接口；
- 12306 非公开查询或购票接口；
- 航司下单、出票、改签；
- 支付；
- A2A 对外智能体协作；
- 自动发布到第三方内容平台。

## 23. 技术验证任务

| PoC | 目的 | 通过条件 |
|---|---|---|
| POC-API-001 | 高德完整路线 | 驾车/公交/步行结果可归一化，费用字段可追溯 |
| POC-API-002 | 高德+百度地点去重 | 不误合并同名异地 POI，坐标转换可回归 |
| POC-API-003 | 和风预警 | 能正确处理更新、取消、过期和时区 |
| POC-LLM-001 | DeepSeek 工具循环 | Thinking/非 Thinking、流式、工具和结构化输出均通过 |
| POC-LLM-002 | 模型兼容探测 | 至少 2 个 OpenAI-compatible 服务能被正确区分能力 |
| POC-AGENT-001 | 可恢复工作流 | 在任意节点终止进程后可从检查点恢复 |
| POC-AGENT-002 | 局部 Patch | 不修改锁定/已完成项，版本冲突返回 409 |
| POC-MCP-001 | 高德 MCP | Streamable HTTP 连接、工具过滤、超时和审计通过 |
| POC-MCP-002 | 恶意 MCP | Prompt Injection、超大结果、Schema 变化被阻断 |
| POC-OCR-001 | 订单截图 | 10 类真实脱敏样本字段准确率和用户修正流程可接受 |
| POC-PERF-001 | 资源基线 | 空闲 <512 MB，受控正常峰值 <2 GB |
| POC-COST-001 | 免费优先 | 默认典型家庭用量下地图、天气、网页和 OCR 不产生超额费用 |
| POC-COST-002 | 外部硬预算 | 地图、天气、OCR、抓取等外部数据服务达到硬限额后不再发出潜在付费请求；DeepSeek 不受此项阻断 |
| POC-COST-003 | 统一计量 | REST、MCP、SDK 和重试可关联且不重复计量 |

## 24. 设计基线与待验证项

### 24.1 已确定基线

1. 高德 Web Service 与 URI/HTTPS 跳转是 P0；专属地图是 P1，账号配额和字段差异通过 Provider 探测处理；
2. 百度保持 P1 回退和影子校验，不让其字段可用性阻塞高德主链路；
3. 和风天气作为已配置的 P1 详细天气 Provider，高德天气是 P0 降级；
4. 首版 OCR 使用服务端轻量 PP-OCR 子进程，用户确认后落库；视觉模型只在用户选择后复核；
5. 领域层定义自有 `WorkflowRuntime`、状态、节点和检查点接口；LangGraph 仅作为可替换适配器候选，PoC 不通过时使用自有显式状态机；
6. 首版采用自有 `ModelProvider + AgentNode`，不强制引入 Pydantic AI；后续可在节点内部替换而不接管业务事务；
7. 首版实现内部 SSE 事件子集，参考 AG-UI 语义但不承诺完整兼容；
8. 只有系统管理员能新增远程 MCP 地址和凭据；家庭管理员只能启停系统管理员已批准的 Provider；
9. P0 攻略来源是用户 URL/文本/截图和公开 Web/官方来源；模型内置搜索、Firecrawl与小红书只读 Worker均为可选 Provider；
10. 公开分享页默认不自动加载会向外部地图 Provider 暴露访问者 IP/坐标的组件；用户点击“打开地图/导航”后再跳转并明确离开本站。

### 24.2 进入对应模块实现前的验证

- 高德、百度、和风账号的实际字段、配额和免费策略；
- PP-OCR 在真实脱敏订单/票据上的准确率、峰值内存和模型版本；
- LangGraph SQLite 适配的异步、升级、恢复和资源表现；
- Chromium PDF 打印在目标 NAS 的中文排版和峰值内存；
- 可选攻略搜索 Provider 的稳定性、许可、资源与 Go/No-Go 门。

## 25. 推荐实施顺序

### 阶段 A：契约先行

1. 定义 Place、Route、Weather、Evidence、PriceObservation、TripPatch JSON Schema；
2. 生成 Pydantic 模型和 OpenAPI；
3. 建立 Provider contract tests；
4. 建立模型能力描述和探测协议。

### 阶段 B：确定性核心

1. Trip version/Patch/审计；
2. 时间和预算引擎；
3. 路线、地点和天气 Adapter；
4. Evidence 和价格观察。

### 阶段 C：智能体工作流

1. Intake；
2. Research；
3. Itinerary + Route + Budget；
4. Critic；
5. Approval/Resume；
6. 局部 Patch。

### 阶段 D：插件和资料处理

1. MCP Gateway；
2. 高德 MCP；
3. OCR；
4. Playwright/Firecrawl Profile；
5. 外部 Provider 扩展 SDK。

## 26. 来源索引

### 标准与协议

- [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12)
- [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html)
- [MCP Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [MCP Transports 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [MCP Authorization 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [AG-UI](https://github.com/ag-ui-protocol/ag-ui)
- [A2A Protocol](https://github.com/a2aproject/A2A/blob/main/docs/specification.md)

### 智能体框架

- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/agents/)
- [OpenAI Agent Orchestration](https://openai.github.io/openai-agents-python/multi_agent/)
- [OpenAI Guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [Pydantic AI](https://pydantic.dev/docs/ai/overview/)
- [Pydantic AI MCP Client](https://pydantic.dev/docs/ai/mcp/client/)
- [AutoGen](https://microsoft.github.io/autogen/stable/index.html)
- [Google ADK](https://google.github.io/adk-docs/)

### 国内服务

- [高德路径规划 2.0](https://lbs.amap.com/api/webservice/guide/api/newroute)
- [高德 MCP Server](https://lbs.amap.com/api/mcp-server/summary)
- [高德 MCP 快速接入](https://lbs.amap.com/api/mcp-server/gettingstarted)
- [百度 Web API](https://lbsyun.baidu.com/faq/api?title=webapi)
- [和风天气](https://dev.qweather.com/en/docs/)
- [高德天气](https://lbs.amap.com/api/webservice/guide/api/weatherinfo)
- [美团生态开放平台](https://openapi.meituan.com/)
- [携程商旅开发者平台](https://openapi.ctripbiz.com/)
- [百度 OCR](https://ai.baidu.com/ai-doc/index/OCR)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)

### 模型与网页工具

- [DeepSeek API](https://api-docs.deepseek.com/)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- [Gemini Function Calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Gemini Structured Output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Firecrawl](https://docs.firecrawl.dev/introduction)
- [Playwright Python](https://playwright.dev/python/)

## 27. 文档维护规则

- 每个外部 Provider Adapter 必须记录 `docs_checked_at` 和文档 URL；
- 接口字段变化先更新契约测试，再更新 Adapter；
- 价格、配额和模型名称不写死在本规格中；
- 每季度或重大版本发布后复核 MCP、模型和地图平台文档；
- 调研中“已存在平台”不等于“当前账号可调用”；只有控制台申请和 PoC 通过后，状态才能从 `RESEARCHED` 改为 `VERIFIED`；
- 所有第三方开源工具上线前复核许可证、最近发布、安全公告、AMD64 镜像和资源占用。

## 附录 A：已核验外部端点登记表

下表只登记已从官方资料核验的入口。它不是完整字段抄录；字段级契约由 Adapter 的 fixture 和 contract test 固化。第三方升级版本后，旧 fixture 必须继续用于兼容性回归。

| ID | Provider | Operation | Method / Endpoint | 认证 | 归一化输出 | 状态 |
|---|---|---|---|---|---|---|
| EXT-AMAP-001 | 高德 | POI 关键词 | `GET https://restapi.amap.com/v5/place/text` | query `key` | `PlaceCandidate[]` | 文档已核验，账号待实测 |
| EXT-AMAP-002 | 高德 | POI 周边 | `GET https://restapi.amap.com/v5/place/around` | query `key` | `PlaceCandidate[]` | 文档已核验，账号待实测 |
| EXT-AMAP-003 | 高德 | 驾车路线 | `GET/POST https://restapi.amap.com/v5/direction/driving` | query/body `key`，以官方要求为准 | `RoutePlan[]` | 文档已核验，账号待实测 |
| EXT-AMAP-004 | 高德 | 公交路线 | `GET https://restapi.amap.com/v5/direction/transit/integrated` | query `key` | `RoutePlan[]` | 文档已核验，账号待实测 |
| EXT-AMAP-005 | 高德 | 步行路线 | `GET https://restapi.amap.com/v5/direction/walking` | query `key` | `RoutePlan[]` | 文档已核验，账号待实测 |
| EXT-AMAP-006 | 高德 | 城市天气 | `GET https://restapi.amap.com/v3/weather/weatherInfo` | query `key` | `WeatherSnapshot` | 文档已核验，账号待实测 |
| EXT-AMAP-007 | 高德 | MCP | `POST https://mcp.amap.com/mcp?key=...` | query API Key | MCP Tools | 文档已核验，工具表待连接 |
| EXT-BAIDU-001 | 百度 | 行政区 POI | `GET https://api.map.baidu.com/place/v3/region` | query `ak` | `PlaceCandidate[]` | 文档已核验，账号待实测 |
| EXT-BAIDU-002 | 百度 | 周边 POI | `GET https://api.map.baidu.com/place/v3/around` | query `ak` | `PlaceCandidate[]` | 文档已核验，账号待实测 |
| EXT-BAIDU-003 | 百度 | POI 详情 | `GET https://api.map.baidu.com/place/v3/detail` | query `ak` | `PlaceDetails` | 文档已核验，账号待实测 |
| EXT-BAIDU-004 | 百度 | 输入提示 | `GET https://api.map.baidu.com/place/v3/suggestion` | query `ak` | `PlaceCandidate[]` | 文档已核验，账号待实测 |
| EXT-QW-001 | 和风 | 日预报 | `GET https://{api_host}/weather/v1/daily/{lat}/{lon}` | Bearer JWT | `WeatherForecast` | 文档已核验，订阅待选择 |
| EXT-QW-002 | 和风 | 当前预警 | `GET https://{api_host}/weatheralert/v1/current/{lat}/{lon}` | Bearer JWT | `WeatherAlert[]` | 文档已核验，订阅待选择 |
| EXT-DS-001 | DeepSeek | Chat | `POST https://api.deepseek.com/chat/completions` | Bearer API Key | `ModelResponse` | 文档已核验，Key 待实测 |
| EXT-DS-002 | DeepSeek | Responses | `POST https://api.deepseek.com/responses` | Bearer API Key | `ModelResponse` | 文档已核验，模型能力待探测 |
| EXT-FC-001 | Firecrawl | 单页抓取 | `POST https://api.firecrawl.dev/v2/scrape` | Bearer API Key | `Evidence` | 可选云服务 |
| EXT-FC-002 | Firecrawl | 搜索 | `POST https://api.firecrawl.dev/v2/search` | Bearer API Key | `SearchResult[]` | 可选云服务 |

### A.1 外部端点登记模板

新增任何端点前必须填写：

```yaml
id: EXT-PROVIDER-000
provider: provider-id
operation: stable_internal_operation
official_docs_url: https://...
docs_checked_at: 2026-08-30
endpoint: https://...
method: GET
auth:
  type: api_key_header
  secret_scope: system
request_schema_ref: schemas/provider/request.json
response_schema_ref: schemas/provider/response.json
normalized_schema_ref: schemas/domain/result.json
coordinate_system: null
money_unit: null
timezone_behavior: explicit
rate_limit: account_console_required
cache_ttl_s: 3600
timeout_s: 10
retry_policy: read_safe
terms_review: required
fixture_refs:
  - tests/fixtures/provider/success.json
  - tests/fixtures/provider/no_result.json
  - tests/fixtures/provider/rate_limited.json
status: researched
```

### A.2 状态定义

- `researched`：官方文档存在，但未使用本项目账号调用；
- `verified`：测试 Key 调用成功，fixture 和字段映射已固化；
- `limited`：可调用，但配额、资质或字段不满足默认用途；
- `degraded`：近期错误率或字段变化导致暂停主用；
- `retired`：不再允许新调用，仅保留历史数据解释。

## 附录 B：MCP 当前协议兼容要求

针对 2026-07-28 协议及旧版服务器，MCP Gateway 必须：

1. 每个请求保留协议版本、客户端信息和能力元数据；
2. 优先使用 `server/discover`，对旧服务回退到 `initialize`；
3. 不依赖 `Mcp-Session-Id` 进行业务关联，内部使用自己的 `run_id`；
4. 兼容 Streamable HTTP 的 JSON 响应和请求级 SSE 响应；
5. 对旧协议的 server-initiated 请求默认拒绝 Sampling/Roots/Elicitation，除非配置明确开启；
6. 锁定官方 SDK 版本并执行协议版本矩阵测试；
7. 将 Tasks、Skills over MCP、MCP Apps 等扩展视为实验能力，首版默认关闭；
8. 不让扩展绕过内部审批、数据最小化和工具风险等级。
