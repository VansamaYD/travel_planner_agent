# 旅游规划智能体详细流程规格

> 文档状态：1.0 需求基线，待设计阶段落实接口与PoC
> 日期：2026-08-30
> 适用范围：首版自托管、小规模多用户、移动端优先系统

配套图示见：[旅游规划智能体工作流图](./agent-workflow-diagrams.md)。系统端到端运行位置见：[系统运行流程与设计阶段准入复核](./system-runtime-flow-and-design-readiness-review.md)。

## 1. 设计目标

智能体系统的核心不是“让模型自由聊天并不断调用工具”，而是把旅行规划拆成可恢复、可验证、可局部重算的工作流。首版需要同时满足：

- **高质量**：硬约束零违反、路线可执行、预算算术正确、关键事实有来源、修改不越界；
- **高效率**：减少重复模型上下文、重复 POI 搜索和全量路线计算，优先批量、缓存和局部重算；
- **可控自治**：只读研究可以自动执行，改变行程、订单、消费和记忆必须经过业务规则与用户确认；
- **可恢复**：进程退出、网络失败、用户稍后继续时能够从检查点恢复；
- **可解释**：用户能看见假设、来源、冲突、方案差异和调整原因；
- **可扩展**：同一流程兼容 DeepSeek 和其他模型，兼容 REST、MCP 和本地工具；
- **低资源**：所有角色运行在一个应用进程的编排体系内，不常驻多个 Agent 服务。

非目标：

- 不构建彼此自由对话的多 Agent 群；
- 不让模型直接写数据库、执行 SQL、下单、支付或删除数据；
- 不保存或展示模型隐藏思维链；
- 不为了“反思”无限循环；
- 不要求一次模型调用生成最终可执行的完整旅行。

## 2. 总体架构决策

### 2.1 单编排器、逻辑多角色

系统采用一个持久化 Workflow Orchestrator。Intake、Research、Designer、Critic 等是节点级角色和提示词模板，不是独立进程，也不默认使用不同模型。

```text
用户/前端
  → Application Service
  → Workflow Orchestrator
      ├─ LLM Nodes：理解、候选生成、证据综合、定向修复、解释
      ├─ Tool Nodes：地图、天气、攻略、订单读取
      ├─ Solver Nodes：时间、路线、预算、约束、依赖图
      └─ Approval Nodes：等待确认、提交、版本冲突处理
  → Transactional Repository
  → SSE/移动端卡片与地图
```

采用这种设计的原因：

- 旅行计划包含大量确定性时间和金额计算，Agent 间自然语言传递会损失结构；
- 单状态图更容易实现版本、检查点、取消、恢复和审计；
- 同一个 DeepSeek 模型可按节点使用不同 Schema、温度和上下文，不需要多份常驻资源；
- 专业节点可以以后替换为更适合的模型或算法，不改变主流程契约。

### 2.2 确定性外壳

模型只产生候选或提案。以下结果必须由程序确定：

- 权限、用户作用域、密钥作用域；
- 日期、时区、时间加减、日界线；
- 金额、人数、票种、房间、车辆、舍入与分摊；
- 坐标转换、距离和路线字段归一化；
- 硬约束检查、锁定项检查、状态机检查；
- 行程版本、差异、乐观锁、事务提交；
- API 配额、缓存、重试、熔断和外部成本策略；
- 审批、通知、导出、删除和公开分享。

## 3. 执行模式

同一个工作流根据任务选择执行 Profile，避免所有请求都走最重流程。

| Profile | 适用请求 | 模型调用 | 外部研究 | 审计强度 |
|---|---|---:|---:|---|
| `CHAT_FAST` | 解释现有计划、简单问答 | 1 | 默认 0 | 只读快照检查 |
| `PATCH_LOCAL` | 换餐厅、调整时间、拖动一点 | 1–2 | 只查受影响地点 | 受影响子图 + 全局硬约束 |
| `PLAN_STANDARD` | 已知目的地的新行程 | 3–5 | 有界并行 | 完整规则 + 1 次模型复核 |
| `PLAN_DEEP` | 多城市、复杂成员、用户指定多攻略 | 5–8 | 多来源研究 | 完整规则 + 最多 2 次定向修复 |
| `IN_TRIP` | 延误、临时关闭、当天调整 | 1–3 | 只取最新关键事实 | 安全、订单、当天可执行性优先 |
| `IMPORT_EXTRACT` | OCR/已有计划/订单导入 | 1–2 | 默认无 | Schema、重复、金额和匹配检查 |

Profile 由确定性分类器根据意图、影响范围、城市数、天数、锁定项、攻略数量和实时性需求选择。模型可以建议升级 Profile，但不能自行解除工具和审批限制。

## 4. 核心状态与产物

### 4.1 `AgentRunState`

```json
{
  "run_id": "run_...",
  "workflow": "trip-plan",
  "workflow_version": "2.0.0",
  "profile": "PLAN_STANDARD",
  "status": "RUNNING",
  "trip_id": "trp_...",
  "base_trip_version": 12,
  "actor": {"user_id": "usr_...", "role": "MEMBER"},
  "intent": {},
  "requirements_ref": "req_...",
  "constraint_set_ref": "cst_...",
  "trip_snapshot_ref": "snap_...",
  "memory_snapshot_ref": "memsnap_...",
  "research_plan_ref": "rsp_...",
  "evidence_refs": [],
  "candidate_set_refs": [],
  "active_candidate_ref": null,
  "audit_report_ref": null,
  "patch_proposal_ref": null,
  "pending_approval_ref": null,
  "affected_entity_ids": [],
  "locked_entity_ids": [],
  "completed_nodes": [],
  "attempts_by_node": {},
  "limits": {
    "tool_calls_remaining": 24,
    "model_calls_remaining": 8,
    "wall_time_seconds_remaining": 300
  },
  "cancel_requested": false,
  "last_event_seq": 0
}
```

状态只保存引用和小型结构，不内嵌攻略全文、原始地图响应、图片或超长模型输出。大对象先写入 Evidence/Artifact Store，状态引用不可变 ID。

### 4.2 关键结构化产物

| 产物 | 产生节点 | 用途 |
|---|---|---|
| `IntentEnvelope` | Intent Router | 意图、任务范围、Profile、风险级别 |
| `TripRequirementsDraft` | Intake | 从表单/对话提取的需求草稿 |
| `ConstraintSet` | Constraint Compiler | 硬约束、软偏好、排除、假设 |
| `ResearchPlan` | Research Planner | 需要查询的事实、来源、停止条件 |
| `EvidenceRecord[]` | Tool/Evidence Nodes | 标准化事实、来源、时间和置信度 |
| `PlaceCandidateSet` | Venue Planner | 分类型候选与初筛得分 |
| `ItinerarySkeleton[]` | Itinerary Designer | 不含虚构精确路线的日程骨架 |
| `SolvedItinerary` | Route/Time Solver | 路线、时间窗、缓冲后的可执行计划 |
| `BudgetSnapshot` | Budget Engine | 确定性预算、区间、分摊和缺口 |
| `AuditReport` | Constraint/Audit Nodes | 问题、严重度、定位和修复建议 |
| `TripPatchProposal` | Patch Builder | 基于版本的结构化差异 |
| `ApprovalRequest` | Approval Gate | 用户需要确认的内容和影响 |
| `RunSummary` | Presenter | 面向用户的简洁说明，不是事实源 |

### 4.3 事实状态

模型和前端必须保留字段级事实状态：

- `verified`：用户、订单或可信工具确认；
- `estimated`：规则、路线或历史数据估算；
- `suggested`：模型/攻略建议；
- `unknown`：无可靠数据；
- `stale`：超过有效期；
- `conflicting`：存在尚未解决的来源冲突。

模型无权把 `suggested` 或 `estimated` 自行提升为 `verified`。

## 5. 通用节点契约

每个节点实现统一接口：

```text
NodeDefinition
  name
  version
  kind: LLM | TOOL | SOLVER | GATE | COMMIT | PRESENTATION
  input_schema
  output_schema
  reads
  writes
  idempotency_strategy
  timeout
  retry_policy
  failure_policy
  observability_policy
```

执行规则：

1. 读取指定版本的输入引用；
2. 校验取消标志、权限、配额和剩余调用上限；
3. 生成稳定的 `node_execution_key = run_id + node + input_hash`；
4. 若同键已有成功产物则复用；
5. 运行节点并执行输出 Schema 校验；
6. 先保存不可变产物，再原子更新 Run State；
7. 发出前端事件；
8. 根据输出的 `next_action` 路由，而不是解析自然语言决定下一节点。

LLM 节点最多允许一次“只修复结构格式”的重试；业务内容修订必须由 Audit Issue 定向触发，不能泛化为“请再想一遍”。

## 6. 意图路由与需求收集

### 6.1 Intent Router

优先使用规则判断显式 UI 操作：表单提交、拖拽、卡片编辑、确认按钮、订单上传已有明确 intent，不调用模型。只有自然语言才使用轻量结构化模型节点。

输出至少包含：

```json
{
  "intent": "CREATE_TRIP | MODIFY_TRIP | EXPLAIN | RESEARCH | IMPORT | IN_TRIP_ADJUST | RECORD_EXPENSE",
  "scope": "NONE | ITEM | DAY | CITY | TRIP",
  "requested_entities": [],
  "explicit_global_optimize": false,
  "requires_current_snapshot": true,
  "risk": "R0 | R1 | R2 | R3",
  "confidence": 0.0,
  "profile": "PATCH_LOCAL"
}
```

低置信度不等于立刻追问。若可以安全显示候选解释，则先给出可撤销建议；只有歧义会导致不同日期、城市、订单、锁定项或大范围修改时才询问。

### 6.2 Intake Agent

Intake 只做结构化，不搜索地点、不生成日程。输入由以下层级组成：

1. 本次用户明确输入；
2. 当前旅行已保存的单次偏好；
3. 用户选择应用的个人/家庭记忆；
4. 产品默认值。

输出把每个字段标记为：

- `explicit`：用户本次明确指定；
- `inherited`：从已确认记忆继承；
- `defaulted`：系统默认；
- `inferred`：模型推断，不能作为硬约束；
- `missing`：缺失。

### 6.3 澄清决策

程序计算 `RequirementReadiness`：

| 缺项 | 是否阻塞 |
|---|---|
| 出发日期/可接受日期范围 | 通常阻塞路线和营业验证 |
| 出发地、目的地或目的地选择范围 | 阻塞 |
| 人数/同行成员 | 阻塞预算和体力约束 |
| 已订交通/酒店时间 | 有订单时阻塞 |
| 必须满足与明确排除 | 需要用户确认后成为硬约束 |
| 预算、风格、作息 | 可使用可见默认值，不一定阻塞 |
| 餐厅具体选择 | 不阻塞，可推荐候选 |

一次最多集中询问 3 个真正阻塞问题。回答后只重跑 Intake 和 Constraint Compiler，不重启整个流程。

### 6.4 约束确认门

正式研究前，移动端显示一张“本次规划依据”卡：

- 日期、城市、人数、已订项目；
- 必须满足、尽量满足、普通偏好、明确排除；
- 采用的默认值和记忆；
- 可能影响结果的未知项。

用户确认后生成不可变 `ConstraintSet`。未确认的模型推断不能进入 `hard_constraints`。

## 7. 新旅行完整规划流程

### 7.1 阶段总览

```text
START
  → load_authoritative_context
  → route_intent
  → intake_requirements
  → compile_constraints
  → readiness_gate
  → await_constraint_confirmation（如需要）
  → build_research_plan
  → gather_core_facts ┐
  → gather_places    ├─ 有界并行
  → gather_guides    ┤
  → gather_weather   ┘
  → normalize_evidence
  → resolve_evidence_conflicts
  → rank_and_prune_places
  → generate_itinerary_skeletons
  → coarse_feasibility_filter
  → solve_routes_and_time
  → calculate_budget
  → deterministic_constraint_audit
  → model_quality_review（有条件）
  → targeted_repair（最多 2 轮）
  → rank_options
  → build_trip_patch_proposal
  → await_user_approval
  → revalidate_version_and_dynamic_facts
  → commit_transaction
  → render_and_explain
END
```

### 7.2 Research Planner

Research Planner 不直接调用工具，只输出最小研究计划：

```json
{
  "questions": [
    {
      "claim_key": "poi.forbidden_city.open_hours.2026-10-03",
      "reason": "硬时间窗依赖",
      "preferred_sources": ["official", "map"],
      "fallback_sources": ["user_guide", "multi_guide_consensus"],
      "freshness": "24h",
      "required": true,
      "stop_when": "one authoritative or two consistent sources"
    }
  ],
  "place_categories": [],
  "route_queries_deferred": true,
  "max_external_calls": 24
}
```

Research Plan 必须区分：

- 决定可行性的核心事实；
- 用于排序的增强事实；
- 仅用于解释的背景资料。

先获取核心事实；若核心事实已证明候选不可行，就不继续消耗增强研究。

### 7.3 有界并行研究

可以并行的任务：不同城市 POI 搜索、用户给定攻略读取、同一日期天气、独立的官方营业信息。

不可盲目并行：

- 未确定候选 POI 前的所有精确路线；
- 对同一事实同时调用所有 Provider；
- 依赖前一步地点 ID/坐标的查询；
- 用户可能马上取消的高消耗浏览器任务。

并发由应用控制，地图/天气请求优先批量、缓存和 in-flight 合并。工具结果按完成顺序写 Evidence，但后续排序使用稳定键，不能因网络返回顺序改变方案。

#### 7.3.1 攻略检索不是无条件全网爬取

新旅行的 `PLAN_STANDARD` 与 `PLAN_DEEP` 默认先做一轮攻略研究，但研究是有预算和停止条件的；简单问答、纯记账、已有计划的文字润色、已锁定地点的局部时间修改不重新搜索攻略。

用户可为每次旅行选择：

- `OFF`：不使用社区攻略，只使用用户输入、官方信息和地图事实；
- `USER_ONLY`：只读取用户粘贴的链接、文字和截图；
- `STANDARD`：默认，读取用户资料并补充公开搜索与少量社区结果；
- `DEEP`：复杂旅行或用户明确要求时，多轮检索并扩大来源覆盖。

`gather_guides` 的标准流程：

1. 从目的地、日期/季节、成员构成、风格、必须项和避坑需求生成 3～6 个互补查询词；
2. 优先读取用户指定攻略，其次使用公开 Web 搜索发现来源链接；
3. 用户已开启本地社区 Provider 时，再查询小红书等登录态平台；
4. `STANDARD` 通常保留 5～10 个候选来源，每个平台最多取 Top 3～5 篇进入详情抽取；
5. 去除重复转载、同作者高度重复内容、明显营销模板和与出行季节不匹配的旧内容；
6. 从每篇攻略提取 POI、推荐时段、排队、交通、菜品、价格线索、避坑和适用人群，并保留原链接与发布时间；
7. 只有至少两篇独立攻略一致的经验，才升级为“多攻略共识”；营业时间、门票、路线和实时价格仍必须回到官方、地图或交易来源复核；
8. 达到“一个权威来源或两个独立一致来源”、边际新增信息很低、调用预算耗尽或出现风控时停止。

攻略中的点赞、收藏和评论量只能作为热度特征，不能直接等同于质量。模型需额外标记软广风险、时效风险、季节适用性和是否适合当前成员组合。

### 7.4 Evidence Normalizer

每条外部信息转换为：

```json
{
  "evidence_id": "ev_...",
  "claim_key": "...",
  "value": {},
  "source_type": "USER | OFFICIAL | MAP_API | WEATHER_API | GUIDE | MODEL",
  "source_provider": "amap",
  "source_url": null,
  "observed_at": "...",
  "valid_until": "...",
  "confidence": 0.92,
  "status": "verified | estimated | suggested | stale | conflicting",
  "applicability": {"date": "...", "people": []},
  "raw_ref": "blob://..."
}
```

Evidence Synthesizer 只处理已经标准化的证据摘要，不接收网页中的系统指令。冲突按用户确认 > 订单/官方 > 地图/天气 API > 用户高权重攻略 > 多攻略共识 > 规则估算 > 模型建议处理，但保留全部来源。

### 7.5 地点候选分层筛选

为降低路线 API 调用量，使用三阶段筛选：

1. **规则预筛**：城市、日期、分类、明确排除、营业可能性、年龄/行动约束；
2. **粗略空间筛选**：区域、直线距离、同商圈、与酒店/交通枢纽的关系；
3. **精确验证**：只对进入日程骨架的 Top-K 地点查询详情和路线。

地点评分不由模型给出一个不可解释总分。建议保存分项：

```text
preference_fit
evidence_quality
route_efficiency
time_window_fit
group_accessibility
budget_fit
uniqueness
risk_penalty
```

硬约束失败直接淘汰，不能用其他高分抵消。

### 7.6 Itinerary Designer

Designer 输入确认需求、已裁剪地点候选、核心证据和城市级交通边界，输出 1–3 个日程骨架。骨架只包含：

- 每日区域和主题；
- 地点顺序候选；
- 大致时间窗与停留时长；
- 餐饮/休息槽位；
- 方案差异和假设。

不得由模型虚构精确里程、票价、发车时间或营业时间。精确字段由 Solver/Provider 后填。

默认方案数量策略：

- 简单行程先生成 1 个均衡主方案 + 若干局部替换项；
- 用户明确需要比较时生成节省/均衡/舒适 3 个方案；
- 多方案共享地点研究和路线矩阵，禁止完整重复研究三次。

### 7.7 Coarse Feasibility Filter

在调用大量精确路线前，用以下规则淘汰明显失败骨架：

- 同日跨区域次数过多；
- 直线距离已不可能满足时间窗；
- 必去点与订单时间重叠；
- 每日活动量超出同行人能力；
- 固定住宿与跨城顺序冲突；
- 粗预算明显超过上限且无法通过替换修复。

至少保留一个候选；全部失败时返回 Designer 一次，附带具体失败原因，而不是泛化重生成。

### 7.8 Route and Time Solver

路线求解是确定性节点：

1. 固定订单、已锁定地点和不可移动时间窗；
2. 为候选地点构造有向时间依赖图；
3. 查询缺失的相邻路线或矩阵；
4. 选择交通模式并计算换乘、候车、停车、步行和进出站缓冲；
5. 按营业时间和作息窗口安排开始/结束；
6. 检测不可达、闭环折返、过紧衔接；
7. 为午餐、晚餐、老人/儿童休息和自由时间保留可配置缓冲；
8. 输出路线来源、查询时间、估算费用和替代模式。

模型可解释为什么推荐某种交通，但不能自行覆盖 Solver 判定的不可达或时间冲突。

### 7.9 Budget Engine

Budget Engine 读取 PriceObservation 和参与人规则，确定性计算：

- 交通、住宿、餐饮、门票、当地交通、停车/油费/过路费；
- 成人/儿童/老人/学生票种资格；
- 每人、每房晚、每车、每桌、每订单计价；
- 已确认订单替换计划估价但保留原估价；
- 已知、估算、待确认、应急金和实际消费分层；
- 总额、按人分摊、家庭分摊和区间上下界。

模型只负责解释预算结构、提出节省候选，不执行最终算术。

## 8. 质量审计与定向修复

### 8.1 双层审计

第一层为确定性审计，必须每次执行：

- 硬约束；
- 日期、时区、时间重叠；
- 路线可达和衔接缓冲；
- 营业/预约时间窗；
- 锁定、已订、已完成项目；
- 预算算术与资格规则；
- 每日强度、连续步行、休息和用餐窗口；
- 来源缺失、过期和冲突；
- 修改范围越界。

第二层为模型质量复核，仅在标准/深度规划或存在软质量问题时执行：

- 行程主题是否连贯；
- 是否遗漏用户特别重视的体验；
- 是否存在虽然可执行但明显不舒适的安排；
- 多天内容是否重复；
- 餐厅、酒店、景点组合是否符合成员偏好；
- 风险和假设是否向用户表达清楚。

### 8.2 `AuditIssue`

```json
{
  "issue_id": "iss_...",
  "code": "TRANSFER_BUFFER_TOO_SHORT",
  "severity": "BLOCKER | ERROR | WARNING | INFO",
  "entity_ids": [],
  "constraint_id": null,
  "evidence_refs": [],
  "message": "...",
  "repair_scope": "ITEM | DAY | CITY | TRIP",
  "suggested_actions": [],
  "auto_repairable": true
}
```

### 8.3 修复策略

修复按最小影响原则排序：

1. 调整未锁定项目时长或缓冲；
2. 调整同日未锁定顺序；
3. 用同区域备选替换冲突地点；
4. 把非必去项目移动到其他天；
5. 更换交通模式；
6. 删除低优先级 AI 推荐项；
7. 只有前述均失败时才请求全局重排或用户放宽约束。

每轮只修复明确 Issue 集，并重新运行确定性审计。最多 2 轮；仍有 Blocker 时不得把方案标记为可确认，必须展示冲突和可选放宽方案。

## 9. 方案排序与用户确认

方案排序采用“门槛 + 多目标”而不是单一模型评分：

1. 有 Blocker 的方案淘汰；
2. 硬约束全部通过；
3. 比较软偏好满足、路线效率、预算、舒适度、证据完整度和自由时间；
4. 使用用户指定优先级形成 Pareto/加权排序；
5. 模型生成可读的差异解释。

移动端默认突出推荐方案，并展示：

- 为什么推荐；
- 与其他方案的时间、预算、步行和核心体验差异；
- 关键未知和待确认价格；
- 可以一键替换的局部候选；
- “应用此方案”前的变更摘要。

用户确认的是 `TripPatchProposal`，不是模型文本。确认提交前必须重新检查当前行程版本和短时动态事实。

## 10. 局部修改工作流

### 10.1 影响范围分析

修改请求首先转为 `ChangeIntent`：

```json
{
  "operation": "REPLACE_PLACE",
  "target_ids": ["item_123"],
  "requested_values": {},
  "preserve": ["date", "meal_type", "budget_band"],
  "explicit_global_optimize": false
}
```

Dependency Analyzer 根据实体关系计算受影响闭包：

- 被修改行程项；
- 前一段与后一段路线；
- 同日时间轴；
- 对应预算项；
- 提醒、日历和地图链接；
- 若跨日/跨城，相关住宿与城际交通。

默认不包含其他日期。只有硬约束传播或用户明确要求全局优化时扩大范围。

### 10.2 局部 Patch 流程

```text
load latest snapshot
  → parse change intent
  → compute affected subgraph
  → enforce locks/completed/booked boundaries
  → research only missing affected facts
  → generate local alternatives
  → solve adjacent routes/time/budget
  → run local audit
  → run global hard-constraint audit
  → build before/after/diff
  → await approval
  → optimistic commit
```

地图拖动时先在前端显示临时位置和近似影响，用户停止拖动后才精确查询；用户确认前不修改正式行程。

### 10.3 版本冲突

提交前若 `base_trip_version != current_version`：

- 若新版本修改的实体与当前 Patch 不相交，程序可重新应用并重新审计；
- 若相交，展示冲突，不允许静默覆盖；
- 让用户选择保留当前、采用提案或重新让 AI 合并；
- AI 合并也必须基于两个结构化 Diff，而不是仅看聊天文本。

## 11. 行中调整工作流

行中调整必须比出发前规划更保守：

- 已完成、已开始、已记账项目不可修改；
- 已预订项目默认锁定，取消/改签仅给提示和链接；
- 默认只调整当天未来项目；
- 先给最小改动方案，再给一个备选；
- 天气只提供建议，除非用户明确开启按天气调整；
- 优先保证交通、住宿、同行人安全和已订项目；
- 网络不可用时可以基于已缓存路线和离线快照生成保守建议，并明确数据时间。

```text
event/user request
  → classify urgency and affected window
  → freeze completed/started/booked entities
  → refresh only critical live facts
  → generate minimum-change option
  → generate optional fallback
  → audit safety/time/orders
  → show diff and source freshness
  → user confirms
  → commit and refresh reminders/links
```

严重天气、交通中断等事件不会自动大幅改写行程；系统发送提示并提供“仅调整今天”“查看多个方案”“暂不调整”。

## 12. 导入、订单与消费智能体

### 12.1 已有计划导入

Markdown、PDF、截图和文本先被解析为 `ImportedPlanDraft`。模型只负责字段映射和候选匹配：

- 日期、城市、地点、时间、交通、住宿、备注；
- 无法确认的地点保留原文和候选列表；
- 先展示导入预览；
- 用户确认后生成 TripPatch；
- 导入后再选择“保持原计划”或“优化计划”。

### 12.2 订单/票据流程

```text
upload
  → content hash dedupe
  → local OCR
  → schema extraction
  → confidence/rule check
  → user correction
  → optional vision/cloud OCR after consent
  → match to itinerary/order candidate
  → show amount/time/passenger conflicts
  → user confirmation
  → commit order/expense event
```

订单抽取不直接改变行程。订单确认后，系统提出匹配和时间/预算 Patch；用户再决定是否应用。

## 13. 用户记忆流程

记忆分为个人、家庭和单次旅行三层。规划时只注入本次用户允许且与任务相关的摘要。

记忆写入流程：

1. 来源必须是用户显式设置、用户修改行为或旅行后评价；
2. Memory Curator 生成 `MemoryProposal`，包含证据、适用范围、置信度和是否可能只是本次特例；
3. “必须满足”和敏感偏好必须确认；
4. 用户可以接受、编辑、拒绝、设为仅本次或长期；
5. 保存后生成新 Memory Version；
6. 后续模型只读取当前有效版本，不依赖旧聊天推断。

系统不得因为用户一次取消某餐厅，就永久推断用户不喜欢该菜系。

## 14. Prompt 与上下文工程

### 14.1 Prompt 分层

```text
System Policy        固定安全、权限、事实和工具规则
Workflow Policy      当前节点目标、允许动作、停止条件
Domain Snapshot      需求、约束、相关行程子图、证据摘要
Output Contract      JSON Schema、字段含义、示例和禁止项
User Message         当前请求
```

不把网页、攻略或 MCP 描述拼接进 System Policy；它们作为带来源标记的 `UNTRUSTED_CONTENT` 数据。

### 14.2 上下文裁剪

- 数据库结构化快照是事实源，聊天历史只用于理解当前表达；
- 新规划节点只读取与其职责相关的字段；
- 局部修改只发送受影响子图和全局硬约束摘要；
- 攻略先抽取主张和引用，不重复发送全文；
- 工具结果保存引用，模型只读取排序后 Top-K；
- 固定 Prompt 前缀和工具 Schema 保持稳定以提高 DeepSeek 缓存命中；
- 任何摘要都包含 `source_version`，防止旧摘要覆盖新状态。

### 14.3 模型参数建议

| 节点 | 温度 | Thinking | 工具 | 输出 |
|---|---:|---|---|---|
| Intent/Intake | 0–0.2 | 低或关闭 | 否 | 严格结构化 |
| Research Planner | 0.1–0.3 | 低 | 不直接执行 | `ResearchPlan` |
| Evidence Synthesizer | 0–0.2 | 低 | 只读证据 | 严格结构化 |
| Itinerary Designer | 0.2–0.5 | 中/高 | 受控只读 | 1–3 个骨架 |
| Quality Reviewer | 0–0.2 | 高 | 不主动扩展研究 | `AuditIssue[]` |
| Targeted Repair | 0.1–0.3 | 中 | 仅受影响工具 | Patch 草稿 |
| Presenter | 0.2–0.5 | 低 | 否 | 用户说明 |
| Order/Memory Extractor | 0 | 低或关闭 | 否 | 严格结构化 |

这些是逻辑能力要求，实际参数由 ModelProvider Capability Profile 映射；不支持某参数时安全降级。

## 15. 工具调用策略

### 15.1 工具选择

模型看到少量业务工具，不直接看到供应商的全部 API 参数。工具 Registry 根据节点、用户权限、Profile 和剩余外部配额动态生成 allowlist。

例如 Designer 可以读候选和证据，但不能提交 Patch；Critic 可以运行约束审计，但不能自由搜索新攻略；Presenter 不获得任何外部工具。

### 15.2 停止条件

每个工具计划必须声明 `stop_when`：

- 已获得一个权威来源；
- 已获得两个一致来源；
- Top-K 候选已满足；
- 所有最终相邻路线已求解；
- 已达到免费额度软阈值；
- 后续信息不会改变方案排序。

“可能还有更多信息”不能成为继续调用的理由。

### 15.3 工具错误分类

| 错误 | 处理 |
|---|---|
| `NO_RESULT` | 换关键词/Provider 一次或转人工指定 |
| `RATE_LIMITED` | 按 Retry-After、缓存或降级，不并发重试 |
| `AUTH_FAILED` | 禁用 Provider 并通知管理员，不让模型反复调用 |
| `TIMEOUT` | 只读幂等请求最多一次退避重试 |
| `SCHEMA_CHANGED` | 暂停工具，保留原始引用，要求管理员复核 |
| `STALE_DATA` | 可作为带时间的参考，不标记 verified |
| `POLICY_BLOCKED` | 向模型返回可解释限制，不暴露内部安全细节 |

## 16. 检查点、并发、取消与恢复

- 每个节点成功后保存检查点；
- Tool 节点先写 Evidence 再推进状态；
- Commit 节点使用幂等 Command ID；
- Approval 节点可以等待数天，恢复时重新检查权限和版本；
- 用户取消后停止新任务，尝试取消在途请求，迟到结果可以缓存但不得继续推进已取消 Run；
- 同一 Trip 默认最多一个写提案工作流；只读解释可并行；
- 同一用户重复发起相同生成请求时复用或提示已有 Run；
- NAS 重启后扫描 `RUNNING/WAITING` 状态，恢复安全节点或标记需用户继续；
- 工作流升级不迁移正在等待确认的 Run 时，允许旧版本完成并对新提交执行当前领域校验。

## 17. 前端事件与渐进呈现

工作流不让用户等待到最后才看到结果。SSE 事件至少包括：

```text
run.started
requirements.summary_ready
approval.required
research.progress
candidate.preview_ready
route.progress
audit.issue_found
proposal.ready
run.completed
run.failed
run.cancelled
```

事件只描述阶段、进度和可展示产物，不输出隐藏思维链。建议体验目标：

- 1 秒内显示任务已开始；
- 3–10 秒显示需求摘要或已有缓存结果；
- 研究过程中逐步显示已确认地点和来源；
- 候选骨架就绪后可预览，但标记“路线/预算校验中”；
- 最终只有通过硬质量门的方案可点击确认。

## 18. 性能与高效策略

### 18.1 减少模型调用

- 显式 UI 操作走规则 Intent；
- 结构化状态替代完整聊天回放；
- Evidence 一次归一化，多方案共享；
- Designer 一次生成多个骨架，不为每个方案重新研究；
- 确定性审计通过且无复杂软问题时跳过模型 Critic；
- Presenter 可由已有结构模板生成，复杂解释才调用模型；
- 格式错误只修复一次，不重跑整个节点。

### 18.2 减少外部调用

- POI 三阶段裁剪后才查详情/精确路线；
- 批量距离或矩阵优先；
- 同一城市/坐标天气共享；
- 相同参数 in-flight 合并；
- 局部修改使用依赖图；
- 百度只降级或抽样；
- 攻略先搜索摘要再抓 Top 3–5 页面；
- `free_only` 达限后停止扩展研究，不影响 DeepSeek 正常规划。

### 18.3 运行上限

运行上限用于稳定性和防循环，不是 DeepSeek 费用额度：

| Profile | 模型调用建议上限 | 外部工具建议上限 | 总时限 |
|---|---:|---:|---:|
| CHAT_FAST | 1 | 0–2 | 30 秒 |
| PATCH_LOCAL | 2 | 8 | 90 秒 |
| PLAN_STANDARD | 5 | 24 | 180 秒 |
| PLAN_DEEP | 8 | 60 | 300 秒 |
| IN_TRIP | 3 | 12 | 90 秒 |

用户明确要求继续深度研究时可以启动新的 Run，而不是无限延长旧 Run。

## 19. 失败与降级

| 失败位置 | 可交付降级结果 |
|---|---|
| 模型不可用 | 保存已收集需求和证据，允许稍后继续；已有行程仍可手动编辑 |
| 地图不可用 | 使用缓存/另一地图/直线粗估，标记路线待验证 |
| 天气不可用 | 不调整计划，展示无实时天气提示 |
| 攻略不可用 | 使用用户资料、地图事实和已有缓存，不虚构评价 |
| 路线候选全失败 | 展示冲突、最小放宽选项，不生成伪可执行计划 |
| Critic 输出失败 | 保留确定性审计；不因缺少语言复核阻塞简单方案 |
| 提交版本冲突 | 保留 Proposal，展示差异并重新基于最新版本计算 |
| 进程重启 | 从最后成功检查点恢复，副作用按幂等键去重 |

## 20. 质量指标与评估集

### 20.1 必须指标

| 指标 | 首版目标 |
|---|---:|
| 硬约束违反率 | 0 |
| 已完成/锁定项越界修改率 | 0 |
| 预算算术误差 | 0 |
| 不可达路线进入确认方案 | 0 |
| 用户确认前数据库副作用 | 0 |
| 关键动态事实无来源率 | <5%，且必须标记 unknown/estimated |
| 局部修改非必要变更数量 | 0 |
| 工具重复调用率 | 持续降低，缓存可解释 |
| Schema 校验通过率 | 100%（含一次格式修复） |
| 受控重启恢复成功率 | >99% |

### 20.2 质量评分只用于比较

可定义内部 `PlanQualityScore` 供方案比较和回归测试，但不能覆盖硬门：

```text
quality =
  preference_fit
  + route_efficiency
  + comfort
  + evidence_completeness
  + budget_fit
  + resilience
  - risk_penalty
```

分数权重按旅行 Profile 可配置，并在测试中固定版本。用户不需要看到一个看似精确的总分，而应看到实际差异。

### 20.3 回归场景

- 北京 3 日家庭游，含老人和儿童；
- 上海雨天亲子行程，默认只提示天气；
- 成都慢节奏美食游，餐厅排队和午休；
- 多城市高铁 + 自驾接驳；
- 航班延误后的当天局部调整；
- 酒店和两项门票已订、其余全局优化；
- 拖动地点后只重算相邻路线；
- 多用户同时编辑触发版本冲突；
- 攻略包含 Prompt Injection；
- 地图 API 超限、天气失败、模型中断；
- OCR 价格错误、退款和重复订单；
- 行程中断后 Docker/NAS 重启恢复。

## 21. 首版节点清单

### P0

- `load_authoritative_context`
- `route_intent`
- `intake_requirements`
- `compile_constraints`
- `readiness_gate`
- `await_approval`
- `build_research_plan`
- `gather_places`
- `gather_weather`
- `ingest_user_guides`
- `normalize_evidence`
- `rank_and_prune_places`
- `generate_itinerary_skeletons`
- `coarse_feasibility_filter`
- `solve_routes_and_time`
- `calculate_budget`
- `deterministic_constraint_audit`
- `targeted_repair`
- `build_trip_patch_proposal`
- `commit_transaction`
- `render_and_explain`
- `compute_affected_subgraph`
- `extract_order_or_plan`
- `in_trip_adjustment`
- `memory_curator`

### P1

- `gather_guides`
- `resolve_evidence_conflicts_with_model`
- `model_quality_review`
- `rank_multiple_options`
- `refresh_pre_trip_facts`

## 22. 实施建议与待验证决策

### 22.1 推荐实现顺序

1. 先定义产物 Schema、节点接口和状态迁移；
2. 实现无模型的时间、预算、约束、差异和依赖图；
3. 接入高德/和风 Adapter 和 Evidence Store；
4. 实现 Intake、Designer、Targeted Repair 三个关键 LLM 节点；
5. 完成审批、提交、恢复和 SSE；
6. 完成 P0 的用户攻略导入、行中局部调整、旅行后评价与记忆确认；
7. 再增加 P1 的自主攻略搜索、模型 Critic 和行前主动刷新。

### 22.2 框架边界

可使用 LangGraph 提供检查点、中断和恢复，但领域 Schema、NodeDefinition、Tool Registry、审批、版本和 Repository 不依赖其私有类型。这样未来可以替换编排框架而不迁移旅行数据。

### 22.3 需要 PoC 验证

- DeepSeek 当前模型在 Intake、Designer、Critic 三类 Schema 上的稳定性；
- Thinking + Tools 时实际上下文回传和缓存命中；
- 2–3 个候选骨架一次生成与分次生成的质量/延迟差异；
- 路线矩阵和逐段算路在国内多交通模式下的准确率；
- SQLite 检查点在取消、并发编辑和 Docker 重启下的一致性；
- `PLAN_STANDARD` 在 NAS 上的峰值内存和 180 秒完成率；
- 确定性审计通过时跳过模型 Critic 对质量的真实影响。
