# DD-10 需求追踪与差异分析

> 版本：1.0-draft
> 对比基线：[SRS 1.0-baseline](../software-requirements-specification.md)
> 覆盖口径：267 条 FR/NFR + DR-001～007 + AC-001～011

## 1. 追踪方法

需求按连续编号域映射到详细设计章节、主要接口/组件和验证方式。域内每一条编号都受该行覆盖；若某条需求需要特殊处理，在“关键差异/补充”中单列。最终实现阶段应把这些范围展开为测试管理系统中的逐条 Case ID。

状态定义：

- `Covered`：设计与验证路径均存在；
- `Partial`：有默认方案，但仍依赖 PoC/实现测量；
- `Deferred`：需求本身为 P1/P2/R，接口已预留但不进入首版；
- `Conflict`：设计与 SRS 行为冲突，必须修订；
- `Missing`：无设计承接。

## 2. 功能需求追踪

| 需求范围 | 数量 | 主要设计 | 主要验证 | 状态 |
|---|---:|---|---|---|
| FR-STATE-001～004 | 4 | DD-02 §7，DD-03 §9～16，DD-05 §3 | 版本/并发/Agent集成 | Covered |
| FR-AUTH-001～008 | 8 | DD-02 §4，DD-04 §5.1，DD-06 §3 | 认证、安全、恢复 E2E | Covered |
| FR-FAM-001～007 | 7 | DD-02 §4/6，DD-04 §5.2，DD-06 §4 | 权限矩阵、家庭 E2E | Covered |
| FR-MEM-001～006 | 6 | DD-02 §5，DD-04 §5.2，DD-05 §4.4 | 记忆确认/删除测试 | Covered |
| FR-TRIP-001～008 | 8 | DD-02 §6，DD-04 §5.3，DD-05 §4，DD-07 §4.2 | AC-001、Agent Eval | Covered |
| FR-PLAN-001～006 | 6 | DD-05 §4～5/11/12，DD-07 §4.3 | 多方案与导入 E2E | Covered |
| FR-EDIT-001～009 | 9 | DD-02 §7，DD-03 §3/9～16，DD-07 §4.4/6 | 拖动、Diff、冲突 E2E | Covered |
| FR-MAP-001～009 | 9 | DD-01 ADR-007，DD-02 §8，DD-04 §5.4/5.6，DD-07 §4.5/9 | 地图契约/移动 E2E | Covered；JS 真机 PoC |
| FR-ROUTE-001～010 | 10 | DD-02 §7.4/8.4，DD-05 §7/9，DD-07 §4.5 | AC-002、路线属性测试 | Covered |
| FR-POI-001～005 | 5 | DD-02 §8，DD-05 §7/11，DD-07 TripItem | POI Provider 契约 | Covered |
| FR-FOOD-001～006 | 6 | DD-02 Evidence/预算，DD-05 研究与预算，DD-07 §4.7 | 餐饮评估集/预算测试 | Covered |
| FR-HOTEL-001～007 | 7 | DD-02 Place/Order/Budget，DD-05 Plan/Route，DD-07 订单 | 酒店区域/确认/路线测试 | Covered |
| FR-WEA-001～005 | 5 | DD-02 WeatherObservation，DD-05 §4.3/9，DD-07 §4.1 | AC-006、Provider降级 | Covered |
| FR-PACE-001～005 | 5 | DD-05 计划骨架/审计，DD-07 创建/方案比较 | Agent Eval/规则测试 | Covered |
| FR-GUIDE-001～011 | 11 | DD-02 §8.3，DD-04 §5.6，DD-05 §11，DD-06 §8，DD-12；小红书专项 | 导入/检索/Claim/冲突/注入 Eval | P0 Covered；独立资料库已设计为P1；Worker Deferred |
| FR-LLM-001～016 | 16 | DD-01 ADR-005，DD-05 全文，DD-08 Usage | Model Adapter/Agent Eval | Covered；轻量路由待优势评估 |
| FR-OCR-001～007 | 7 | DD-02 ImportDraft/Attachment，DD-04 §5.8/8，DD-05 OCR，DD-06 §9 | OCR PoC、文件安全 E2E | Partial：质量/峰值 PoC |
| FR-BUD-001～014 | 14 | DD-02 §9，DD-04 §5.7，DD-05 BudgetCalculator，DD-07 §4.7 | AC-003、Property Test | Covered |
| FR-ORD-001～008 | 8 | DD-02 §10.1，DD-03 §7，DD-04 §5.8，DD-07 §4.8 | AC-004 | Covered |
| FR-EXP-001～008 | 8 | DD-02 §10.2，DD-03 §7.2，DD-04 §5.8，DD-07 §4.7 | AC-005、Property Test | Covered |
| FR-LIVE-001～009 | 9 | DD-03 Trip/Item，DD-05 §4.3，DD-07 §4.1/8 | AC-007、离线 E2E | Covered |
| FR-NOT-001～005 | 5 | DD-01 Notifications，DD-04 §5.9，DD-08 §6 | 调度/SMTP/ICS测试 | P0 Covered；ICS P1 Deferred |
| FR-LIST-001～004 | 4 | DD-04 §5.9，DD-05 Tool，DD-07 首页/离线 | 清单 E2E | Covered |
| FR-SAFE-001～004 | 4 | DD-04 §5.9，DD-05 safety 工具，DD-07 首页 | 应急离线/POI测试 | P0 Covered；海外 P2 Deferred |
| FR-SHARE-001～010 | 10 | DD-02 §12.1，DD-03 §8，DD-04 §5.10，DD-06 §10，DD-07 §4.9 | AC-008、安全 E2E | P0 Covered；公共库 P1 Deferred |
| FR-AUD-001～006 | 6 | DD-02 §13.1，DD-03 事务，DD-06 §11 | 审计完整性/隐私删除 | Covered |
| FR-IO-001～008 | 8 | DD-02 §12，DD-04 §5.11/8/9，DD-07 §4.9，DD-08 备份 | 导入导出/恢复 E2E | P0 Covered；ICS P1 Deferred |
| FR-ADM-001～006 | 6 | DD-04 §5.11，DD-06 Secret，DD-07 §4.10，DD-08 §5/9/10 | 管理端 E2E | Covered |
| FR-BACK-001～009 | 9 | DD-04 管理接口，DD-06 §12，DD-08 §11/12 | AC-010、迁移恢复 | Covered |

功能需求计数合计：220。

## 3. 非功能需求追踪

| 需求范围 | 数量 | 主要设计 | 验证 | 状态 |
|---|---:|---|---|---|
| NFR-PERF-001～012 | 12 | DD-01 部署/并发，DD-08 §6/7，DD-09 §9 | AC-011 AMD64 门 | Partial：必须实测 |
| NFR-AVL-001～005 | 5 | DD-03 错误恢复，DD-05 Provider降级，DD-08 §13 | AC-009、故障注入 | Covered |
| NFR-SEC-001～010 | 10 | DD-06 全文，DD-08 部署，DD-09 §8 | 安全发布门 | Covered |
| NFR-PRI-001～005 | 5 | DD-02 删除，DD-05 Context，DD-06 §4/10/13 | 隐私/分享/删除 E2E | Covered |
| NFR-DEP-001～006 | 6 | DD-01/08，DD-07 浏览器/PWA | 多浏览器/Compose测试 | Covered；真机矩阵待执行 |
| NFR-UX-001～004 | 4 | DD-07 全文 | 移动/无障碍 E2E | Covered |
| NFR-MNT-001～005 | 5 | DD-01 ADR/模块，DD-04 兼容，DD-08 升级 | 架构/许可证/升级门 | Covered；发布前许可证复核 |

非功能需求计数合计：47。功能 220 + 非功能 47 = 267，与 SRS 唯一 ID 自动提取结果一致。

## 4. 数据需求追踪

| 需求 | 设计 | 验证 | 状态 |
|---|---|---|---|
| DR-001 稳定 ID | DD-02 §1 | ID/外部引用测试 | Covered |
| DR-002 UTC/时区 | DD-02 §1/7 | 跨日/时区测试 | Covered |
| DR-003 金额精度 | DD-02 §1/9/10 | Property Test | Covered |
| DR-004 坐标系 | DD-02 §8，DD-01 ADR-007 | 坐标契约测试 | Covered |
| DR-005 附件 | DD-02 §12.2，DD-04 §8，DD-06 §9 | 文件/加密测试 | Covered |
| DR-006 来源时间 | DD-02 §8/9 | Evidence/Provider测试 | Covered |
| DR-007 乐观锁 | DD-02 §6，DD-03 §11 | 并发测试 | Covered |

## 5. 验收场景追踪

AC-001～AC-011 已在 DD-09 §11 逐项映射。设计覆盖：家庭创建、全过程路线、多人预算、订单导入、消费退款、天气建议、行中调整、公开分享、外部断开、备份恢复和性能。

## 6. 原始规约与详细设计对比

### 6.1 已保持一致的关键口径

| 原始规约 | 详细设计响应 |
|---|---|
| DB 是唯一事实，聊天不是 | Context 每次读取最新版本；聊天仅作意图摘要 |
| AI 修改需确认 | Proposal/Patch 两阶段提交；应用命令最终校验 |
| 所有变动留历史 | Version + Audit + Outbox 同事务 |
| 高德主、百度补充 | 页面/主路线高德，Provider 端口允许百度验证/跳转 |
| 天气不擅自大改 | 默认提示/备选，用户明确授权才重排 |
| 订单不下单 | 只读导入、匹配、归档，不接支付/交易 |
| 消费保留原值 | 追加更正/冲销链，无覆盖金额 API |
| 小红书 P0 用户导入 | P1/R 可选只读 Worker，主链路不依赖 |
| 远程 MCP 管理员添加 | 家庭管理员仅启用已批准工具 |
| 公开内容独立脱敏副本 | Public DTO 白名单、二次确认、不自动更新 |
| 移动端友好 | 四主入口、旅行工作区、行中首页、离线包 |
| 空闲 <512 MB/峰值 <2 GB | 两常驻容器、重任务串行、目标环境实测门 |

### 6.2 设计澄清，不改变需求

- 访客细分为“登录家庭访客”和“匿名分享访问”，权限仍符合三角色首版要求；
- TripItem 的喜好标签与执行状态拆分，解决“必去/已完成”混在一个 Enum 的歧义；
- 历史恢复创建新版本，不倒转版本号；
- 订单当前视图由不可变事件投影，便于查询但不丢事实；
- DeepSeek 费用只统计/告警，其他 Provider 可硬限额；
- 高德/百度“导入”首版定义为可点击导航/地点链接，不声称存在未验证的整程导入 API；
- 百度 Server SK 仅在所选服务明确需要签名时配置，不作为通用必填项。

### 6.3 仍需 PoC、但不阻塞编码骨架

| 项目 | 设计默认 | Go/No-Go |
|---|---|---|
| 高德 JS 真机 | 高德页面地图 | iOS/Android Key/域名/手势通过；失败保留文本和外链 |
| PP-OCR | 轻量子进程并发 1 | 质量可确认、主服务不 OOM、总峰值 <2 GB |
| Chromium PDF | HTML 模板受控打印 | 30 天文档峰值达标；否则换轻量渲染器 |
| 自有 Runtime | 自有状态图 | 恢复/取消/内存优于或不差于候选框架 |
| 可选小红书 Worker | 默认关闭 Profile | 只读、安全、会话、资源和维护成本通过专项门 |
| 轻量模型路由 | 未配置则主模型 | 固定评估集证明节省且无显著质量下降 |

## 7. 当前发现的差异

### GAP-001：人工需求总数初次加总错误

- 现象：本文件初稿误写功能需求合计为 235，导致总数误写为 282；
- 校验：机器从 SRS 定义行提取 220 个 FR、47 个 NFR，共 267 个唯一 ID，无重复；
- 处理：已修正人工合计，不改变任何需求正文或范围；
- 状态：Closed。

### GAP-002：文件上限曾出现设计偏差

- 现象：DD-04 初稿曾写图片/订单更小的不同上限；
- SRS 基线：单图 20 MB、单 PDF 50 MB、单次 20 文件、家庭 20 GB；
- 处理：DD-04 已修正为 SRS 基线；
- 状态：Closed。

### GAP-003：许可证最终批准时点

- SRS：发布前单独决定，候选 Apache-2.0/AGPL-3.0；准入复核将 Apache-2.0 作为设计基线；
- 设计：ADR-012 标为“暂定接受”，发布前第三方许可证复核；
- 状态：Covered，不阻塞详细设计；发布门仍需正式批准。

## 8. 追踪检查规则

最终校验必须以正则提取 SRS 中唯一的 `FR-*`/`NFR-*` ID：

1. ID 无重复；
2. 每个前缀在本矩阵只有一个连续覆盖范围；
3. 范围首尾和实际 ID 一致，无空洞；
4. 需求总数由工具计算，不手工硬编码推断；
5. AC-001～011 和 DR-001～007 均出现；
6. 所有 `Partial` 项有 PoC 和失败降级；
7. 不允许 `Conflict` 或 `Missing` 进入设计批准。

## 9. 当前准出判断

架构、数据、事务、API、Agent、安全、移动端和运维均已形成实施契约；没有发现产品行为冲突。需求计数已经关闭校验，仍需完成全部文档的链接、术语、状态和需求覆盖检查，并把结果写入 DD-11。在最终复核完成前，本文件保持 `1.0-draft`。
