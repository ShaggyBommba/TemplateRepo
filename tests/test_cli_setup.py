from __future__ import annotations

from click.testing import CliRunner

from presentation.cli.app import setup, teardown


def test_setup_claude_installs_plugin_marketplace() -> None:
    runner = CliRunner()

    result = runner.invoke(setup, ["--target", "claude", "--dry-run"])

    assert result.exit_code == 0
    assert "+ claude plugin marketplace add --scope user" in result.output
    assert "+ claude plugin install --scope user bazzpara@bazzpara" in result.output
    assert "+ claude mcp add" not in result.output


def test_setup_codex_keeps_direct_skill_and_mcp_install() -> None:
    runner = CliRunner()

    result = runner.invoke(setup, ["--target", "codex", "--dry-run"])

    assert result.exit_code == 0
    assert "Installing codex skill" in result.output
    assert "+ codex mcp add bazzpara --url http://127.0.0.1:8035/mcp" in result.output
    assert "+ claude plugin" not in result.output


def test_teardown_claude_removes_plugin_marketplace() -> None:
    runner = CliRunner()

    result = runner.invoke(teardown, ["--target", "claude", "--dry-run"])

    assert result.exit_code == 0
    assert "+ claude plugin uninstall --scope user bazzpara@bazzpara" in result.output
    assert "+ claude plugin marketplace remove bazzpara" in result.output
