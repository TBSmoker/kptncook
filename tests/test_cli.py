from typer.testing import CliRunner

from kptncook import cli


def test_web_command_is_available_in_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "web" in result.output
