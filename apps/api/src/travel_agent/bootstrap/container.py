from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from travel_agent.bootstrap.settings import Settings, get_settings
from travel_agent.modules.access.application.invite_service import FamilyInviteService
from travel_agent.modules.access.application.member_service import FamilyMemberService
from travel_agent.modules.access.application.service import AccessService
from travel_agent.modules.access.infrastructure.invite_store import SqlAlchemyInviteStore
from travel_agent.modules.access.infrastructure.member_store import SqlAlchemyMemberStore
from travel_agent.modules.access.infrastructure.rate_limit import LoginRateLimiter
from travel_agent.modules.access.infrastructure.security import (
    AesGcmTextProtector,
    Argon2idHasher,
    SecureTokenIssuer,
    SystemClock,
    resolve_protection_key,
)
from travel_agent.modules.access.infrastructure.store import SqlAlchemyAccessStore
from travel_agent.modules.conversations.infrastructure import SqlAlchemyConversationStore
from travel_agent.modules.conversations.provider import DeepSeekChatProvider, DisabledChatProvider
from travel_agent.modules.conversations.service import ConversationService
from travel_agent.modules.itinerary.application.ports import ItineraryStore
from travel_agent.modules.itinerary.application.service import ItineraryService
from travel_agent.modules.itinerary.infrastructure.store import SqlAlchemyItineraryStore
from travel_agent.modules.knowledge.provider import PlaceKnowledgeProvider
from travel_agent.modules.knowledge.service import KnowledgeService, KnowledgeStore
from travel_agent.modules.knowledge.store import SqlAlchemyKnowledgeStore
from travel_agent.modules.knowledge.vision import DeepSeekVisionProvider
from travel_agent.modules.operations.application.health import HealthService
from travel_agent.modules.operations.infrastructure.health_checks import (
    DatabaseReadinessCheck,
    DirectoryReadinessCheck,
    MasterKeyReadinessCheck,
)
from travel_agent.modules.planning.application.ports import PlanningStore
from travel_agent.modules.planning.application.service import PlanningService
from travel_agent.modules.planning.infrastructure.provider import (
    DeepSeekProvider,
    DisabledModelProvider,
)
from travel_agent.modules.planning.infrastructure.store import SqlAlchemyPlanningStore
from travel_agent.modules.tools.domain import ToolDescriptor
from travel_agent.modules.tools.providers import (
    AmapProvider,
    GuideLibraryProvider,
    QWeatherProvider,
    XiaohongshuMcpProvider,
)
from travel_agent.modules.tools.runtime import RegisteredTool, ToolGateway
from travel_agent.modules.tools.store import SqlAlchemyToolStore
from travel_agent.modules.trips.application.ports import TripStore
from travel_agent.modules.trips.application.service import TripService
from travel_agent.modules.trips.infrastructure.store import SqlAlchemyTripStore
from travel_agent.shared.infrastructure.db.database import Database


@dataclass(slots=True)
class Container:
    settings: Settings
    database: Database
    health_service: HealthService
    access_service: AccessService
    family_member_service: FamilyMemberService
    family_invite_service: FamilyInviteService
    trip_service: TripService
    itinerary_service: ItineraryService
    planning_service: PlanningService
    conversation_service: ConversationService
    tool_gateway: ToolGateway
    knowledge_service: KnowledgeService
    login_rate_limiter: LoginRateLimiter
    invite_registration_rate_limiter: LoginRateLimiter

    async def startup(self) -> None:
        self.settings.ensure_runtime_directories()
        await self.database.ping()

    async def shutdown(self) -> None:
        await self.database.dispose()


def build_container(settings: Settings | None = None) -> Container:
    resolved_settings = settings or get_settings()
    database = Database.from_settings(resolved_settings)
    protector = AesGcmTextProtector(resolve_protection_key(resolved_settings))

    def store_factory() -> SqlAlchemyAccessStore:
        return SqlAlchemyAccessStore(database.session_factory, protector)

    def member_store_factory() -> SqlAlchemyMemberStore:
        return SqlAlchemyMemberStore(database.session_factory, protector)

    def invite_store_factory() -> SqlAlchemyInviteStore:
        return SqlAlchemyInviteStore(database.session_factory, protector)

    def trip_store_factory() -> TripStore:
        return SqlAlchemyTripStore(database.session_factory, protector)

    def itinerary_store_factory() -> ItineraryStore:
        return SqlAlchemyItineraryStore(database.session_factory, protector)

    def planning_store_factory() -> PlanningStore:
        return SqlAlchemyPlanningStore(database.session_factory, protector)

    def tool_store_factory() -> SqlAlchemyToolStore:
        return SqlAlchemyToolStore(database.session_factory, protector)

    def knowledge_store_factory() -> KnowledgeStore:
        return SqlAlchemyKnowledgeStore(database.session_factory, protector)

    password_hasher = Argon2idHasher()
    token_issuer = SecureTokenIssuer()
    access_service = AccessService(
        store_factory=store_factory,
        password_hasher=password_hasher,
        token_issuer=token_issuer,
        clock=SystemClock(),
        session_lifetime=timedelta(days=resolved_settings.session_lifetime_days),
    )
    deepseek_key = resolved_settings.deepseek_api_key
    model_provider = (
        DeepSeekProvider(
            deepseek_key.get_secret_value(),
            resolved_settings.deepseek_base_url,
            resolved_settings.deepseek_model,
            resolved_settings.model_test_timeout_seconds,
            resolved_settings.model_planning_max_output_tokens,
        )
        if deepseek_key is not None and resolved_settings.deepseek_model
        else DisabledModelProvider()
    )
    chat_provider = (
        DeepSeekChatProvider(
            deepseek_key.get_secret_value(),
            resolved_settings.deepseek_base_url,
            resolved_settings.deepseek_model,
            resolved_settings.model_test_timeout_seconds,
            resolved_settings.model_planning_max_output_tokens,
        )
        if deepseek_key is not None and resolved_settings.deepseek_model
        else DisabledChatProvider()
    )
    amap_key = _secret(resolved_settings.amap_web_service_key)
    qweather_key = _secret(resolved_settings.qweather_api_key)
    amap_provider = AmapProvider(amap_key, resolved_settings.external_tool_timeout_seconds)
    registered_tools: list[RegisteredTool] = []
    registered_tools.append(
        RegisteredTool(
            ToolDescriptor(
                "guide_library_search",
                (
                    "检索用户已经选择并下载的私人攻略库。"
                    "在制定或讨论计划前, 优先用它查找用户确认过的攻略内容。"
                ),
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "要检索的主题或地点"},
                        "city": {"type": "string", "description": "可选城市"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "local_guide_library",
                60,
                0,
            ),
            GuideLibraryProvider(tool_store_factory),
            "检索私人攻略库",
            private_scope=True,
        )
    )
    if amap_key:
        registered_tools.extend(
            [
                RegisteredTool(
                    ToolDescriptor(
                        "place_search",
                        "查询中国境内景点、餐厅、酒店、车站等地点。需要精确地点、地址、坐标或地图评分时使用。",
                        {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "地点或分类关键词"},
                                "city": {"type": "string", "description": "城市名, 建议提供"},
                            },
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                        "amap",
                        resolved_settings.map_cache_ttl_seconds,
                        resolved_settings.external_cache_stale_seconds,
                    ),
                    amap_provider,
                    "查询高德地点",
                ),
                RegisteredTool(
                    ToolDescriptor(
                        "route_quote",
                        "查询两个中国境内地点之间的驾车、步行或公交路线时长、距离和费用线索。",
                        {
                            "type": "object",
                            "properties": {
                                "origin": {"type": "string"},
                                "destination": {"type": "string"},
                                "city": {"type": "string"},
                                "mode": {
                                    "type": "string",
                                    "enum": ["driving", "walking", "transit"],
                                },
                            },
                            "required": ["origin", "destination"],
                            "additionalProperties": False,
                        },
                        "amap",
                        resolved_settings.route_cache_ttl_seconds,
                        resolved_settings.external_cache_stale_seconds,
                    ),
                    amap_provider,
                    "计算高德路线",
                ),
            ]
        )
    if resolved_settings.qweather_api_host and qweather_key:
        registered_tools.append(
            RegisteredTool(
                ToolDescriptor(
                    "weather_forecast",
                    "查询中国城市未来三天天气。天气默认只用于提示, 不应擅自大幅修改行程。",
                    {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                        "additionalProperties": False,
                    },
                    "qweather",
                    resolved_settings.weather_cache_ttl_seconds,
                    resolved_settings.external_cache_stale_seconds,
                ),
                QWeatherProvider(
                    resolved_settings.qweather_api_host,
                    qweather_key,
                    resolved_settings.external_tool_timeout_seconds,
                ),
                "查询和风天气",
            )
        )
    if resolved_settings.xhs_research_enabled:
        xhs_provider = XiaohongshuMcpProvider(
            resolved_settings.xhs_mcp_endpoint,
            resolved_settings.xhs_search_timeout_seconds,
            resolved_settings.xhs_max_results_per_query,
        )
        registered_tools.extend(
            [
                RegisteredTool(
                    ToolDescriptor(
                        "guide_search_xhs",
                        (
                            "使用用户主动启用的只读 Worker 搜索小红书旅游攻略。"
                            "结果仅作为社区经验, 不是实时事实。"
                        ),
                        {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                        "xiaohongshu",
                        resolved_settings.xhs_search_cache_ttl_seconds,
                        resolved_settings.external_cache_stale_seconds,
                    ),
                    xhs_provider,
                    "搜索小红书攻略",
                    private_scope=True,
                ),
                RegisteredTool(
                    ToolDescriptor(
                        "guide_detail_xhs",
                        "读取用户已选择的小红书攻略正文、图片、互动摘要和部分评论。",
                        {
                            "type": "object",
                            "properties": {
                                "feed_id": {"type": "string"},
                                "xsec_token": {"type": "string"},
                            },
                            "required": ["feed_id", "xsec_token"],
                            "additionalProperties": False,
                        },
                        "xiaohongshu",
                        resolved_settings.xhs_detail_cache_ttl_seconds,
                        resolved_settings.external_cache_stale_seconds,
                    ),
                    xhs_provider,
                    "下载小红书攻略详情",
                    private_scope=True,
                    expose_to_model=False,
                ),
            ]
        )
    vision_provider = DeepSeekVisionProvider(
        deepseek_key.get_secret_value() if deepseek_key is not None else "",
        resolved_settings.deepseek_base_url,
        resolved_settings.deepseek_vision_model,
        resolved_settings.vision_timeout_seconds,
        resolved_settings.vision_analysis_enabled,
    )
    knowledge_service = KnowledgeService(knowledge_store_factory, vision_provider, SystemClock())
    registered_tools.append(
        RegisteredTool(
            ToolDescriptor(
                "place_knowledge_search",
                (
                    "检索已沉淀的景点、餐厅、酒店和交通枢纽资料卡。"
                    "规划地点或解释行程节点前优先使用, 可复用坐标和已核验信息。"
                ),
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "地点名称关键词"},
                        "city": {"type": "string", "description": "可选城市"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "local_place_knowledge",
                60,
                0,
            ),
            PlaceKnowledgeProvider(knowledge_service),
            "检索地点知识卡",
            private_scope=True,
        )
    )
    registered_tools.append(
        RegisteredTool(
            ToolDescriptor(
                "place_knowledge_upsert",
                (
                    "把地图、已下载攻略或用户资料中的地点事实合并到地点知识卡。"
                    "仅在本轮已有明确证据来源时使用; 不得根据模型记忆编造。"
                    "该卡片是建议知识, 不会直接修改正式行程。"
                ),
                {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "city": {"type": "string"},
                        "entity_type": {
                            "type": "string",
                            "enum": [
                                "attraction",
                                "restaurant",
                                "hotel",
                                "transport_hub",
                                "other",
                            ],
                        },
                        "address": {"type": "string"},
                        "intro": {"type": "string"},
                        "longitude": {"type": ["number", "null"]},
                        "latitude": {"type": ["number", "null"]},
                        "details": {
                            "type": "object",
                            "description": "标签、营业时间、预约、项目、美食、价格等结构化字段",
                        },
                        "evidence_source": {
                            "type": "string",
                            "description": "本轮工具结果中的 URL、攻略 ID 或地图来源",
                        },
                        "observed_at": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0.1, "maximum": 0.75},
                    },
                    "required": ["name", "city", "entity_type", "evidence_source"],
                    "additionalProperties": False,
                },
                "local_place_knowledge",
                60,
                0,
            ),
            PlaceKnowledgeProvider(knowledge_service),
            "更新地点知识卡",
            private_scope=True,
        )
    )
    tool_gateway = ToolGateway(tool_store_factory, SystemClock(), tuple(registered_tools))
    health_service = HealthService(
        checks=(
            DatabaseReadinessCheck(database),
            DirectoryReadinessCheck(resolved_settings.data_root),
            MasterKeyReadinessCheck(resolved_settings),
        )
    )
    return Container(
        settings=resolved_settings,
        database=database,
        health_service=health_service,
        access_service=access_service,
        family_member_service=FamilyMemberService(
            store_factory=member_store_factory,
            password_hasher=password_hasher,
            clock=SystemClock(),
        ),
        family_invite_service=FamilyInviteService(
            store_factory=invite_store_factory,
            token_issuer=token_issuer,
            password_hasher=password_hasher,
            clock=SystemClock(),
        ),
        trip_service=TripService(store_factory=trip_store_factory, clock=SystemClock()),
        itinerary_service=ItineraryService(
            store_factory=itinerary_store_factory, clock=SystemClock()
        ),
        planning_service=PlanningService(
            store_factory=planning_store_factory,
            provider=model_provider,
            clock=SystemClock(),
            provider_name="deepseek",
            model_name=resolved_settings.deepseek_model,
        ),
        conversation_service=ConversationService(
            store_factory=lambda: SqlAlchemyConversationStore(database.session_factory, protector),
            provider=chat_provider,
            tool_runtime=tool_gateway,
            knowledge_runtime=knowledge_service,
            clock=SystemClock(),
        ),
        tool_gateway=tool_gateway,
        knowledge_service=knowledge_service,
        login_rate_limiter=LoginRateLimiter(),
        invite_registration_rate_limiter=LoginRateLimiter(attempts=3, window_seconds=600),
    )


def _secret(value: object) -> str:
    getter = getattr(value, "get_secret_value", None)
    return str(getter()).strip() if callable(getter) else ""
