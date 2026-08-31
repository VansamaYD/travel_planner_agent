from pathlib import Path

from travel_agent.bootstrap.settings import Settings


def test_settings_convert_sync_sqlite_url_to_async(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        data_root=tmp_path,
        database_url="sqlite:///data/example.db",
    )

    assert settings.effective_database_url == "sqlite+aiosqlite:///data/example.db"


def test_default_database_lives_below_data_root(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_root=tmp_path)

    assert settings.effective_database_url.endswith("/db/travel_agent.db")
