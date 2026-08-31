# 外部 API Key 申请与接入验证清单

> 状态：接入准备 v0.1
> 日期：2026-08-30
> 目标：在冻结领域 Schema 和 OpenAPI 契约前，使用真实测试凭据确认认证方式、字段、配额、模型工具能力和资源占用。

## 1. 是否需要先准备 API Key

需要。

公开文档只能确认“平台声明支持什么”，不能确认当前个人账号实际获得的配额、字段、认证方式和权限。尤其是地图收费字段、POI 详情、天气 API Host、模型 Tool Calls、结构化输出和 MCP 工具列表，都应当先通过真实测试固化 fixture，再进入最终接口契约。

正确顺序：

```text
整理申请入口和变量
  → 申请最小测试凭据
  → 本机 .env 配置
  → Provider 能力探测
  → 保存脱敏原始响应 fixture
  → 确认字段映射和降级规则
  → 冻结 JSON Schema/OpenAPI
  → 开始业务开发
```

## 2. 密钥保存规则

仓库提供 [`.env.example`](../.env.example)，但真实 Key 只能写入本机 `.env`：

```bash
cp .env.example .env
```

然后使用本机编辑器填写 `.env`。

禁止：

- 不把真实 Key 写入 Markdown、Issue、聊天记录或测试报告；
- 不提交 `.env`、PEM 私钥、截图中的完整 Key；
- 不把服务端 Key 放进前端 JavaScript；
- 不在日志中打印 Authorization Header 或带 Key 的完整 URL；
- 不用生产 Key 跑自动化测试；
- 不把同一个 Key 跨开发、测试和正式环境长期复用。

如果密钥曾经出现在 Git、聊天或公开日志中，应立即在平台控制台撤销并重新生成，而不是只删除文本。

## 3. 第一批必须申请

第一批只覆盖“模型生成 + 地点/路线 + 地图展示 + 天气”的闭环。

### 3.1 DeepSeek API

- 申请/控制台：[DeepSeek 开放平台](https://platform.deepseek.com/)
- API 文档：[DeepSeek API Docs](https://api-docs.deepseek.com/)
- 环境变量：
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_BASE_URL=https://api.deepseek.com`
  - `DEEPSEEK_MODEL`：从当前控制台/模型文档复制，不在代码中猜测
- 初始权限：普通 Chat、Tool Calls、流式；如账号支持，再测试 Responses。
- 费用控制：首次充值只需满足少量能力测试；设置单次输出和工具次数上限。

验证项目：

- 普通非流式回复；
- SSE 流式回复；
- JSON Object；
- 单个 Tool Call；
- 多个并行 Tool Calls；
- Thinking + Tool Calls 上下文回传；
- 非法工具参数是否会出现；
- 超时、429、余额不足和无效模型错误格式；
- token usage、request ID 和结束原因字段。

### 3.2 高德 Web Service Key

- 申请说明：[高德创建 Web Service 应用和 Key](https://lbs.amap.com/api/webservice/create-project-and-key)
- 控制台：[高德开放平台](https://console.amap.com/)
- Key 类型：`Web服务`
- 环境变量：`AMAP_WEB_SERVICE_KEY`
- 如果启用高德 MCP：可先把同一测试 Key 写入 `AMAP_MCP_KEY`；后续建议独立轮换。

验证项目：

- 地理编码/逆地理编码；
- POI 关键词搜索和周边搜索；
- POI 详情字段；
- 驾车、公交、步行路线；
- 驾车收费、公交价格、出租车估价等字段是否对当前账号返回；
- 路线 2.0 的 GET/POST 行为；
- 无结果、参数错误、配额耗尽和无效 Key；
- 当前账号调用量限制与服务条款。

注意：高德服务协议对数据缓存、展示方式、测试用途和许可有要求。PoC 可以保存脱敏 fixture 用于字段测试，但正式数据保留策略必须再次审查[高德服务协议](https://lbs.amap.com/pages/terms/)。

### 3.3 高德 JS API Key 与安全密钥

- 申请说明：[高德 JS API 2.0 快速上手](https://lbs.amap.com/api/javascript-api-v2/getting-started)
- Key 类型：`Web端(JS API)`
- 环境变量：
  - `AMAP_JS_API_KEY`
  - `AMAP_JS_SECURITY_KEY`
- 限制：配置本机和测试域名白名单；正式域名之后单独配置。

Web Service Key 和 JS API Key 是不同类型，不能只申请一个然后同时用于前后端。

验证项目：

- 手机宽度地图加载；
- 多日标记点和路线绘制；
- 地点卡片与地图联动；
- 安全密钥配置；
- 域名白名单；
- 高德 App 导航、打车和专属地图链接是否能在测试手机打开。

### 3.4 和风天气

- 申请说明：[和风天气 Project 与 Credential](https://dev.qweather.com/en/docs/configuration/project-and-key/)
- 认证说明：[和风天气 Authentication](https://dev.qweather.com/en/docs/configuration/authentication/)
- 控制台：[QWeather Console](https://console.qweather.com/)
- 环境变量：
  - 快速 PoC：`QWEATHER_API_HOST`、`QWEATHER_API_KEY`
  - 目标 JWT：`QWEATHER_PROJECT_ID`、`QWEATHER_CREDENTIAL_ID`、`QWEATHER_PRIVATE_KEY_FILE`

平台会分配 API Host，必须从控制台复制，不能假设公共固定 Host。快速 PoC 可以先使用 API Key；目标实现使用 Ed25519 JWT。私钥文件放入 `./secrets/`，不要把 PEM 内容直接写进 `.env`。

验证项目：

- 当前天气；
- 小时和每日预报；
- 预警更新、取消、过期；
- 空气质量；
- 本地时间和 UTC；
- 中文语言参数；
- attribution 字段的展示要求；
- 当前套餐允许的天数、分辨率和每日请求量。

## 4. 第二批可选申请

第一批通过后再申请，避免干扰核心定位。

### 4.1 百度地图

- 开放平台：[百度地图开放平台](https://lbsyun.baidu.com/)
- Web API 总览：[百度 Web API](https://lbsyun.baidu.com/faq/api?title=webapi)
- 环境变量：
  - `BAIDU_MAP_SERVER_AK`
  - `BAIDU_MAP_SERVER_SK`（仅在所选认证方式要求时填写）
  - `BAIDU_MAP_JS_AK`

服务端和浏览器端分别创建应用。首版只用于 POI 补充、路线影子校验和百度地图跳转，不作为主地图。

### 4.2 百度 OCR

- 产品文档：[百度 OCR](https://ai.baidu.com/ai-doc/index/OCR)
- 控制台：[百度智能云控制台](https://console.bce.baidu.com/ai/)
- 环境变量：`BAIDU_OCR_API_KEY`、`BAIDU_OCR_SECRET_KEY`

本地 PaddleOCR 不需要 Key。只有在本地识别效果不足且用户允许上传图片时，才测试百度 OCR。

### 4.3 Firecrawl

- 官网/控制台：[Firecrawl](https://www.firecrawl.dev/)
- API 文档：[Firecrawl v2](https://docs.firecrawl.dev/api-reference/v2-introduction)
- 环境变量：`FIRECRAWL_API_KEY`、`FIRECRAWL_BASE_URL`

用于网页搜索、抓取和结构化提取。它不能授权系统绕过目标网站登录、验证码、访问控制或服务条款。

### 4.4 其他模型

只有在 DeepSeek 的首轮测试完成后再申请，用于兼容性对照：

- OpenAI：`OPENAI_API_KEY`、`OPENAI_MODEL`
- Anthropic：`ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL`
- Gemini：`GEMINI_API_KEY`、`GEMINI_MODEL`
- 任意兼容平台：`OPENAI_COMPAT_API_KEY`、`OPENAI_COMPAT_BASE_URL`、`OPENAI_COMPAT_MODEL`

至少选择一个与 DeepSeek 不同的 Provider 做对照，才能验证自有 `ModelProvider` 是否真的解耦。

## 5. 暂时不要申请

以下平台目前不属于个人自托管 PoC 的必要条件：

- 携程、飞猪、美团合作型 OpenAPI；
- 12306 非公开接口；
- 航司、酒店和门票下单接口；
- 支付接口；
- 短信商业通道。

这些平台需要商务、企业资质或特定业务合作时，再按 Adapter 接入；现在申请会拖慢核心验证。

## 6. `.env` 变量分级

| 分组 | 最小必填 | 可选 |
|---|---|---|
| 模型 | DeepSeek Key、Base URL、Model | OpenAI/Anthropic/Gemini |
| 地图后端 | 高德 Web Service Key | 百度 Server AK |
| 地图前端 | 高德 JS Key、安全密钥 | 百度 JS AK |
| 天气 | 和风 Key/API Host，或只用高德天气 | 和风 JWT |
| OCR | 无，本地 PaddleOCR | 百度 OCR |
| 网页 | 无，静态 HTTP | Firecrawl、Playwright |
| 通知 | 无 | SMTP |

## 7. 凭据就绪检查

在运行联网测试前逐项确认：

- [ ] `.env` 已从 `.env.example` 复制；
- [ ] `.env` 被 `.gitignore` 忽略；
- [ ] 未把真实 Key 发到聊天或文档；
- [ ] 高德 Web Service 与 JS API Key 类型正确；
- [ ] JS Key 配置了测试域名白名单；
- [ ] 和风 API Host 来自控制台；
- [ ] DeepSeek Model ID 来自当前官方控制台/文档；
- [ ] 所有 Key 都是测试用途，可随时撤销；
- [ ] Provider 控制台设置了配额或余额提醒；
- [ ] `INTEGRATION_TEST_LIVE=true` 只在明确运行联网测试时启用。

## 8. 测试输出规范

测试不能只打印“成功”。每项测试生成：

```json
{
  "provider": "amap",
  "operation": "route.driving",
  "tested_at": "2026-08-30T10:00:00+08:00",
  "status": "passed",
  "latency_ms": 230,
  "http_status": 200,
  "provider_code": "10000",
  "schema_hash": "sha256:...",
  "fields_present": ["distance", "duration"],
  "fields_missing": ["tolls"],
  "raw_fixture": "data/integration-fixtures/amap/route-driving.json",
  "secrets_redacted": true,
  "notes": []
}
```

原始 fixture 保存前必须移除：Key、Authorization、手机号、订单号、精确家庭地址和个人身份信息。

## 9. 何时可以进入接口契约阶段

满足以下条件后再冻结 Schema：

1. DeepSeek 普通、流式、结构化和工具调用测试通过；
2. 高德地点、驾车、公交、步行至少各有一个真实 fixture；
3. 高德 JS API 在手机浏览器完成一次加载和交互；
4. 天气主来源或高德降级来源测试通过；
5. 外部错误格式和配额错误至少各保存一个样例；
6. 已确认哪些第三方字段不能稳定获得；
7. ModelProvider 和 ProviderAdapter 的字段映射没有依赖真实 Key；
8. 联网测试期间的资源峰值仍满足 2 GB 上限。

这些验证完成后，再生成正式 JSON Schema、OpenAPI 和智能体节点契约，可以显著减少后续返工。
