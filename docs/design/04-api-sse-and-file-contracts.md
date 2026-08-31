# DD-04 REST、SSE 与文件接口契约

> 版本：1.0-draft
> 协议：HTTPS + JSON REST + HTTP SSE
> 描述标准：OpenAPI 3.1.1、JSON Schema 2020-12

## 1. 通用约定

- API 前缀：`/api/v1`；健康端点不带版本；
- JSON 字段使用 `snake_case`，时间使用带 `Z` 的 RFC 3339 UTC 字符串；
- 本地日期 `YYYY-MM-DD` 与本地时间 `HH:mm` 必须同时携带 `timezone`；
- ID 是不透明 UUIDv7 字符串；金额为 `{amount_minor,currency}`；
- 写请求使用 `Content-Type: application/json`，上传使用分段上传接口；
- 返回 `X-Request-Id`；客户端可传同名请求 ID；
- 旅行写请求必须传 `If-Match: "trip-{version}"` 或正文 `expected_version`；
- 可重试写请求必须传 `Idempotency-Key`；
- 列表默认游标分页，不使用页码处理可变时间线；
- 所有用户可见文案提供稳定 `message_key`，首版服务端返回简体中文默认消息。

## 2. 认证与浏览器安全

浏览器登录使用 `HttpOnly; Secure; SameSite=Lax` Session Cookie。改变状态的请求还需 `X-CSRF-Token`，令牌由受保护的 `/auth/session` 返回。API Key 仅供未来 CLI/自动化，首版管理页不生成长期 Bearer Token。

公开分享使用随机高熵路径 Token；密码单独提交并换取短期分享 Session Cookie，禁止把密码放 URL。

## 3. 响应封装

单资源成功：

```json
{
  "data": {},
  "meta": {"request_id": "019...", "trip_version": 13}
}
```

列表成功：

```json
{
  "data": [],
  "meta": {"request_id": "019...", "next_cursor": "opaque", "has_more": true}
}
```

错误使用 `application/problem+json`：

```json
{
  "type": "https://travel-agent.local/problems/version-conflict",
  "title": "行程版本冲突",
  "status": 409,
  "code": "trip_version_conflict",
  "detail": "当前行程已被其他修改更新。",
  "instance": "/api/v1/trips/019.../proposals/019.../apply",
  "request_id": "019...",
  "errors": [{"path": "expected_version", "code": "stale", "message": "期望 12，当前 13"}],
  "current_trip_version": 13,
  "retryable": false
}
```

敏感错误不得回显上游响应、文件路径、SQL、Prompt 或凭据。

## 4. 状态码

| 状态 | 用途 |
|---|---|
| 200 | 查询或同步命令成功 |
| 201 | 资源创建成功 |
| 202 | 后台任务已接受，返回 Job/Run |
| 204 | 无正文成功 |
| 400 | 语法/请求格式错误 |
| 401 | 未登录或 Session 失效 |
| 403 | 已识别但权限不足 |
| 404 | 不存在，或为防枚举对无权主体隐藏 |
| 409 | 版本、幂等键、状态冲突 |
| 413 | 文件或请求过大 |
| 415 | 不支持的文件/MIME |
| 422 | Schema 或业务规则不满足 |
| 429 | 用户/Provider 配额或限流 |
| 503 | 临时不可用、写锁超时或关键依赖维护 |

## 5. 资源端点

### 5.1 初始化与认证

| 方法与路径 | 作用 | 权限 |
|---|---|---|
| `GET /setup/status` | 是否首次初始化 | 匿名，仅布尔状态 |
| `POST /setup/initialize` | 创建首位管理员并返回一次性恢复码 | 仅未初始化实例 |
| `POST /auth/login` | 密码登录 | 匿名 |
| `POST /auth/logout` | 撤销当前 Session | 登录用户 |
| `GET /auth/session` | 当前用户、CSRF、家庭上下文 | 登录用户 |
| `POST /auth/password/change` | 修改密码并递增 Session epoch | 登录用户 |
| `POST /auth/password/reset-request` | SMTP 或管理员流程 | 匿名、限流 |
| `POST /auth/recovery/admin` | 使用恢复码恢复管理员 | 物理部署持有者、强限流 |

恢复码只在初始化响应展示一次；服务端只存验证哈希。

### 5.2 家庭、成员与偏好

```text
GET/POST       /families
GET/PATCH      /families/{family_id}
GET/POST       /families/{family_id}/members
PATCH          /families/{family_id}/members/{membership_id}/role
DELETE         /families/{family_id}/members/{membership_id}
PUT            /families/{family_id}/members/{membership_id}/profile
POST           /families/{family_id}/invites
DELETE         /families/{family_id}/invites/{invite_id}
POST           /family-invites/accept
POST           /family-invites/register
GET/POST       /families/{family_id}/member-profiles
GET/PATCH      /member-profiles/{profile_id}
GET/POST       /preferences?scope_type=&scope_id=
PATCH/DELETE   /preferences/{preference_id}
GET            /users/me/memories
POST           /memory-suggestions/{id}/accept
POST           /memory-suggestions/{id}/reject
PATCH/DELETE   /users/me/memories/{id}
```

当前轻量实现将可复用旅行档案按家庭成员关系保存，并通过
`PUT /families/{family_id}/members/{membership_id}/profile` 携带 `expected_version`
执行乐观锁更新。后续独立 `member-profiles` 资源用于同一账号在家庭内维护多个旅行画像时扩展，
不得破坏当前成员档案契约。

家庭邀请默认为带有效期的单次令牌。原始邀请码只在创建响应中返回一次，数据库只保存摘要。
为避免邀请码进入反向代理访问日志，接受和受邀注册接口通过 JSON 请求体传递 `code`，
移动端分享链接将邀请码放在 URL Fragment 中。受邀注册不等同于开放公共注册；没有有效邀请码时
不得创建账号。

### 5.3 Trip、需求和参与者

| 方法与路径 | 说明 |
|---|---|
| `GET /trips` | 按权限返回旅行摘要 |
| `POST /trips` | 表单或自然语言创建 Draft |
| `GET /trips/{trip_id}` | 当前摘要、版本和可用动作 |
| `PATCH /trips/{trip_id}` | 标题、可见性等元数据；需版本 |
| `DELETE /trips/{trip_id}` | 软删除；彻底删除走独立 Job |
| `GET/PATCH /trips/{trip_id}/requirements` | 当前需求与约束确认 |
| `GET/POST /trips/{trip_id}/participants` | 旅行时点成员快照 |
| `PATCH/DELETE /trips/{trip_id}/participants/{id}` | 修改参与人 |
| `POST /trips/{trip_id}/start` | 进入行中模式 |
| `POST /trips/{trip_id}/complete` | 完成并触发复盘建议 |

`POST /trips` 支持 `input_mode=form|chat|import`，服务端先形成 Draft，不因自然语言创建而直接生成正式计划。

### 5.4 行程、地图编辑和版本

```text
GET    /trips/{trip_id}/itinerary
GET    /trips/{trip_id}/days/{date}
POST   /trips/{trip_id}/commands/add-item
POST   /trips/{trip_id}/commands/update-item
POST   /trips/{trip_id}/commands/move-item
POST   /trips/{trip_id}/commands/remove-item
POST   /trips/{trip_id}/commands/set-item-status
POST   /trips/{trip_id}/commands/set-locks
POST   /trips/{trip_id}/commands/move-marker-preview
GET    /trips/{trip_id}/versions
GET    /trips/{trip_id}/versions/{version_no}
GET    /trips/{trip_id}/versions/{from}/diff/{to}
POST   /trips/{trip_id}/versions/{version_no}/restore-preview
POST   /trips/{trip_id}/versions/{version_no}/restore
```

地图拖动先调用 `move-marker-preview`，返回新 POI 绑定候选、受影响路线/时间/预算和 `preview_token`；确认时提交 Token 与 expected version。Token 与输入哈希绑定且短期有效。

### 5.5 规划、对话与 Proposal

| 方法与路径 | 说明 |
|---|---|
| `POST /trips/{id}/planning-runs` | `initial/local_edit/global_replan/live_adjust/review` |
| `GET /planning-runs/{run_id}` | 状态、节点、进度、等待问题 |
| `POST /planning-runs/{run_id}/messages` | 回答澄清或补充用户指令 |
| `POST /planning-runs/{run_id}/cancel` | 协作式取消 |
| `POST /planning-runs/{run_id}/retry` | 从安全检查点重试 |
| `GET /trips/{id}/proposals` | 提案列表 |
| `GET /proposals/{proposal_id}` | Patch、Diff、质量、来源 |
| `POST /proposals/{proposal_id}/apply` | 用户确认并应用 |
| `POST /proposals/{proposal_id}/reject` | 拒绝并可附反馈 |
| `POST /proposals/{proposal_id}/rebase` | 基于当前版本重算 |

对话消息保存用户原文，但模型输入由服务端重新构造当前快照。消息接口不能成为直接修改 Trip 的后门。

### 5.6 地图、路线、天气和研究

```text
GET  /places/search?q=&city=&provider=
GET  /places/{place_id}
POST /places/resolve
POST /routes/quote
GET  /trips/{trip_id}/route-map?date=
GET  /weather?place_id=&start=&end=
POST /trips/{trip_id}/guide-sources
GET  /trips/{trip_id}/guide-sources
POST /guide-sources/{id}/extract
GET  /trips/{trip_id}/evidence
GET  /evidence/{id}
```

服务端返回内部 Place/Route/Evidence，不透传供应商原始 JSON。外部导航链接由 `/map-links` 根据用户选择即时生成，链接参数脱敏。

### 5.7 预算

```text
GET  /trips/{trip_id}/budgets/current
POST /trips/{trip_id}/budgets/recalculate
POST /trips/{trip_id}/budget-items
PATCH/DELETE /budget-items/{id}
GET  /trips/{trip_id}/budget-comparison
GET/POST /families/{id}/exchange-rates
```

重算若超过同步阈值返回 202 Job。响应必须分别展示估算、报价、订单和实际消费，不只返回总数。

### 5.8 订单、OCR 与消费

```text
POST /trips/{trip_id}/imports                 创建导入会话
POST /imports/{id}/files                      分段/单文件上传
POST /imports/{id}/analyze                    启动 OCR/解析
GET  /imports/{id}                            草稿与候选匹配
POST /imports/{id}/confirm                    用户确认后生成正式对象
GET  /trips/{trip_id}/orders
GET  /orders/{id}
POST /orders/{id}/events                      变更/取消/退款
POST /orders/{id}/rematch-preview
POST /orders/{id}/rematch
GET/POST /trips/{trip_id}/expenses
GET /expenses/{id}
POST /expenses/{id}/correct
POST /expenses/{id}/reverse
GET /trips/{trip_id}/expense-report
```

禁止 `PATCH /expenses/{id}/amount` 和覆盖订单原始事件的接口。

### 5.9 清单、提醒和应急

```text
GET/POST/PATCH /trips/{id}/checklists...
GET/POST/PATCH /trips/{id}/reminders...
GET/PATCH      /users/me/notification-preferences
GET            /trips/{id}/emergency-info
POST           /trips/{id}/nearby-safety-search
```

### 5.10 分享和公共库

```text
POST /trips/{id}/share-previews
GET  /share-previews/{id}
POST /share-previews/{id}/publish
GET  /trips/{id}/shares
POST /shares/{id}/revoke
GET  /public/shares/{token}
POST /public/shares/{token}/unlock
POST /public/shares/{token}/copy
POST /public/shares/{token}/comments
GET  /public/trips                     P1
POST /public/shares/{token}/reports    P1
```

公开响应 Schema 与私有 Trip DTO 分离，避免序列化器配置错误泄漏字段。

### 5.11 导入导出、任务和管理

```text
POST /trips/{id}/exports
GET  /exports/{id}
GET  /exports/{id}/download
GET  /jobs/{id}
POST /jobs/{id}/cancel
GET  /admin/status
GET/PATCH /admin/settings/{section}
POST /admin/providers/{id}/probe
GET  /admin/usage
GET  /admin/audit-events
POST /admin/backups
GET  /admin/backups
POST /admin/backups/{id}/verify
POST /admin/restores/validate
POST /admin/restores
GET  /admin/updates
POST /admin/updates/{version}/prepare
```

恢复和更新执行前必须返回影响预览并使用一次性确认 Token，不接受一个普通布尔 `confirm=true`。

## 6. 查询投影 DTO

API 不把数据库模型直接序列化。核心 DTO 分为：

- `TripSummary`：列表轻量字段；
- `TripWorkspace`：当前版本、权限、当天概况、待确认项；
- `ItineraryDayView`：一天项目、交通段和地图数据；
- `ProposalDetail`：影响摘要、分组 Diff、来源和质量报告；
- `BudgetReport`：计划/订单/实际四层价格；
- `LiveTripView`：今日、下一项、关键票据、提醒、离线版本；
- `PublicTripView`：仅脱敏白名单字段。

所有 DTO 含 `schema_version`，导出 JSON 使用独立、长期兼容的 Export Schema。

## 7. SSE 协议

连接：`GET /api/v1/events?trip_id=&run_id=`。浏览器使用 Session Cookie；服务端验证资源权限。`Last-Event-ID` 用于短期重连，事件缓冲默认 15 分钟或 1000 条。

```text
id: 019...
event: planning.node.completed
retry: 3000
data: {"schema_version":"sse/1.0","run_id":"...","sequence":8,"occurred_at":"...","payload":{...}}
```

事件类型：

| 事件 | 内容 |
|---|---|
| `planning.run.started/completed/failed` | Run 生命周期 |
| `planning.node.started/completed` | 用户可理解的阶段与进度 |
| `planning.text.delta` | 可选解释文本增量，不含隐式思维链 |
| `planning.tool.started/completed` | 仅显示工具类别、来源和状态 |
| `planning.waiting_user` | 澄清问题或需要确认的条件 |
| `proposal.ready/conflict/applied` | 提案状态 |
| `trip.version.created` | 新版本号及摘要 |
| `job.progress/completed/failed` | OCR、PDF、备份等任务 |
| `notification.created` | 站内提醒 |
| `heartbeat` | 15～30 秒保活 |

SSE 不是事实存储。断线且缓冲失效时返回 `event_gap`，客户端重新 GET Run/Trip 当前状态。事件载荷不含 API Key、完整 Prompt、Cookie、健康信息、订单号、票据正文和模型隐式推理。

## 8. 文件接口

### 8.1 允许类型与默认上限

| 用途 | 类型 | 单文件上限 |
|---|---|---|
| 图片（攻略/计划/订单/票据） | PNG、JPEG、WebP | 20 MB |
| PDF（攻略/计划/订单/票据） | PDF | 50 MB |
| JSON 导入 | `application/json` | 20 MB |
| 加密全量归档 | 专用归档 MIME | 管理员配置 |

单次默认最多 20 个文件、家庭存储默认 20 GB，均可由管理员配置。仅依据扩展名不可信；服务端检查魔数、MIME、页数、像素和解压膨胀比例。SVG、HTML、可执行文件和嵌入脚本默认拒绝。PDF 在隔离子进程解析。

### 8.2 上传流程

1. 创建 Import Session，返回限制和上传 ID；
2. 上传到随机临时路径并边写边计算哈希；
3. 验证 MIME/大小/重复；
4. 加密并登记 Attachment；
5. 启动解析 Job；
6. 返回结构化 Draft；
7. 用户确认后写正式对象；
8. 删除临时明文和 OCR 中间文件。

下载使用鉴权端点流式解密，响应带 `Content-Disposition`、`nosniff`、私有缓存头。公开分享只访问重新生成的脱敏 Artifact。

## 9. OpenAPI 与兼容性

- 源 OpenAPI 由 FastAPI 生成后经契约测试冻结到 `packages/contracts/openapi.json`；
- 前端类型由冻结契约生成，禁止手写重复 DTO；
- 非破坏性新增字段允许，客户端必须忽略未知字段；
- 删除/重命名/改变语义必须进入 `/v2` 或保留兼容适配期；
- Enum 增加值对客户端可能是破坏性变更，UI 必须提供 unknown fallback；
- JSON 导出 Schema 需要迁移器，至少支持当前和前两个主要版本。

## 10. 接口验收

- OpenAPI 通过 3.1 校验，示例通过 JSON Schema；
- 401/403/404 行为防止资源枚举；
- 所有 Trip 写端点验证版本和幂等；
- 所有文件经过格式、权限和路径测试；
- SSE 断线、重连、事件缺口和权限撤销测试通过；
- 公开 DTO 的敏感字段快照测试为零泄漏；
- 订单和消费不存在原地覆盖金额的接口。
