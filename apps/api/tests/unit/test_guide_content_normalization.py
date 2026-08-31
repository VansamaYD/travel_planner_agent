from travel_agent.modules.tools.store import _city_hint, _extract_topics


def test_topics_are_extracted_from_xhs_content_and_removed_from_body() -> None:
    content = "青岛四日路线正文\n\n#青岛[话题]##青岛旅游[话题]##五四广场美食推荐[话题]# #"

    body, tags = _extract_topics(content)

    assert body == "青岛四日路线正文"
    assert tags == ["青岛", "青岛旅游", "五四广场美食推荐"]


def test_city_hint_reads_city_from_title_query_or_topic_text() -> None:
    assert _city_hint("四天三夜青岛慢游攻略") == "青岛"
    assert _city_hint("#苏州园林[话题]") == "苏州"
    assert _city_hint("没有明确目的地") == "未分类"
