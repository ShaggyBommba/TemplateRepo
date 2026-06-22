from __future__ import annotations

from pathlib import Path

from infrastructure.config import AmexScraperConfig


def test_amex_scraper_config_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("AMEX_USERNAME", "user")
    monkeypatch.setenv("AMEX_PASSWORD", "password")
    monkeypatch.setenv("AMEX_DOWNLOAD_DIR", "tmp/downloads")
    monkeypatch.setenv("AMEX_PROFILE_DIR", "tmp/profile")
    monkeypatch.setenv("AMEX_HEADLESS", "true")
    monkeypatch.setenv("CHROME_CHANNEL", "chrome")

    config = AmexScraperConfig(_env_file=None)

    assert config.username.get_secret_value() == "user"
    assert config.password.get_secret_value() == "password"
    assert config.download_dir == Path("tmp/downloads")
    assert config.profile_dir == Path("tmp/profile")
    assert config.headless is True
    assert config.chrome_channel == "chrome"
