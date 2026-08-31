# 国内优先的智能旅游规划平台：数据源、API、MCP 与移动端接入调研

> 调研日期：2026-08-30
> 阶段：需求细化与技术可行性调研
> 范围：国内市场优先；海外能力仅做架构预留
> 说明：接口字段、配额、价格、商业授权及平台规则会持续变化。本文给出的是技术选型依据，不替代最终商务合同、法务审查和上线前实测。

> 项目已进一步收敛为个人/小团队低频自托管系统。具体 Docker、DeepSeek、自定义模型、SQLite、低成本和降级方案见：[自托管小型系统设计](./self-hosted-small-system-design.md)。

## 1. 结论摘要

### 1.1 推荐的总体方案

建议采用“高德主用、百度校验、腾讯预留、交易平台合作接入、社区内容受控接入”的多供应商架构：

1. **高德作为国内地图主供应商**：路径规划 2.0 的成本字段较完整，驾车可返回预估过路费，公交可返回票费，路线还可返回出租车估价；POI 可提供评分、人均消费等适合行程粗预算的数据。高德官方 MCP 还支持把模型生成的攻略导入高德 App，生成专属地图和唤端链接。
2. **百度作为路线与 POI 交叉校验源**：百度 Direction API 支持 18 个以内途经点、未来 7 天驾车规划、跨城公交组合、摩托车等能力；POI 详情可返回价格、评分、评论数、营业时间、建议游玩时长和最佳游玩时间。百度也提供官方开源 MCP Server 和远程 MCP 接入。
3. **腾讯位置服务作为第三候选**：官方 MCP 已覆盖沿途搜索、途经点智能排序、未来路线、公交票价、矩阵等能力。若产品主要运行在微信生态，可纳入第二阶段实测。
4. **地图价格只用于规划估算，不用于交易承诺**：高德/百度给出的出租车费、过路费、公交票价、POI 人均价格都应标记为估算值。机票、酒店、门票、套餐等实时可订价格，应通过携程、飞猪、美团等商务合作接口获取，或跳转官方页面让用户确认。
5. **小红书不应依赖非公开接口作为生产核心数据源**：官方开放能力主要是登录授权、小程序经营和分享发布，并没有面向普通开发者的全站笔记搜索 API。社区 MCP/爬虫只能用于低频、用户主动触发的研究性 PoC；正式商用应优先采用用户粘贴链接、合法授权数据、开放搜索摘要和平台商务合作。
6. **大模型不直接“计算真实价格”**：由确定性的预算引擎完成计价、分摊、币种和舍入；模型负责解释偏好、生成候选方案、调用工具、比较方案、解释风险。所有价格保留来源、查询时间、置信度、适用人数和是否可预订。
7. **移动端采用 H5/PWA 优先 + 原生唤端链接**：每个行程段提供“查看地图”“开始导航”“打车”“购票/预订”“查看来源”按钮；唤端失败时回退到 HTTPS 页面。微信/QQ 内置浏览器需特别处理无法直接打开地图 App 的情况。

### 1.2 产品竞争力不应只放在“生成攻略”

携程 AI 行程助手已经覆盖食住行游娱购、地图拖拽编辑、实时数据与预订；高德 MCP 已能把攻略直接变成专属地图。因此，本产品应重点建立以下差异化能力：

- 从家门口出发到回家的**全过程分段行程**，而不是只有目的地内景点列表；
- 预算的**总价、分摊、预算上限、超支原因和价格可信度**；
- 成人、儿童、老人、学生、司机、行李、房间和车辆约束下的**多人协同计算**；
- 路线、营业时间、游玩时长、天气、体力、就餐时间之间的**可解释合理性检查**；
- 计划预算与实际消费的**自动对账和归档**；
- 原始攻略观点、地图事实和实时商品价格的**证据分层**；
- 行中变化后的**局部重排**，而不是整份攻略重新生成。

参考：[携程 AI 行程助手](https://www.ctrip.com/tripplanner/)、[高德 MCP 出行规划专属地图案例](https://developer.amap.com/api/mcp-server/application-case/travel-planning-case)。

## 2. 需求细化

## 2.1 用户输入

基础输入：

- 出发地、最终返回地；
- 出发/返回日期和时间窗口；
- 目的地，可为单城、多城、环线或未确定；
- 成人、儿童、婴儿、老人、学生人数与必要证件类型；
- 总预算、币种、预算是否包含购物；
- 交通偏好：飞机、高铁、普速、自驾、租车、包车、公交、步行、骑行；
- 住宿偏好：价格、星级、房型、房间数、是否含早、停车、亲子设施；
- 兴趣：自然、人文、美食、摄影、亲子、夜生活、小众、无障碍等；
- 节奏：特种兵、均衡、休闲；
- 禁忌与约束：过敏、宗教饮食、行动能力、晕车、早起限制、必须打卡点；
- 行李数量、是否有儿童座椅、是否携宠物；
- 私家车参数：能源类型、百公里油耗/电耗、充电偏好、车型高度等。

系统应支持自然语言输入，但在生成正式计划前把关键信息转换为结构化 `TripRequirements`，并提示仍未确定、会显著影响价格或可行性的字段。

## 2.2 从出发到返回的全过程行程

每一次旅行应拆分为可验证的行程段，而不是一段文本：

1. 家/集合点 → 机场或火车站；
2. 值机、安检、候车缓冲；
3. 飞机/高铁/自驾主干交通；
4. 到达站 → 酒店或首个目的地；
5. 每日景点、餐厅、休息点、酒店之间的市内交通；
6. 返程前退房、行李寄存和去车站/机场；
7. 返程主干交通；
8. 到达站 → 家/解散点。

每个 `TripLeg` 至少保存：起终点、坐标及坐标系、计划起止时间、交通方式、距离、耗时、缓冲时间、费用构成、预订状态、来源、查询时间、导航链接和备选方案。

## 2.3 行程合理性分析

建议将合理性拆成可计算规则，模型只负责补充语义判断：

- **时间可行性**：交通时长 + 排队 + 游玩 + 吃饭 + 缓冲是否超过当天可用时间；
- **营业约束**：到达时是否营业、是否闭馆、是否需要预约；
- **空间顺序**：是否反复跨区、是否存在明显折返；
- **体力负荷**：步行距离、爬升、连续站立、老人儿童承受度；
- **交通衔接**：机场/车站最晚到达时间、换乘时间、末班车；
- **天气风险**：高温、暴雨、台风、降雪、景区临时关闭；
- **用餐合理性**：用餐时段、排队时间、餐厅与路线偏离程度；
- **预算合理性**：估算是否漏项、多人分摊是否正确、是否超过上限；
- **预约冲突**：门票、酒店、车次、餐厅预约是否相互冲突；
- **回退能力**：室内备选、雨天备选、临时取消后的替换项。

输出不应只有“合理/不合理”，而应返回问题等级、证据、影响和可执行修改建议。

## 3. 高德地图与百度地图详细对比

## 3.1 能力矩阵

| 维度 | 高德地图 | 百度地图 | 本项目判断 |
|---|---|---|---|
| 国内驾车路线 | 支持多策略、多路线、途经点、车牌限行 | 支持多路线、18 个以内途经点、车牌限行 | 都可用，必须同路线实测 |
| 未来路线 | 有实时/预测相关能力，具体产品按权限核实 | Direction v2 明确支持未来 7 天驾车规划 | 百度文档更明确 |
| 驾车过路费 | `tolls`、收费里程和收费道路等扩展字段 | `toll` 预估道路费 | 高德字段更细 |
| 出租车估价 | 驾车/公交等返回 `taxi_cost` 或 `taxi_fee` | 需按具体接口和城市实测 | 高德更适合初期预算 |
| 公交票价 | 公交方案可返回 `transit_fee` | 公交方案可返回 `ticket_price` | 都可用，票制复杂时需复核 |
| 跨城公共交通 | 公交规划可组合火车、公交、地铁等 | 支持公交、地铁、火车、飞机、大巴 | 百度描述更完整，高铁票价仍不能替代 12306/OTA |
| 步行/骑行/电动车 | 步行、骑行、电动车 | 步行、骑行、电动车，另有摩托车能力 | 百度在摩托车场景更强 |
| POI 价格与评分 | 餐饮、酒店、景点等可有 `rating`、`cost` | 详情可有 `price`、`overall_rating`、`comment_num` | 都是推荐和粗估字段，不是实时成交价 |
| 景点辅助信息 | POI 类型、照片、营业等字段按权限 | 可含营业时间、最佳游玩时间、建议游玩时长 | 百度适合景点规则补充 |
| 批量距离 | 基础距离支持多起点到单终点；物流矩阵为高级场景 | 官方 MCP 包含方向矩阵 | 路线优化前先做能力/配额实测 |
| App/H5 唤端 | Web URI、Android/iOS URI；官方 MCP 可生成专属地图、导航和打车链接 | Web URI、Android/iOS/鸿蒙调起，支持 WebApp 回退 | 高德专属地图是明显优势 |
| MCP | 官方 MCP，12 类核心位置能力并可生成专属地图 | 官方开源 MCP，远程 HTTP/SSE、npm、pip | 两者均适合 PoC；生产服务仍应有内部适配层 |
| 坐标系 | GCJ-02 | 默认常见 BD-09，可请求/转换 GCJ-02 | 严禁直接混用 |
| 商用 | 商业用途需获取技术服务许可/商用授权 | 高级字段、图片、营业状态及高并发等可能需购买 | 上线前必须商务确认 |

官方依据：[高德路径规划 2.0](https://lbs.amap.com/api/webservice/guide/api/newroute)、[高德 POI 搜索](https://lbs.amap.com/api/webservice/guide/api/search/)、[百度 Direction API](https://lbsyun.baidu.com/docs/webapi?title=directionv2%2Fdirection-api-v2)、[百度地点检索 v3](https://lbsyun.baidu.com/docs/webapi?title=placev3%2Fguide%2Fwebservice-placeapiV3%2FinterfaceDocumentV3)。

## 3.2 高德路线费用字段

高德路径规划 2.0 对本项目最有价值的字段包括：

- 驾车路线总览：`distance`、`cost.duration`、`cost.tolls`、`cost.toll_distance`、红绿灯数等；
- 整体出租车估价：`taxi_cost`；
- 公交方案：`transit_fee`、`taxi_fee`，以及步行、地铁、公交、铁路和出租车分段；
- 路况与拥堵信息，可用于判断计划时段的风险；
- 途经点、车牌限制和路线偏好。

注意事项：

- 过路费和出租车费均是估算，不能替代出租车平台报价或收费站实际金额；
- 城市夜间费、动态调价、跨城返空费、高速费是否包含需通过测试确认；
- 必须在请求中显式申请扩展字段，否则可能拿不到完整成本数据；
- 公交票价可能受分段票制、优惠卡、儿童政策影响。

参考：[高德路径规划 2.0 官方文档](https://lbs.amap.com/api/webservice/guide/api/newroute)。

## 3.3 百度路线费用与 POI 字段

百度值得作为补充的字段和能力：

- 驾车 `toll`：文档明确说明为估算路费，可能与实际不同；
- 公交 `ticket_price`：按票种统计总票价；
- POI `detail_info.price`、`overall_rating`、`comment_num`、`shop_hours`；
- 景点 `best_time`、`sug_time`、描述、榜单排名等；
- 未来 7 天驾车、18 个以内途经点、摩托车限行等。

百度文档还说明，地点 API 出于数据保护原因可能不是客户端最新数据，且部分图片和营业状态需要商用授权后申请。因此不能假设“百度地图 App 能看到的内容，API 一定能返回”。

参考：[百度驾车路线](https://lbsyun.baidu.com/docs/webapi?title=directionv2%2Fwebservice-direction%2Fdirve)、[百度公交路线](https://lbsyun.baidu.com/docs/webapi?title=directionv2%2Fwebservice-direction%2Ftransit)、[百度地点检索 FAQ](https://lbsyun.baidu.com/index.php?title=%E6%A8%A1%E6%9D%BF%3AFAQ-placeapi)。

## 3.4 最终地图选型建议

### 推荐：高德主用，百度影子验证

初期不建议在用户界面同时混合两套地图瓦片与坐标。推荐：

- 用户地图展示、导航、专属地图：高德；
- 服务端主要算路、POI 搜索与费用粗估：高德；
- 对关键路线、景点营业时间、游玩时长进行后台抽样：百度；
- 当高德超时、无结果或字段不足时，调用百度并将结果转换到统一模型；
- 微信生态和沿途智能排序需求明显后，再评估腾讯位置服务。

选择理由不是“高德永远更准”，而是高德当前更贴合本产品的行程输出、费用字段和 App 唤端闭环。真实准确率必须通过本项目自己的基准集验证。

## 3.5 地图 PoC 验收方法

建议建立至少 60 条黄金路线：

- 20 条市内驾车/出租车：一线、新一线、旅游城市、小城市；
- 10 条跨城自驾：含高速费、轮渡、山区；
- 10 条地铁/公交：含分段票价和跨城交通；
- 10 条步行/骑行：景区入口、大型园区、过江；
- 10 条多途经点路线：5～15 个景点。

每条记录人工核验：

- 可用路线数、距离、耗时、过路费、公交票价、出租车估价；
- 起终点是否落在正确入口；
- 是否有明显绕路、限行或不可达；
- 同一时刻高德、百度和真实 App 结果差异；
- 接口延迟、错误率、配额消耗和字段缺失率。

供应商决策指标建议为：路线可达率 25%、ETA 误差 20%、费用字段完整率 20%、POI 命中与入口准确率 15%、移动端闭环 10%、成本与商务确定性 10%。

## 4. 路线与多人费用计算引擎

## 4.1 价格类型必须分层

系统中的每个价格必须属于以下一种：

| 类型 | 例子 | 可否用于下单 |
|---|---|---|
| 统计估算 | 地图 POI 人均、历史均价 | 否 |
| 路线估算 | 过路费、出租车费、油费 | 否 |
| 查询报价 | OTA 某时刻的机票/酒店/门票报价 | 仅在有效期内，仍需下单确认 |
| 已锁定价格 | 创建订单后短时保价 | 可以，受订单条款约束 |
| 实际支付 | 用户支付或导入账单 | 用于归档与复盘 |

价格记录建议字段：

```json
{
  "amount": 328.00,
  "currency": "CNY",
  "pricing_type": "quote",
  "unit": "room_night",
  "quantity": 2,
  "source": "partner_api",
  "source_name": "example_provider",
  "queried_at": "2026-08-30T10:20:00+08:00",
  "expires_at": "2026-08-30T10:35:00+08:00",
  "confidence": 0.96,
  "includes": ["tax"],
  "excludes": ["deposit"],
  "evidence_url": "https://..."
}
```

## 4.2 多人计价单位

不能简单使用“单价 × 人数”。先识别计价单位：

- `per_person`：机票、高铁票、景点成人票；
- `per_child` / `per_student` / `per_senior`：特殊人群票；
- `per_vehicle`：出租车、租车、过路费、停车费；
- `per_room_night`：酒店；
- `per_order`：服务费、配送费、保险订单费；
- `per_table` / `per_dish`：餐厅套餐或点菜；
- `per_day`：租车、导游、随身 Wi-Fi；
- `actual`：已发生消费。

## 4.3 计算公式示例

### 出租车

```text
车辆数 = ceil(乘客数 / 实际可乘人数)
```

实际可乘人数需考虑行李、儿童座椅和车型。总费用：

```text
出租车总估价 = 单车路线估价 × 车辆数 + 预约费 + 可能的高速费调整
```

### 自驾

```text
燃油费 = 路线公里数 / 100 × 百公里油耗 × 当前油价
电费 = 路线公里数 / 100 × 百公里电耗 × 平均充电单价
自驾总价 = 能源费 + 过路费 + 停车费 + 租车费 + 异地还车费 + 保险
```

### 酒店

不能只用 `ceil(人数 / 每房人数)`。应做房型分配：

- 成人与儿童同住规则；
- 婴儿床/加床费用；
- 房间最大入住人数；
- 单人入住偏好；
- 含早人数；
- 连住优惠和取消政策。

### 餐饮

POI 人均价格只适合粗估：

```text
等效用餐人数 = 成人 + 儿童系数 × 儿童 + 老人系数 × 老人
餐饮估算 = 人均价格 × 等效用餐人数 × 餐型系数 + 包间/服务费
```

用户确认餐厅后，应优先取套餐、菜单或用户自定义预算；大模型不能凭菜名虚构价格。

### 门票

```text
门票总价 = Σ(票种实时价 × 对应人数) + 预约/讲解/摆渡/索道等附加项
```

儿童票规则可能按年龄、身高或证件，老人/学生优惠也可能只限特定证件。系统应保存资格条件并在不确定时按成人价形成上限预算。

## 4.4 三档预算

每份行程建议同时输出：

- **节省档**：公共交通、经济型住宿、普通餐饮；
- **均衡档**：舒适交通、位置更好的住宿、部分特色餐厅；
- **舒适档**：更少换乘、更多打车、更高房型或包车。

每档展示总额、人均、固定费用、按人费用、可选费用、预留金，以及相对用户预算的差额。建议默认预留 8%～15%，旺季和不确定项目较多时提高。

## 5. 餐饮、景点门票、酒店与交通价格来源

## 5.1 数据源优先级

| 数据领域 | 首选 | 次选 | 兜底 | 结论 |
|---|---|---|---|---|
| 餐厅发现/人均 | 高德/百度 POI | 合作方本地生活数据 | 用户输入、公开页面链接 | 适合推荐和粗估，不保证菜单实价 |
| 餐厅预订/套餐 | 美团生态合作、餐饮直连 | 餐厅官方小程序/电话链接 | 用户自行确认 | 通常需商务准入 |
| 景点基础信息 | 高德/百度 POI、景区官网 | 文旅官方平台 | 合法攻略内容 | 营业时间需在出行前复核 |
| 景点实时票价 | 携程玩乐、飞猪门票、美团合作 | 景区官方购票页 | 跳转链接 | 必须区分票种和日期 |
| 酒店实时价 | 携程/飞猪/美团酒店合作 | 酒店集团直连 | 跳转 OTA | 地图 POI 价格不能替代房态报价 |
| 飞机 | OTA 合作、航司 NDC | 航司官网链接 | 用户自行确认 | 报价时效短，行李/退改要结构化 |
| 高铁/火车 | 正式合作渠道或 12306 官方跳转 | 低频只读查询 PoC | 用户输入订单 | 12306 不提供通用公共开发者售票 API |
| 市内公交 | 地图路线 API | 当地公交官方 | 静态规则 | 优惠卡与特殊人群票另算 |
| 出租车 | 地图估价 | 打车平台唤端后报价 | 里程规则估算 | 动态调价以打车页为准 |

## 5.2 可申请的国内平台

### 携程

- [携程旅游/玩乐开放平台](https://ttdopen.ctrip.com/)覆盖景点门票、玩乐、租车、接送机等商品导入、分销、下单、退订和核销；
- [携程商旅开发者平台](https://openapi.ctripbiz.com/)适合企业差旅、审批、人员和订单整合；
- [Trip.com 开发者中心](https://developers.trip.com/?lang=zh-CN)可作为国际业务预留。

判断：能力完整，但面向供应商、分销商或企业合作，不应按“免费开放 API”估算项目周期。

### 飞猪

[飞猪开放平台](https://open.fliggy.com/)明确覆盖机票、酒店、门票、度假、汽车票、船票、用车等，但不同类目有独立资质、技术服务费和接入标准。

判断：适合第二阶段商务接入；初期先用深链/官方页面跳转完成需求验证。

### 美团/大众点评

- [美团生态开放平台](https://openapi.meituan.com/)支持 API、H5 嵌入和混合接入，但需要申请合作、商务评估和验收；
- [美团餐饮直连平台](https://developer.dianping.com/)主要服务点餐、排队、核销、门店和团购等商家系统连接；
- [美团酒店直连平台](https://openplatform-hotel.meituan.com/portal/process-chart)主要面向酒店供给、房态、价格、库存和订单直连。

判断：公开入口不等于可匿名检索全站商户、评论和消费数据。若没有正式合作，不应把大众点评抓取作为商业产品的数据底座。

## 5.3 铁路数据的特殊边界

[12306 官方网站](https://www.12306.cn/index/)提示铁路未授权其他网站或 App 开展类似服务。当前社区工具通常调用 12306 网站正在使用的公开 Web 端点，而不是正式、稳定、有 SLA 的开发者 API。

可用于内部 PoC 的工具：

- [drfccv/mcp-server-12306](https://github.com/drfccv/mcp-server-12306)：支持余票、票价、车站、经停和换乘，提供 stdio、HTTP 和 Docker；
- [HansBug/china-railway-12306](https://github.com/HansBug/china-railway-12306)：面向 Codex/Claude Code 的只读 Skill，明确限制为低频个人查询，不用于订票、监控和绕过控制。

生产建议：

- 默认跳转 12306 或正式 OTA；
- 社区工具只在低频、用户主动查询、无登录无下单条件下进行技术验证；
- 做熔断、缓存和限速，不承诺可用性；
- 不保存用户 12306 凭证，不做验证码、抢票、占座和自动下单；
- 商业上线前获取铁路/OTA 合作或书面法律意见。

## 5.4 航空补充

国内航司可能提供 NDC 合作接口，例如[厦门航空开放平台](https://open.xiamenair.com/portal/index)覆盖查询、预订、支付、出票、退改、选座、行李和餐食，但一般需要申请和审核。早期应优先接一家聚合 OTA，而不是逐家航司接入。

## 6. 攻略、评价与小红书接入

## 6.1 内容证据分层

建议将内容分为四层：

1. **官方事实层**：景区官网、文旅局、交通部门、地图营业信息；
2. **交易事实层**：OTA 商品、库存、价格、退改条款；
3. **社区经验层**：小红书、马蜂窝、B 站、微博等用户体验；
4. **模型推断层**：模型根据多来源做的总结。

最终回答应明确区分事实与观点。例如“景区 17:00 停止入园”必须有官方或可靠来源；“下午光线更适合拍照”可以来自多篇攻略，但需标记为经验总结。

## 6.2 小红书官方可用能力

目前可确认的官方能力包括：

- [小红书账号开放平台](https://openaccount.xiaohongshu.com/docs/api-reference)：OAuth、Token 和最小用户资料，非全站内容搜索；
- [小红书小程序开放平台](https://miniapp.xiaohongshu.com/)：小程序、交易、POI 入口、笔记挂载等经营能力；
- [小红书分享开放平台](https://agora.xiaohongshu.com/)：把第三方图文或视频分享到小红书；
- 小程序可使用 `xhsdiscover://miniapp/...` 形式的站内跳转链接，需按开放平台要求入驻、备案和审核。

结论：官方平台适合“登录、分享、经营、站内承接”，没有证据表明它向普通开发者开放全站旅游笔记搜索和批量评论获取。

## 6.3 推荐的小红书接入路径

按风险从低到高：

### A. 用户粘贴分享链接（推荐首发）

- 用户主动粘贴一篇或多篇笔记链接；
- 系统保存链接和用户可见的摘要，不默认永久复制图片/全文；
- 提取景点、餐厅、避坑项、时间和价格线索；
- 使用地图 API 对 POI 名称、地址、营业状态和路线重新验证；
- 给用户保留“查看原笔记”链接。

### B. Web 搜索摘要

通过合规搜索服务检索公开网页或 `site:xiaohongshu.com` 结果，取得链接与摘要，再由用户打开来源。优点是无需维护登录 Cookie，缺点是覆盖不完整且排序不可控。

### C. 用户授权的可见浏览器会话

只在用户主动发起时，使用本地/隔离浏览器打开其已登录页面，提取当前可见内容。需要明确提示、频率限制、日志脱敏、会话隔离和随时撤销。

### D. 非公开 API 或自动化抓取

只能做隔离 PoC，不应作为生产承诺。常见风险包括接口随时变更、账号风控、Cookie 泄露、平台条款、版权、个人信息、反不正当竞争和大规模采集风险。

## 6.4 社区小红书工具评估

本项目自有只读查询组件的完整范围、接口、容器隔离、Agent 约束、资源预算和 PoC 验收见：[小红书旅游攻略查询工具规格说明与可行性研究](./xiaohongshu-guide-search-tool-spec-and-feasibility.md)。

| 项目 | 主要能力 | 活跃/成熟度观察 | 许可与风险 | 建议 |
|---|---|---|---|---|
| [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) | 本地 Streamable HTTP MCP；登录检查、笔记搜索、详情、作者、评论，也包含发布和互动 | Go + 浏览器，Docker/多平台构建，社区使用量较大 | 需要二维码登录和 Cookie；页面变化、账号风控；服务自身不应直接暴露公网 | **首选只读 PoC**；网关仅放行 `check_login_status`、`search_feeds`、`get_feed_detail`、`user_profile` |
| [YuriGao/xiaohongshu-mcp](https://github.com/YuriGao/xiaohongshu-mcp) | 真实浏览器操作，提供 MCP 与 REST；搜索筛选、详情、评论、主页 | Go 1.24+，Chrome/Chromium，可 Docker 部署 | 同样包含发布、评论、点赞等写能力；服务本身无鉴权 | 可作为第二实现对照；只监听 `127.0.0.1` 或 Docker 内网 |
| [DeliciousBuding/xiaohongshu-skill](https://github.com/DeliciousBuding/xiaohongshu-skill) | AgentSkills 规范的 `SKILL.md`；CLI 搜索、筛选、详情、评论与结构化 JSON 契约 | Python + Playwright；兼容 Codex/Claude Code/OpenClaw；安装浏览器约 300 MB | 包含发帖和互动；需要登录态；Linux 服务器通常只能无头运行 | **首选 Skill 形态验证**；只注册 `search`、`feed`、`user` 等只读命令 |
| [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 聚合网页、RSS、小红书、B站、微博等多平台后端并提供路由 Skill | 适合做“数据源路由器”与降级链参考 | 多一层依赖；不同后端的登录态、许可和稳定性仍需逐一审查 | 借鉴其 `doctor`、后端路由和降级设计，不建议 MVP 直接整体嵌入 |
| [DevinChen2014/xiaohongshu-xhs-rednote-mcp](https://github.com/DevinChen2014/xiaohongshu-xhs-rednote-mcp) | 托管只读 MCP；搜索、热榜、分享链接解析、详情、评论、作者和视频转写 | Streamable HTTP + Bearer Key，接入方便 | 仓库只公开连接说明，业务实现私有；价格、隐私、稳定性依赖第三方 | 仅作为用户自配的可选远程 Provider，不作为自主部署默认项 |
| [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 小红书、抖音、B站、微博、知乎等搜索、详情、评论、作者 | 大型社区，功能较全 | README 明确仅学习研究、禁止商业用途 | 只做隔离研究和数据结构参考 |
| [ShunL12324/xhs-mcp](https://github.com/ShunL12324/xhs-mcp) | 搜索、浏览、发布、互动、多账号 | TypeScript/Playwright，项目较新 | 依赖登录态和非公开能力 | PoC 候选，不进入生产主链路 |
| [Algovate/xhs-mcp](https://github.com/Algovate/xhs-mcp/) | CLI/MCP、搜索、推荐、发布、互动 | MCP 传输较完整 | 浏览器和账号风控风险 | 仅本地验证 |
| [haoyu-haoyu/xhs-mcp](https://github.com/haoyu-haoyu/xhs-mcp) | 搜索、阅读和分析 | 明确基于非公开接口 | 仅非商业学习许可 | 不可商用 |
| [aki66938/xhs-toolkit](https://github.com/aki66938/xhs-toolkit) | 创作、发布、创作者数据 | 偏创作者运营 | 需登录态 | 与攻略检索并不完全匹配 |

任何社区工具上线前至少检查：最近提交、Issue 响应、许可证、依赖漏洞、Cookie 存储、日志脱敏、浏览器隔离、限速、平台协议和法务意见。不要实现验证码绕过、设备指纹规避或封禁对抗。

### 6.4.1 已有旅游攻略 Skill 可借鉴的部分

| 项目 | 有价值的能力 | 不应误判为 |
|---|---|---|
| [aleczhanshi/xiami](https://github.com/aleczhanshi/xiami) | 已拆分 `scrape-xhs`、单笔记总结、携程机票、酒店实价、路线和 HTML 输出等 Skill；非常接近本项目的数据采集流程 | 稳定的官方携程/小红书 API。其核心仍是浏览器自动化和小红书 MCP |
| [ErikaAlk/trip-planner](https://github.com/ErikaAlk/trip-planner) | 强调多篇攻略互证、软广识别、携程/飞猪价格双源、高德路线实测和“查不到就明确降级” | 可直接复用的数据服务。它更接近严谨的 Agent 工作规约和验证器 |
| [XiaoiYuyao/travel-agent-skill](https://github.com/XiaoiYuyao/travel-agent-skill) | 行程、预算、交通、餐厅、地图和移动端外链的输出结构 | 自动读取小红书/点评的连接器。其重点是联网研究和平台跳转链接 |
| [huanyuzhilv/skills-travel-planner](https://github.com/huanyuzhilv/skills-travel-planner) | `tripData.json`、HTML/PDF 路书、小红书配图和 DeepSeek 接入方式 | 免费自托管的小红书数据源；小红书部分依赖 TikHub Key |

这些项目更适合用来提炼 **Skill 契约、证据校验、降级规则和输出结构**，而不是整套复制。尤其是任何声称“携程实价”或“小红书搜索”的 Skill，都必须继续追踪到底层是官方合作 API、第三方付费 API、浏览器读取还是非公开接口。

### 6.4.2 官方与第三方接口的现实边界

| 平台/接口 | 当前能确认的开放能力 | 能否直接搜索普通用户攻略 | 本项目定位 |
|---|---|---|---|
| [小红书账号开放平台](https://openaccount.xiaohongshu.com/docs/quick-start) | 首期为 OAuth 登录和最小用户资料 | **不能** | 可选登录能力，与攻略采集分开 |
| [小红书分享开放平台](https://agora.xiaohongshu.com/) | 向小红书分享图文/视频 | **不能** | 未来导出/分享扩展 |
| [马蜂窝开放平台](https://open.mafengwo.cn/support/) | 旅行商城供应商、酒店、门票、订单和部分 POI 接口 | 未发现面向普通开发者的全站游记/攻略检索 | 只做来源跳转或将来商务接入；酒店 POI 接口不等于攻略库 |
| [美团生态开放平台](https://openapi.meituan.com/) | 本地生活合作接口；需申请合作、评估和联调 | 不属于匿名公众内容 API | 小型自用系统不作为首发依赖 |
| [美团点评 POI 数据接口](https://poiopen.dianping.com/instructions/doc/poi.html) | 授权城市 POI 扫描、详情、变更通知等 | 不是通用点评搜索；需要签名和开放范围 | 有资质后可作为 POI 数据补充 |
| [美团企业版到餐 API](https://h5.dianping.com/app/bep-docs/sky-doc/canyinopenapi/daocan_api.html) | 商家、菜品、详情和评论等企业服务接口 | 需要企业/渠道接入，并非公开免费点评 API | 不符合当前“无需商业合作”的优先级 |
| [马蜂窝酒店 POI 查询](https://open.mafengwo.cn/docs/api/326.html) | 酒店业务中的 POI 名称检索，默认 30 次/分钟 | **不能**替代游记/攻略搜索 | 仅在对应供应商合作场景使用 |
| SocialDataX / TikHub 等第三方 | 可封装小红书搜索、详情、评论或图片 | 技术上可能可以 | 作为可插拔付费 Provider；先核价、隐私、许可和 SLA，不写死到核心业务 |

结论是：目前没有一个“申请免费 Key 后即可长期、稳定、合规搜索小红书/携程/马蜂窝/大众点评全部攻略”的统一官方 API。MVP 必须按多个来源、多个风险等级设计，而不能把某个社区抓取器当作基础数据库。

### 6.4.3 本项目推荐的攻略检索适配层

内部统一接口建议只暴露只读语义，不直接暴露社区工具原始工具名：

```text
GuideSourceAdapter
├─ search_guides(query, filters, limit) -> GuideSearchResult[]
├─ resolve_shared_link(url)             -> GuideReference
├─ fetch_guide(reference, options)      -> GuideDocument
├─ fetch_comments(reference, limit)     -> GuideComment[]
└─ health()                             -> ProviderHealth
```

第一阶段 Provider 顺序：

1. `user_input`：用户粘贴的正文、截图、分享链接；
2. `web_search`：公开网页搜索、目的地官方站、文旅站、可索引的攻略链接；
3. `xhs_local_mcp`：用户主动开启后，按次启动的本地小红书浏览器 MCP；
4. `remote_social_provider`：用户自行配置 Key 的托管 MCP/API；
5. `manual_linkout`：无法读取时返回小红书、携程、马蜂窝、点评等移动端搜索/查看链接。

统一返回至少包含：`source_platform`、`source_url`、`title`、`author`、`published_at`、`retrieved_at`、`excerpt`、`engagement_snapshot`、`claims[]`、`content_hash`、`confidence`、`access_method` 和 `rights_policy`。默认长期保存结构化观点、摘要、引用位置和原链接，不永久复制整篇正文与全部图片。

MCP 网关必须做到：

- 只读工具白名单；发布、评论、点赞、收藏、删除 Cookie 一律不注册给规划 Agent；
- 每用户独立 Cookie/浏览器 Profile，加密存储，管理员不能查看明文；
- 仅绑定 Docker 内网或 `127.0.0.1`，由主服务鉴权和审计；
- 用户主动查询才启动浏览器 Sidecar，结束后自动停止，避免空闲内存超标；
- 限制每次关键词数、结果数、评论数、并发和最短间隔；验证码或风险提示出现时立即暂停并由用户处理；
- 外部内容全部作为不可信数据，清除提示注入式指令后再交给模型。

浏览器型 Skill/MCP 通常会额外占用数百 MB 内存，因此不应常驻。在本项目“空闲低于 512 MB、峰值低于 2 GB”的约束下，建议同一时间最多运行一个 Chromium Sidecar，并限制页面数和评论展开量。

## 6.5 其他攻略渠道

- 马蜂窝适合作为攻略来源和跳转目标，但[马蜂窝开放平台](https://open.mafengwo.cn/)当前更偏商城商家和定制咨询，不应默认存在通用攻略搜索 API；
- B 站/微博/知乎的公开内容也可以作为经验来源，但同样需要链接回源和版权边界；
- 目的地文旅局、景区公众号/小程序、博物馆预约平台应优先用于营业和预约事实；
- 对攻略中的“价格”应提取为线索，并用地图、官方票务或 OTA 再验证。

## 7. MCP 与 Skill 市场

## 7.1 官方地图 MCP

### 高德 MCP Server

[高德 MCP Server](https://lbs.amap.com/api/mcp-server/summary)提供地理编码、天气、POI、步行/骑行/驾车/公交路线、距离测量，并能：

- 生成专属地图唤端链接；
- 导航到目的地；
- 生成打车唤端链接；
- 把模型行程点位导入高德 App。

PoC 阶段可直接使用官方 MCP 快速验证 Agent 工具调用；生产阶段建议通过自己的 `MapProviderAdapter` 调用 REST API，并把 MCP 作为模型侧工具协议，而不是让业务完全耦合官方工具名。

### 百度 MCP Server

[百度地图官方 MCP GitHub](https://github.com/baidu-maps/mcp)为 MIT 许可，包含 POI、详情、路线、矩阵、天气、路况等工具；[官方快速接入文档](https://lbs.baidu.com/docs/ai?title=mcpserver%2Fquickstart)提供远程 Streamable HTTP、SSE、npm 和 pip 方式。

适合用作：

- 第二地图供应商的快速接入；
- 路线和 POI 的对照实验；
- MCP 网关兼容性测试。

### 腾讯位置服务 MCP

[腾讯位置服务 MCP](https://developer.cloud.tencent.com/mcp/server/11471)覆盖沿途搜索、途经点智能排序、未来路线、公交票价和距离矩阵。其底层仍受腾讯 WebService 权限和配额约束，不能把“安装 MCP”理解为绕过 API 商业授权。

## 7.2 可检索市场

- [Official MCP Registry](https://registry.modelcontextprotocol.io/)：官方中心化元数据仓库，目前仍处于预览阶段；注册不等于安全认证；
- [Smithery](https://www.smithery.ai/)：MCP 发现、连接和凭证管理；
- [SkillsMP](https://skillsmp.com/)：检索公开 `SKILL.md`，提供 REST API 和只读 MCP；
- [Docker MCP Registry](https://github.com/docker/mcp-registry)：适合容器化 MCP 的发现与运行；
- GitHub 关键词：`travel mcp server`、`maps mcp`、`12306 mcp`、`xiaohongshu mcp`、`travel SKILL.md`。

安全要求：市场条目只用于发现，不用于建立信任。安装前必须固定版本/提交哈希、审查代码和依赖、限制网络/文件/密钥权限，并在隔离环境运行。

## 8. GitHub 开源数据工具调研

## 8.1 推荐清单

| 工具 | 用途 | 当前判断 | 生产建议 |
|---|---|---|---|
| [baidu-maps/mcp](https://github.com/baidu-maps/mcp) | 官方百度地图 MCP | 官方、MIT、能力清晰 | 可进入 PoC 和生产候选 |
| 高德官方 MCP | 高德 POI、路线、专属地图 | 官方托管能力 | 可进入 PoC；生产确认配额和许可 |
| [drfccv/mcp-server-12306](https://github.com/drfccv/mcp-server-12306) | 12306 只读查询 MCP | 功能完整、社区项目 | 仅低频 PoC；无官方 SLA |
| [HansBug/china-railway-12306](https://github.com/HansBug/china-railway-12306) | 12306 只读 Skill/CLI | 代码小、边界声明清楚 | 适合验证 Skill 形态，不做售票 |
| [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 多平台社区内容研究 | 活跃且覆盖广 | 明确禁止商业使用，不进入生产 |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | 通用网页转 Markdown、RAG 提取 | 活跃、能力强 | 使用 0.9.0+；Docker API 曾有多项高危漏洞，必须隔离和鉴权 |
| [Firecrawl](https://github.com/firecrawl/firecrawl) | 搜索、抓取、结构化、MCP | 活跃，可云服务或自部署 | 自部署许可、成本与数据合规需评估 |
| [Playwright](https://github.com/microsoft/playwright) | 浏览器自动化底座 | 官方、稳定 | 适合用户授权浏览器和内部测试，不代表可绕过网站规则 |
| [Scrapy](https://github.com/scrapy/scrapy) | 传统结构化爬虫框架 | 成熟 | 只抓获准站点；适合自有/合作数据源 |
| [RSSHub](https://github.com/DIYgod/RSSHub) | 将部分公开更新转换为 RSS | 社区活跃 | 路由可用性与站点授权逐项确认 |

## 8.2 开源工具准入门槛

进入生产前必须满足：

- 许可证允许商业使用；
- 最近 6～12 个月仍有维护，且高危漏洞有修复版本；
- 有明确超时、限速、重试、缓存和熔断；
- 不要求保存用户主账号密码；
- Cookie 加密存储，按用户与任务隔离；
- URL 白名单和 SSRF 防护；
- 禁止访问内网、云元数据地址和本地文件；
- 抽取内容进行提示注入过滤，外部网页不能变成 Agent 指令；
- 记录来源和时间，不把抓取结果伪装成官方 API；
- 站点条款、robots、版权、个人信息和数据库权益通过审核。

## 8.3 不提供开放 API 时的建议流程

```text
官方/合作 API
  ↓ 不可用
官方页面深链或 H5 嵌入
  ↓ 仍不能满足
用户主动提供 URL/文件/截图
  ↓ 需要自动读取
用户授权的隔离浏览器、低频单页提取
  ↓ 仅研究验证
社区工具 PoC（不得成为商用核心依赖）
```

开源工具解决的是技术可访问性，不自动解决合法性、稳定性、数据授权和商业 SLA。

## 9. 移动端与链接跳转设计

## 9.1 推荐形态

首版建议响应式 H5/PWA，后续再决定是否用 Flutter/React Native 开发 App。原因：

- 攻略分享和外部链接跳转更自然；
- 微信、短信和浏览器可直接打开；
- 更新速度快，适合需求验证；
- 可逐步接入地图 URI、OTA H5、小程序和 Universal/App Links。

## 9.2 每个行程卡片的操作

移动端行程卡至少应包含：

- 查看地点详情；
- 在高德/百度地图中查看；
- 从当前位置开始导航；
- 打车前往；
- 查看公交/步行替代路线；
- 打开景区、餐厅、酒店或 OTA 预订页；
- 查看攻略来源；
- 标记到达、完成、跳过；
- 上传或拍摄票据；
- 重新规划后续行程。

## 9.3 地图唤端

高德：

- [Web URI 路线规划](https://lbs.amap.com/api/uri-api/guide/travel/route)；
- `amapuri://` 原生路线/导航；
- 官方 MCP 可返回专属地图、导航和打车链接。

百度：

- [Web 地图调起 API](https://lbsyun.baidu.com/docs/webapi?title=mapadjustment%2Furi%2Fweb)；
- `baidumap://` 原生路线；
- Android/iOS SDK 可调起百度地图并配置 WebApp 回退。

实现原则：

- 页面中同时提供主按钮和“其他地图”菜单；
- 先尝试 Universal/App Link 或 HTTPS，必要时使用 scheme；
- 1～2 秒未成功唤端时展示 Web 路线；
- 微信/QQ 中提示“在浏览器打开”，避免用户点击无反应；
- 不在 URL 中放身份证、手机号、精确家庭住址等敏感数据；
- 短链必须是自有可审计跳转服务，防止开放重定向。

## 9.4 坐标管理

统一内部对象：

```json
{
  "lat": 39.9087,
  "lng": 116.3975,
  "coord_system": "GCJ02",
  "provider": "amap",
  "provider_poi_id": "...",
  "entrance_type": "main_gate"
}
```

必须明确 WGS-84、GCJ-02、BD-09。转换时记录来源坐标系，不允许把百度经纬度直接传给高德。大型景区、机场、车站要保存“地点中心点”和“导航入口点”，避免路线落在建筑另一侧。

## 10. 技术架构建议

## 10.1 分层架构

```text
移动 H5 / App / 小程序
        │
旅行会话与行程 API
        │
Agent Orchestrator
  ├─ 需求结构化 Agent
  ├─ 候选 POI/攻略 Agent
  ├─ 路线规划 Agent
  ├─ 预算 Agent
  ├─ 合理性审计 Agent
  └─ 行中重排 Agent
        │
确定性领域服务
  ├─ Map Provider Adapter
  ├─ Travel Inventory Adapter
  ├─ Price & Budget Engine
  ├─ Route Optimizer
  ├─ Evidence/RAG Service
  ├─ Deep Link Service
  └─ Expense Ledger
        │
高德 / 百度 / 腾讯 / OTA / 官方站点 / 受控浏览器
```

不要让大模型直接拼第三方 URL 或自行理解供应商 JSON。每个外部接口通过适配器变成稳定的内部 Schema，并在工具层做参数校验、权限、预算和审计。

## 10.2 Provider Adapter 示例

```ts
interface MapProvider {
  geocode(query: GeocodeInput): Promise<PlaceCandidate[]>;
  searchPlaces(query: PoiSearchInput): Promise<Poi[]>;
  getPlaceDetail(id: ProviderPoiId): Promise<PoiDetail>;
  planRoute(input: RouteInput): Promise<RouteOption[]>;
  routeMatrix(input: MatrixInput): Promise<RouteMatrix>;
  createDeepLink(input: DeepLinkInput): Promise<DeepLinkResult>;
}
```

`RouteOption` 应统一为：

- 距离和时长；
- 过路费、公交票价、出租车估价；
- 路线段和换乘；
- 路况、限制和告警；
- 原始供应商与查询时间；
- 估算置信度；
- 可导航链接。

## 10.3 路线优化

大模型适合提出景点候选，不适合独立求最优访问顺序。建议：

1. 用地图矩阵得到点到点耗时；
2. 用规则过滤闭馆、时间窗和不可达点；
3. 使用 OR-Tools 等求解带时间窗的车辆路径/行程问题；
4. 将多个可行解交给模型解释风格差异；
5. 用户选择后再调用精确路线 API 获取逐段路线。

目标函数可以组合：总交通时间、费用、折返、体力、偏好得分和不确定性惩罚，而不是只追求最短距离。

## 10.4 缓存与刷新

建议 TTL：

- 地理编码/基础 POI：7～30 天，营业状态更短；
- 路线距离：1～24 小时，实时路况 5～15 分钟；
- 天气：1～3 小时；
- 机票/酒店/门票报价：以供应商过期时间为准，通常分钟级；
- 攻略摘要：可较长，但展示原文发布时间和抓取时间；
- 实际消费：永久保存，允许用户修订。

出发前 24 小时和当天应自动重新验证关键路线、天气、营业和已选价格，但自动刷新不应擅自改动已确认订单。

## 11. 实际消费归档

建议支持：

- 手工记账；
- 票据 OCR；
- 支付截图/电子发票导入；
- 订单邮件或短信的用户授权导入；
- 多人垫付和 AA 分账；
- 计划项与实际消费自动匹配；
- 退款、押金、预授权、外币和汇率；
- 预算剩余和超支告警；
- 行程结束后的分类报表与复盘。

关键数据模型：`Expense`、`Payment`、`ParticipantShare`、`Receipt`、`Refund`、`PlanCostLink`。实际支付金额永远不能被新的地图估价覆盖。

## 12. 数据质量、安全与合规

### 12.1 质量

- 每条关键事实附来源、查询时间和置信度；
- 价格过期后明显标红，不静默沿用；
- 多来源冲突时展示冲突，不让模型任意选一个；
- 行程生成后运行独立审计 Agent/规则引擎；
- 监控路线无结果率、POI 误匹配率、价格缺失率和用户改动率。

### 12.2 隐私

- 家庭住址默认只在生成首末段时使用，可让用户改成附近地标；
- 身份证、护照和儿童信息最小化存储；
- 第三方密钥只在服务端；
- OAuth Token、Cookie 和票据图片加密并支持删除；
- 不把用户敏感数据发送给与当前任务无关的 MCP Server。

### 12.3 Agent 与 MCP 安全

- 第三方 MCP 工具采用白名单和最小权限；
- 工具调用前做参数 Schema、目的域名和预算校验；
- 外部网页、攻略和工具描述均视为不可信输入，防止提示注入；
- 下单、支付、发布内容、删除数据必须二次确认；
- 记录工具名、版本、输入摘要、输出摘要和费用；
- 社区 MCP 固定版本并在隔离容器运行。

### 12.4 商业授权

[高德商务合作说明](https://lbs.amap.com/cooperation/cooperation/)明确商业目的需事先获取商用授权/技术服务许可；百度的 POI 图片、营业状态和部分高级能力也要求商用授权。PoC 免费配额不能推导出正式上线成本。采购阶段应让供应商书面确认：

- 使用场景是否属于商业使用；
- 日配额、QPS、超额价格和 SLA；
- 是否允许缓存、派生计算、展示和跨终端使用；
- POI 评分、价格、图片、评论和营业字段的授权范围；
- 地图 Logo、审图号和归属标识要求；
- 用户数据回传和隐私合规要求。

## 13. 分阶段实施建议

## Phase 0：两周技术验证

- 高德与百度 API Key、MCP 接入；
- 60 条黄金路线对比；
- POI 搜索、详情、人均价、评分、营业字段抽样；
- H5 行程卡与高德/百度唤端；
- 预算引擎最小模型；
- 用户粘贴攻略链接的结构化提取；
- 12306 社区工具仅做隔离只读实验。

交付标准：输出可复现测试报告，不只展示 Demo。

## Phase 1：MVP

- 单次国内多日旅行；
- 家门口到返回的全过程路线；
- 高德主地图和百度故障回退；
- 三档预算与多人分摊；
- 景点、餐厅、住宿候选及来源链接；
- 合理性审计和一键局部调整；
- H5 分享、导航、打车和预订跳转；
- 手工/票据消费归档。

MVP 暂不做自动下单，不把小红书爬虫作为在线依赖。

## Phase 2：交易与行中服务

- 选择一家 OTA/本地生活平台完成正式商务 API 接入；
- 实时机票、酒店、门票报价和订单同步；
- 行中天气、延误、闭馆、超支提醒；
- 多人协作、投票、垫付与 AA；
- 官方小程序/合作渠道接入；
- 关键事件局部重排。

## Phase 3：平台化

- Provider Marketplace；
- MCP 网关和内部 Skill 市场；
- 旅行社、企业差旅和定制师工作台；
- 内容合作方数据接入；
- 国际地图、航旅、评价和多币种扩展。

## 14. 海外扩展预留

国内数据适配层不能写死供应商、币种和票种。海外可预留：

- Google Maps Routes API：路线、收费信息和部分燃油消耗能力；
- [Mapbox](https://docs.mapbox.com/api/navigation/matrix/)：Directions、Matrix、Optimization、Map Matching；
- [Amadeus Self-Service APIs](https://developers.amadeus.com/self-service/apis-docs)：航班、酒店、活动和接送；
- [Tripadvisor Developers](https://www.tripadvisor.com/developers)：评价内容合作；注意其旧 Content API 于 2026-08-31 停止，需评估新 Terra/Partner 方案；
- Trip.com 国际合作接口；
- OpenStreetMap + OSRM/GraphHopper/OpenTripPlanner 作为特定地区的自托管候选。

需要预留：多币种、税费、服务费、小费、时区、夏令时、国际驾照、签证、护照、跨境漫游、右舵/左舵、国际地址和本地紧急电话。

## 15. 建议立即发起的商务与技术问题清单

### 向高德询问

- 路径规划 2.0、POI `rating/cost`、专属地图、打车链接的商业授权和缓存范围；
- 企业配额、QPS、SLA、超额计费；
- 出租车估价是否包含高速费、夜间费及支持城市；
- 专属地图链接的有效期、点位数量和品牌展示限制；
- 海外路线权限与价格。

### 向百度询问

- Direction v2、POI 价格/评分/建议游玩时长的授权范围；
- POI 图片、营业状态和详细字段的商用套餐；
- 官方 MCP 与 REST API 的配额是否共享；
- 未来路线、矩阵、摩托车和跨城交通的价格与 SLA。

### 向 OTA/本地生活平台询问

- 是否接受 AI 行程规划平台作为分销/导流合作方；
- 可开放的搜索、报价、库存、下单、退款和订单回调范围；
- H5 深链、Affiliate、API 和小程序的可用模式；
- 价格缓存时间、归因参数、佣金、结算和客服责任；
- 是否可展示评价摘要、图片和评分。

## 16. 最终选型建议表

| 能力 | MVP 选择 | 生产目标 | 风险级别 |
|---|---|---|---|
| 地图展示/算路 | 高德 API + 官方 MCP 验证 | 高德商用许可 | 中 |
| 地图回退/校验 | 百度 API + 官方 MCP | 百度正式配额 | 中 |
| 微信生态补充 | 暂不接 | 腾讯位置服务评估 | 低 |
| POI 人均与评分 | 高德主、百度补 | 商务授权与抽样校验 | 中 |
| 门票/酒店/机票实时价 | 外链跳转 | 一家 OTA 正式 API | 高 |
| 高铁票 | 12306/OTA 跳转 | 合作渠道 | 高 |
| 小红书攻略 | 用户粘贴链接 + 回源 | 官方合作或受控授权流程 | 高 |
| 通用网页提取 | Playwright/Crawl4AI 隔离 PoC | 自建受控提取服务 | 中高 |
| 预算计算 | 自研确定性引擎 | 规则 + 报价 + 实付对账 | 低 |
| 实际消费 | 手工/OCR | 订单与支付授权导入 | 中高 |

## 17. 验收指标建议

- 关键路线可达率 ≥ 98%；
- 起终点入口正确率 ≥ 95%；
- 费用项漏项率 ≤ 3%；
- 人数/房间/车辆分摊计算正确率 = 100%；
- 行程时间冲突检出率 ≥ 95%；
- 过期价格被识别率 = 100%；
- 每条关键推荐均能展示来源和查询时间；
- 唤端成功或 Web 回退成功率 ≥ 99%；
- 外部工具失败时不生成虚构价格或虚构可订状态；
- 用户能在两步内从行程卡进入导航或预订页面。

## 18. 调研来源索引

### 国内地图

- [高德路径规划 2.0](https://lbs.amap.com/api/webservice/guide/api/newroute)
- [高德 POI 搜索](https://lbs.amap.com/api/webservice/guide/api/search/)
- [高德 URI 路线规划](https://lbs.amap.com/api/uri-api/guide/travel/route)
- [高德 MCP Server](https://lbs.amap.com/api/mcp-server/summary)
- [高德流量限制说明](https://lbs.amap.com/api/webservice/guide/tools/flowlevel)
- [高德商务合作](https://lbs.amap.com/cooperation/cooperation/)
- [百度 Direction API](https://lbsyun.baidu.com/docs/webapi?title=directionv2%2Fdirection-api-v2)
- [百度地点检索 v3](https://lbsyun.baidu.com/docs/webapi?title=placev3%2Fguide%2Fwebservice-placeapiV3%2FinterfaceDocumentV3)
- [百度地图调起 API](https://lbsyun.baidu.com/docs/webapi?title=mapadjustment%2Furi)
- [百度官方 MCP Server](https://github.com/baidu-maps/mcp)
- [腾讯位置服务 MCP](https://developer.cloud.tencent.com/mcp/server/11471)

### 旅游与本地生活

- [携程旅游/玩乐开放平台](https://ttdopen.ctrip.com/)
- [携程商旅开发者平台](https://openapi.ctripbiz.com/)
- [Trip.com 开发者中心](https://developers.trip.com/?lang=zh-CN)
- [飞猪开放平台](https://open.fliggy.com/)
- [美团生态开放平台](https://openapi.meituan.com/)
- [美团餐饮直连](https://developer.dianping.com/)
- [美团酒店直连](https://openplatform-hotel.meituan.com/portal/process-chart)
- [12306 官方网站](https://www.12306.cn/index/)
- [厦门航空开放平台](https://open.xiamenair.com/portal/index)

### 小红书、MCP 与开源工具

- [小红书账号开放平台](https://openaccount.xiaohongshu.com/docs/api-reference)
- [小红书小程序开放平台](https://miniapp.xiaohongshu.com/)
- [小红书分享开放平台](https://agora.xiaohongshu.com/)
- [Official MCP Registry](https://registry.modelcontextprotocol.io/)
- [Smithery](https://www.smithery.ai/)
- [SkillsMP](https://skillsmp.com/)
- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)
- [Crawl4AI](https://github.com/unclecode/crawl4ai)
- [Firecrawl](https://github.com/firecrawl/firecrawl)
- [MCP Server 12306](https://github.com/drfccv/mcp-server-12306)

---

### 文档维护建议

每月自动检查一次所有官方文档和 GitHub 项目的状态；每季度复测地图黄金路线；每次第三方平台条款、价格或配额变化后更新本文件。所有“可用”结论必须标明最后实测日期，避免把网页仍存在误认为接口仍适合生产。
