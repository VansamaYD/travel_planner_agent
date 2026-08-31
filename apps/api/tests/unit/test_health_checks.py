from pathlib import Path

import pytest
from pydantic import SecretStr

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.operations.infrastructure.health_checks import (
    DirectoryReadinessCheck,
    MasterKeyReadinessCheck,
)


@pytest.mark.asyncio
async def test_production_rejects_a_short_master_key(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        data_root=tmp_path,
        app_master_key=SecretStr("too-short"),
    )

    result = await MasterKeyReadinessCheck(settings).run()

    assert result.status == "error"
    assert result.detail == "valid_master_key_required_in_production"


@pytest.mark.asyncio
async def test_master_key_accepts_at_least_32_utf8_bytes(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        data_root=tmp_path,
        app_master_key=SecretStr("a" * 32),
    )

    result = await MasterKeyReadinessCheck(settings).run()

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_directory_check_requires_every_runtime_directory(tmp_path: Path) -> None:
    settings = Settings(app_env="test", data_root=tmp_path)
    settings.ensure_runtime_directories()
    (tmp_path / "tmp").rmdir()

    result = await DirectoryReadinessCheck(tmp_path).run()

    assert result.status == "error"
    assert result.detail == "runtime_directories_unavailable"
