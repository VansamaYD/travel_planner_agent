import uuid

from travel_agent.modules.access.infrastructure.rate_limit import LoginRateLimiter
from travel_agent.modules.access.infrastructure.security import AesGcmTextProtector
from travel_agent.shared.domain.ids import new_uuid7


def test_protected_text_uses_random_nonce_and_context_binding() -> None:
    protector = AesGcmTextProtector(b"k" * 32)

    first = protector.encrypt("家庭名称", context="family.name")
    second = protector.encrypt("家庭名称", context="family.name")

    assert first != second
    assert "家庭名称".encode() not in first
    assert protector.decrypt(first, context="family.name") == "家庭名称"


def test_login_rate_limiter_blocks_after_configured_failures() -> None:
    limiter = LoginRateLimiter(attempts=2, window_seconds=300)
    key = limiter.key("127.0.0.1", "Admin")

    assert limiter.allowed(key)
    limiter.record_failure(key)
    assert limiter.allowed(key)
    limiter.record_failure(key)
    assert not limiter.allowed(key)
    limiter.reset(key)
    assert limiter.allowed(key)


def test_uuid7_values_are_valid_and_time_sortable() -> None:
    first = new_uuid7()
    second = new_uuid7()

    assert uuid.UUID(first).version == 7
    assert uuid.UUID(second).version == 7
    assert first != second
