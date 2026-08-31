# 智能旅游规划工具：个人/小团队自托管版设计方案

> 日期：2026-08-30
> 部署目标：单机或家庭服务器 Docker Compose
> 使用范围：个人、家庭或小团队低频使用，不开展自动售票、代订、内容分发或商业数据服务
> 规格状态：需求基线复核通过，进入设计阶段
> 关联文档：[系统运行流程与设计准入复核](./system-runtime-flow-and-design-readiness-review.md)、[国内 API、MCP 与数据源调研](./domestic-travel-agent-integration-research.md)

## 1. 方案定位

本版本不是大型旅游交易平台，而是一套用户完全掌控数据、密钥和部署环境的个人旅行助手：

- 用户自己部署，默认只在本机或家庭局域网开放；
- 用户自己配置 DeepSeek、高德、百度等 API Key；
- 系统生成计划、估算预算、检查合理性、整理攻略和记录实际消费；
- 机票、酒店、门票等不自动下单，统一跳转官方或 OTA 页面；
- 不依赖携程、美团、飞猪等商业合作接口；
- 不把小红书非公开 API、12306 非官方接口当作稳定基础设施；
- 所有第三方数据都保留来源链接和查询时间；
- 核心能力在第三方接口不可用时仍能以降级方式运行。

这会显著降低开发、运维和合规复杂度，同时保留未来增加正式数据源的接口。

## 2. 优化后的产品范围

## 2.1 MVP 必做功能

### 对话与需求结构化

- 通过自然语言描述旅行需求；
- 自动提取出发地、目的地、日期、人数、预算、偏好和约束；
- 缺少关键条件时只追问真正影响结果的问题；
- 保存多轮会话和需求版本；
- 支持重新生成、局部调整和方案对比。

### 全过程行程

- 家/集合点到机场、车站或自驾出发点；
- 飞机、高铁、自驾等城际交通段；
- 酒店、景点、餐厅之间的市内路线；
- 返程交通和到家路线；
- 每段显示时间、距离、交通方式、预算、来源和导航链接；
- 支持高德、百度或浏览器地图跳转。

### 预算计算

- 成人、儿童、老人、学生人数；
- 机票/火车票/门票按人计算；
- 打车、自驾、停车、过路费按车辆计算；
- 酒店按房间与晚数计算；
- 餐饮按人均或用户自定义预算计算；
- 总价、人均价、固定费用、可选费用和预留金；
- 预算版本与实际消费对比。

### 合理性审计

- 当天时间是否排满或冲突；
- 景点是否可能闭馆；
- 路线是否明显折返；
- 机场/火车站缓冲是否不足；
- 老人儿童步行和体力负担；
- 用餐时段是否合理；
- 预算是否漏项或超支；
- 输出问题严重程度和修改建议。

### 攻略整理

- 用户粘贴网页、小红书、马蜂窝等分享链接；
- 用户也可粘贴文字、上传 Markdown/PDF/截图；
- 提取 POI、建议时间、避坑事项和价格线索；
- 使用地图 API 重新识别 POI 和路线；
- 保留原链接，不默认复制完整文章和图片；
- 多篇攻略合并时标记共识和冲突。

### 实际消费

- 手工录入；
- 上传小票或支付截图；
- OCR 提取金额、时间和商户，用户确认后入账；
- 分类、垫付人、参与人、退款和备注；
- 计划预算与实际消费匹配；
- 导出 CSV/JSON。

## 2.2 首版明确不做

- 自动购买机票、酒店、火车票和景区门票；
- 代用户登录 12306、OTA 或支付平台；
- 验证码处理、抢票、监控余票和自动占座；
- 大规模抓取小红书、大众点评、携程等平台；
- 社交广场、攻略公开发布和用户增长系统；
- 商家后台、佣金结算和供应链系统；
- 多租户计费、复杂 RBAC 和企业 SSO；
- Kubernetes、微服务拆分和高可用集群。

## 3. 最小可行技术架构

```text
手机 / 平板 / PC 浏览器
          │ HTTPS / 局域网
          ▼
  Web PWA（响应式界面）
          │ REST + SSE
          ▼
  Travel API 单体服务
  ├─ 会话与行程服务
  ├─ LLM 编排器
  ├─ 地图适配器
  ├─ 预算引擎
  ├─ 合理性规则引擎
  ├─ 攻略提取器
  ├─ 消费与附件服务
  └─ 定时刷新任务
          │
  ┌───────┼─────────┬──────────┐
  ▼       ▼         ▼          ▼
SQLite  本地文件   DeepSeek   高德/百度
```

核心建议：采用“模块化单体”，代码内保持清晰模块边界，但不把每个模块拆成独立容器。对当前规模，微服务只会增加网络、鉴权、日志、升级和排障成本。

## 4. 推荐技术栈

## 4.1 前端

建议：React + TypeScript + Vite 或 Next.js 静态/客户端模式。

首版更推荐 Vite PWA：

- 镜像小、启动简单；
- 适合纯 API 后端；
- 响应式移动端实现直接；
- 可“添加到主屏幕”；
- 无需引入服务端渲染复杂度。

主要界面：

- 对话规划页；
- 行程时间线；
- 地图与每日路线；
- 预算明细；
- 攻略来源抽屉；
- 消费账本；
- 系统设置和连接测试。

## 4.2 后端

建议：Python + FastAPI。

理由：

- 适合 LLM、OCR、文档解析和优化算法生态；
- OpenAPI 文档自动生成；
- SSE 流式输出实现简单；
- Pydantic 可严格校验模型输出和第三方数据；
- 后续可接 OR-Tools、Playwright、PaddleOCR 等。

如果团队更熟悉 TypeScript，NestJS 也可行，但不建议为了“Agent 框架”而改变团队最熟悉的技术栈。

## 4.3 数据库

默认：SQLite + WAL 模式。

适用于：

- 单用户或家庭使用；
- 低并发；
- 单个 API 容器；
- 便于备份和迁移。

注意：

- 数据库文件放在 Docker Volume；
- 只能由 API 主进程管理写入；
- 开启 WAL、外键和定期 checkpoint；
- 附件不存数据库二进制，存文件卷并保存哈希和相对路径。

可选 PostgreSQL Profile：当需要多人同时使用、远程服务器部署或复杂检索时启用。数据库访问通过 ORM/Repository 隔离，避免业务代码依赖 SQLite 特性。

## 4.4 后台任务

首版不需要 Redis/Celery。

推荐：

- FastAPI 进程内任务或 APScheduler；
- 数据库表保存任务状态；
- 长任务使用一个独立 `worker` 容器，但复用同一代码镜像；
- 同一任务设置幂等键，防止重复生成行程或重复 OCR。

需要持续监控、大批量抓取或多 worker 后，再引入 Redis 队列。

## 5. Docker Compose 部署形态

## 5.1 默认最小部署

```text
travel-web   80/8080   前端静态资源与反向代理
travel-api   8000      后端、SQLite、任务调度
travel-data  volume    数据库、附件、备份
```

推荐对外只暴露 Web 端口，API 仅在 Compose 内部网络可访问。Web 容器将 `/api` 反向代理到 `travel-api`。

## 5.2 可选 Compose Profiles

```text
profile: postgres    PostgreSQL 替代 SQLite
profile: ollama      本地模型推理
profile: llm-gateway LiteLLM 多模型网关
profile: crawler     隔离的浏览器提取服务
profile: observability Langfuse（仅调试需要）
```

默认配置不启动任何 Profile，降低内存和维护成本。

## 5.3 Compose 设计草案

```yaml
services:
  web:
    image: travel-planner-web:${APP_VERSION:-latest}
    restart: unless-stopped
    ports:
      - "${WEB_PORT:-8080}:80"
    depends_on:
      api:
        condition: service_healthy
    networks: [travel_net]

  api:
    image: travel-planner-api:${APP_VERSION:-latest}
    restart: unless-stopped
    env_file: .env
    volumes:
      - travel_data:/app/data
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks: [travel_net]

volumes:
  travel_data:

networks:
  travel_net:
```

正式实现时应固定镜像版本，避免生产环境直接使用会漂移的 `latest`。

## 5.4 目录和卷

容器内建议：

```text
/app/data/
├── travel.db
├── uploads/
│   ├── receipts/
│   ├── guides/
│   └── exports/
├── cache/
├── backups/
└── logs/
```

上传文件以 UUID 命名，原文件名只保存为数据库元数据。路径必须经过规范化，禁止 `../` 和绝对路径。

## 6. 自定义模型与 DeepSeek 接入

## 6.1 统一 OpenAI-compatible 接口

DeepSeek 官方 API 支持 OpenAI 兼容格式，当前官方基础地址为 `https://api.deepseek.com`。模型名称和价格会更新，因此应用不能把模型名写死，应全部由配置提供。[DeepSeek API 快速开始](https://api-docs.deepseek.com/)

统一配置：

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=replace_me
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=120
LLM_MAX_RETRIES=2
LLM_MAX_OUTPUT_TOKENS=12000
LLM_TEMPERATURE=0.2
```

`LLM_MODEL` 只作为示例。部署者应在设置页或 `.env` 中填写供应商当前支持的模型。

## 6.2 模型能力探测

不同“OpenAI-compatible”服务并不完全兼容。连接模型时应运行一次能力测试：

- 普通对话；
- SSE 流式响应；
- JSON Schema/JSON mode；
- Tool Calling；
- 最大上下文与最大输出；
- 是否支持图片输入；
- 是否返回 token usage；
- 错误码和限流行为。

结果保存为 `ModelCapabilities`：

```json
{
  "streaming": true,
  "tool_calling": true,
  "json_mode": true,
  "vision": false,
  "usage_reporting": true,
  "tested_at": "2026-08-30T12:00:00+08:00"
}
```

如果模型不支持工具调用，系统可以退化为“两阶段 JSON 指令”：先让模型输出经过 Schema 校验的工具请求，应用执行后再把结果传回模型。

## 6.3 直接接入还是 LiteLLM

### MVP 推荐：后端直接接入

后端实现一个薄的 `LLMProvider`：

```python
class LLMProvider(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...
    async def healthcheck(self) -> ModelHealth: ...
```

优势：少一个容器、少一套数据库和管理界面，故障面更小。

### 多模型后再启用 LiteLLM

[LiteLLM](https://github.com/BerriAI/litellm)可自托管为统一 OpenAI 格式网关，支持多个模型供应商、费用跟踪、重试、Fallback 和预算限制。适合以下情况：

- 同时使用 DeepSeek、OpenAI-compatible 和本地模型；
- 希望不同任务使用不同模型；
- 需要网关级预算、调用日志和故障转移；
- 多个应用共用模型入口。

个人单模型部署不必一开始引入 LiteLLM。

## 6.4 本地模型

可选 Ollama Profile：

```dotenv
LLM_BASE_URL=http://ollama:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=用户已下载的模型名
```

[Ollama](https://docs.ollama.com/api/openai-compatibility)支持部分 OpenAI API、流式、JSON、工具调用和嵌入，并有[官方 Docker 部署文档](https://docs.ollama.com/docker)。

适合本地模型的任务：

- 攻略摘要；
- OCR 结果整理；
- 消费分类；
- 简单结构化提取。

复杂多日路线规划和工具编排是否可用取决于模型能力，不能因为能聊天就认为能稳定调用工具。建议保留云模型作为可选主模型或失败回退。

## 6.5 模型分工

小系统不需要多个独立 Agent 进程，但可以在同一编排器内定义任务角色：

| 任务 | 模型要求 | 温度 | 是否允许工具 |
|---|---|---:|---|
| 需求结构化 | JSON 稳定 | 0～0.2 | 否 |
| POI 候选生成 | 语言与工具调用 | 0.3～0.6 | 是 |
| 行程编排 | 长上下文、推理 | 0.2～0.4 | 是 |
| 合理性复审 | 批判性、JSON | 0～0.2 | 可读工具结果 |
| 攻略摘要 | 长文本 | 0.2 | 否 |
| 消费分类 | 小模型即可 | 0 | 否 |

用同一个模型也可以完成这些任务，角色是提示词和 Schema 层面的分工，不代表必须启动多个 Agent 服务。

## 7. Agent 编排优化

## 7.1 受控工作流而非完全自治

旅行计划涉及真实时间、地点和费用。推荐“有限自治”：

```text
用户需求
  → 结构化和缺项检查
  → 搜索候选 POI
  → 获取地图事实
  → 生成候选日程
  → 确定性预算计算
  → 规则审计
  → 模型解释与修正
  → 用户确认
```

模型可以决定调用哪些只读工具，但以下操作必须由应用控制：

- API 调用次数上限；
- 可访问域名；
- 价格计算；
- 数据写入；
- 文件访问；
- 对外跳转；
- 删除和覆盖。

## 7.2 单次规划工具预算

建议默认限制：

- 最多 2 次需求澄清；
- POI 搜索每城市每类别 1～2 次；
- POI 详情最多 30 个候选；
- 精确路线只计算最终候选，初筛用矩阵或缓存；
- 模型工具循环最多 8～12 轮；
- 同一请求总超时 3～5 分钟；
- 用户取消后立即停止后续调用。

这既控制 API 和 Token 成本，也降低模型陷入循环的概率。

## 7.3 结构化中间状态

不要让每一步都把完整聊天历史重新发送给模型。保存：

- `TripRequirements`；
- `CandidatePlace[]`；
- `RouteOption[]`；
- `ItineraryDraft`；
- `BudgetSummary`；
- `AuditIssue[]`；
- `Evidence[]`。

下一步只发送必要字段和摘要。长攻略原文先分块提取事实，再合并结果，可显著降低 Token 消耗。

## 7.4 防止模型虚构

行程中的字段应有状态：

- `verified`：由外部工具或用户确认；
- `estimated`：按规则估算；
- `suggested`：模型建议；
- `unknown`：没有可靠数据；
- `stale`：数据已过期。

模型不能把 `suggested` 改成 `verified`。前端通过颜色和图标区分。

## 8. 地图和价格数据的低频接入

## 8.1 默认数据源

推荐配置：

```dotenv
MAP_PRIMARY=amap
AMAP_API_KEY=replace_me
MAP_FALLBACK=none
BAIDU_MAP_API_KEY=
```

个人使用可以只配置高德。百度仅在用户有 Key 时作为回退或对照，不应要求两个地图 Key 才能启动。

## 8.2 免费配额优化

- 地理编码和 POI 详情长期缓存；
- 相同起终点、日期和模式的路线缓存；
- 拖动编辑过程中只计算近似距离，用户停止后再精算；
- 批量候选先用直线距离预筛；
- 只对最终行程生成逐步路线；
- 失败采用指数退避，避免快速耗尽配额；
- 设置每天和每次规划的调用上限；
- 设置页显示今日调用量和最近错误。

低频、非商业使用仍需遵守各平台服务协议和展示要求；“不商用”不等于可以绕过配额、复制数据或无视平台规则。

## 8.3 价格降级规则

无商业 OTA API 时：

- 火车票：用户手动输入或打开 12306 查询；
- 机票/酒店/门票：打开官方/OTA 搜索页，用户回填价格；
- 餐厅：地图人均作为估算，可手动覆盖；
- 自驾：地图里程和过路费 + 用户维护油价/电价；
- 打车：地图估价，标明最终以打车 App 为准；
- 所有手动价格允许上传截图作为证据。

产品体验上，可提供“复制查询条件”和“一键打开查询页面”，减少用户重复输入。

## 9. 攻略读取的自托管方案

## 9.1 默认安全路径

```text
用户提供 URL/文字/文件
  → 域名和文件类型检查
  → 普通 HTTP 抽取
  → 失败则提示用户粘贴正文或上传截图
  → 用户明确授权后才启动浏览器提取
```

系统不应后台定时抓取攻略平台，也不应自动发现并批量下载内容。

## 9.2 crawler Profile

可选浏览器服务单独容器运行：

- 无宿主文件系统写权限；
- 只挂载临时目录；
- 不可访问 Docker Socket；
- 禁止访问局域网、回环地址和云元数据地址；
- 域名白名单；
- 单任务页数、响应体大小和执行时间限制；
- 浏览器上下文任务结束即销毁；
- 不记录 Cookie 和页面敏感字段。

Crawl4AI、Firecrawl 或 Playwright 都只是技术候选。若使用 Crawl4AI，应采用已修复已知漏洞的版本并保持容器仅内网访问；其历史 Docker API 曾出现 SSRF、RCE 和文件写入问题，不能裸露到公网。[Crawl4AI 安全公告](https://github.com/unclecode/crawl4ai/security)

## 9.3 小红书策略

首版只实现：

- 接受用户分享链接；
- 尝试读取无需登录即可公开展示的标题和摘要；
- 读取失败时要求用户粘贴正文或上传截图；
- 保留“打开原文”按钮；
- P0 不自动登录、不保存小红书 Cookie、不调用非公开签名接口。

这会牺牲自动化程度，但更稳定，也更符合个人工具应有的安全边界。

P1/R 可以启用独立的用户授权只读 Worker：只保存用户扫码产生的加密浏览器会话，不保存账号密码，不提供发布/互动，不绕过验证码或风控，并且 Chromium 按需运行。该组件不属于默认 Compose，完整边界和 PoC 门见：[小红书旅游攻略查询工具规格与可行性研究](./xiaohongshu-guide-search-tool-spec-and-feasibility.md)。

## 10. 数据模型建议

核心实体：

```text
UserSettings
ModelConnection
MapConnection
Trip
TripRequirement
TripDay
TripItem
TripLeg
Place
RouteSnapshot
PriceObservation
BudgetItem
Evidence
GuideSource
Expense
Receipt
Job
AuditLog
```

## 10.1 TripItem

```json
{
  "id": "uuid",
  "type": "attraction",
  "title": "某景点",
  "start_at": "2026-10-02T09:00:00+08:00",
  "end_at": "2026-10-02T11:30:00+08:00",
  "place_id": "uuid",
  "status": "planned",
  "verification": "estimated",
  "evidence_ids": ["uuid"],
  "notes": ""
}
```

## 10.2 PriceObservation

同一项目可以保存多次价格观察，不覆盖历史：

```json
{
  "subject_type": "hotel",
  "subject_id": "uuid",
  "amount": 399,
  "currency": "CNY",
  "unit": "room_night",
  "price_type": "manual_quote",
  "source_url": "https://...",
  "observed_at": "2026-08-30T12:00:00+08:00",
  "expires_at": null,
  "confidence": 0.9
}
```

## 10.3 Evidence

```json
{
  "kind": "map_api",
  "source_name": "amap",
  "source_url": null,
  "retrieved_at": "2026-08-30T12:00:00+08:00",
  "claim": "预计驾车 38 分钟",
  "raw_snapshot_path": "snapshots/sha256.json",
  "status": "fresh"
}
```

## 11. API 设计建议

```text
POST   /api/v1/chat/messages
GET    /api/v1/chat/streams/{job_id}
POST   /api/v1/trips
GET    /api/v1/trips/{id}
PATCH  /api/v1/trips/{id}/requirements
POST   /api/v1/trips/{id}/generate
POST   /api/v1/trips/{id}/audit
POST   /api/v1/trips/{id}/replan
GET    /api/v1/trips/{id}/budget
POST   /api/v1/trips/{id}/sources
POST   /api/v1/trips/{id}/expenses
POST   /api/v1/receipts/ocr
POST   /api/v1/connections/llm/test
POST   /api/v1/connections/map/test
GET    /api/v1/system/health
POST   /api/v1/system/backup
```

生成类接口返回 `job_id`，前端通过 SSE 获取阶段进度。刷新页面后仍可读取数据库中的任务状态。

## 12. 配置与密钥

## 12.1 `.env.example`

```dotenv
APP_ENV=production
APP_SECRET=replace_with_random_value
PUBLIC_BASE_URL=http://localhost:8080
DATA_DIR=/app/data
DATABASE_URL=sqlite:////app/data/travel.db

LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=120
LLM_DAILY_TOKEN_BUDGET=500000

MAP_PRIMARY=amap
AMAP_API_KEY=
BAIDU_MAP_API_KEY=

CRAWLER_ENABLED=false
ALLOW_PRIVATE_NETWORK_FETCH=false
TELEMETRY_ENABLED=false
```

## 12.2 设置页

个人用户通常不愿编辑配置文件，因此界面应支持：

- 配置模型 Base URL、Key 和模型名；
- “测试连接”并显示能力探测结果；
- 配置地图 Key；
- 设置每日 Token/API 调用预算；
- 导入/导出不含密钥的系统配置；
- 删除 Key 和清空模型调用日志。

密钥优先通过环境变量注入。若允许在 UI 保存，必须使用由 `APP_SECRET` 派生的加密密钥加密，且备份默认不包含明文密钥。

## 13. 安全设计

## 13.1 网络

- 默认监听 `127.0.0.1` 或局域网，不直接暴露公网；
- 远程访问优先使用 Tailscale/WireGuard；
- 若公开到互联网，必须配置 HTTPS、登录、限流和反向代理；
- API、数据库、Ollama、LiteLLM、crawler 不直接映射公网端口；
- 禁止容器访问 Docker Socket。

## 13.2 认证

单用户部署也应有密码或 Passkey，避免局域网其他设备读取家庭住址、票据和行程。

建议：

- 首次启动创建管理员；
- Argon2id 密码哈希；
- HttpOnly、Secure、SameSite Cookie；
- CSRF 防护；
- 可选关闭新用户注册；
- 登录失败限速。

## 13.3 文件与 URL

- 上传大小上限；
- MIME 与扩展名双重校验；
- 图片重编码后再 OCR；
- PDF 禁止执行脚本和外部链接；
- URL 解析后再次检查最终重定向地址；
- 禁止 `file://`、`ftp://`、`data:`、`javascript:`；
- 禁止访问回环、内网、链路本地和云元数据 IP；
- 外部内容永远按不可信数据处理，不得覆盖系统提示词。

## 13.4 隐私

- 精确家庭地址允许用“附近地点”替代；
- 发送到云模型前提示会上传哪些内容；
- OCR 可配置成本地模式；
- 日志不记录 API Key、Cookie、身份证号、完整票据；
- 支持一键导出和彻底删除用户数据；
- 附件和数据库一起备份，不上传未知云存储。

## 14. 备份、升级和恢复

## 14.1 备份

每日或手动备份：

- SQLite 在线备份；
- 上传附件；
- 系统配置；
- Schema 版本；
- 不默认包含 API Key。

备份输出单个加密归档，保留最近 7～30 份。必须实际测试恢复流程，而不只是生成压缩包。

## 14.2 升级

- Docker 镜像使用语义化版本；
- 升级前自动备份；
- 数据库迁移可回滚或至少有恢复说明；
- 不自动跟随 `latest`；
- 前端显示当前版本和可用迁移；
- 更新第三方抓取/浏览器组件时优先看安全公告。

## 15. 资源需求

## 15.1 云模型模式

仅 Web + API + SQLite：

- 2 核 CPU；
- 2～4 GB 内存；
- 10～30 GB 磁盘，取决于票据和攻略附件；
- 无 GPU；
- NAS、迷你主机、普通云服务器均可。

## 15.2 本地模型模式

取决于模型大小和量化方式：

- 小模型可使用 8～16 GB 系统内存；
- 中大型模型通常需要更多内存或独立 GPU；
- Apple Silicon 可直接在宿主机运行 Ollama，再让容器通过受控地址访问；
- 不建议为了本项目首版专门采购高端 GPU，先用 DeepSeek API 验证产品。

## 15.3 可选组件成本

Langfuse 虽可 Docker 自托管，但完整部署会引入 PostgreSQL、Redis、ClickHouse 和对象存储等组件，对个人系统偏重。[Langfuse 自托管说明](https://github.com/langfuse/langfuse-docs/blob/main/content/self-hosting/index.mdx)

建议首版只记录简化的模型调用日志：请求 ID、模型、耗时、Token、工具调用、错误和估算成本；需要调试复杂 Agent 后再启用 Langfuse Profile。

## 16. 成本控制

## 16.1 模型成本

- 结构化和分类任务使用便宜/本地模型；
- 只在最终行程生成和审计使用强模型；
- 攻略先本地分块提取再发送摘要；
- 工具结果只保留必要字段；
- 缓存相同目的地的稳定事实；
- 限制输出长度和工具循环次数；
- 设置日预算和单次规划预算；
- 设置页显示近 7/30 天 Token 和估算费用。

DeepSeek 的价格和模型名称会调整，成本计算应从配置或定期更新的价格表读取，不能硬编码文档快照。[DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing)

## 16.2 地图成本

- 默认一个地图供应商；
- 对稳定结果缓存；
- 对实时路线设置短 TTL；
- 对 POI 详情设置较长 TTL；
- 日调用上限达到 80% 时警告；
- 达到上限后允许用户手动输入距离和价格，不让整个系统不可用。

## 17. 可用性与降级

| 故障 | 降级行为 |
|---|---|
| 模型 API 不可用 | 保存需求，允许手工编辑行程；稍后重试 |
| Tool Calling 不支持 | 使用两阶段 JSON 工具请求 |
| 地图 API 不可用 | 使用已缓存路线、直线距离或手工录入 |
| POI 无结果 | 用户粘贴地图分享链接或手工创建地点 |
| 攻略网页不可读 | 粘贴正文、上传截图/PDF |
| 票价不可查 | 跳转官方页面并手工回填 |
| OCR 失败 | 保留原图，用户手工录入 |
| 后台任务中断 | 从数据库阶段状态恢复或安全重跑 |

系统应把“无法验证”明确呈现给用户，绝不自动编造缺失结果。

## 18. 开发阶段建议

## 阶段 A：基础骨架

- Docker Compose；
- Web + FastAPI；
- SQLite 和迁移；
- 用户登录；
- 设置页和模型连接测试；
- 高德连接测试；
- 健康检查、日志和备份。

## 阶段 B：旅行规划闭环

- 需求结构化；
- POI 搜索；
- 全过程 TripLeg；
- 行程生成；
- 预算引擎；
- 合理性规则；
- SSE 进度；
- 移动端导航链接。

## 阶段 C：攻略与消费

- URL/文字/PDF/截图导入；
- 证据和来源；
- OCR；
- 消费账本；
- 计划与实付对比；
- CSV/JSON 导出。

## 阶段 D：可选扩展

- 百度回退；
- Ollama；
- LiteLLM；
- PostgreSQL；
- 隔离 crawler；
- Langfuse；
- 多用户协作。

## 19. MVP 验收标准

- 一条命令 `docker compose up -d` 能启动；
- 首次启动 5 分钟内完成模型和地图配置；
- 手机浏览器可完整使用；
- 可生成包含家到目的地再回家的多日行程；
- 每一段路线可打开高德/百度或 Web 地图；
- 多人预算计算无浮点和分摊错误；
- 行程冲突可被规则引擎发现；
- 所有外部事实有来源或明确标记为估算；
- 模型或地图断网时不会丢失用户输入；
- 可以备份并在空环境恢复；
- 默认部署不暴露 API、数据库和模型服务端口；
- 不配置 crawler、百度、Ollama、LiteLLM 时系统仍可正常运行。

## 20. 最终推荐配置

首版最合理的组合：

```text
前端：React + TypeScript + Vite PWA
后端：Python + FastAPI + Pydantic
数据库：SQLite WAL
附件：本地 Docker Volume
模型：OpenAI-compatible Adapter → DeepSeek API
地图：高德 Web Service API
路线跳转：高德 URI，百度作为可选
任务：数据库状态 + 轻量后台 worker
OCR：首版服务端轻量 PP-OCR 子进程 + 用户确认；视觉模型按用户选择复核
部署：Docker Compose
远程访问：Tailscale/WireGuard 或 HTTPS 反向代理
```

不建议首版引入：

```text
Kubernetes、Redis、Kafka、向量数据库、完整 LiteLLM 网关、
完整 Langfuse、自动登录抓取平台、自动交易、多地图同时展示。
```

该方案能覆盖当前核心目标，又不会把个人工具做成难以维护的平台工程。

## 21. 下一步输出物

完成本设计确认后，建议按顺序产出：

1. `requirements.md`：用户故事、验收条件和非功能需求；
2. `architecture.md`：模块、数据流、错误与安全边界；
3. `data-model.md`：数据库实体和迁移策略；
4. `api-contract.yaml`：内部 REST/OpenAPI 契约；
5. `docker-compose.yml` 与 `.env.example`；
6. 可运行的 Web/API 骨架；
7. DeepSeek 与高德最小联调；
8. 第一条端到端旅行计划。
