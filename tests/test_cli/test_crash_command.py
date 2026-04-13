"""Tests for the goose crash CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from goose.cli.crash import crash


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def normal_flight_ulg(fixtures_dir: Path) -> Path:
    return fixtures_dir / "px4_normal_flight.ulg"


@pytest.fixture
def motor_failure_ulg(fixtures_dir: Path) -> Path:
    return fixtures_dir / "px4_motor_failure.ulg"


class TestCrashCommand:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(crash, ["--help"])
        assert result.exit_code == 0
        assert "Analyze a flight log" in result.output

    def test_missing_file(self, runner: CliRunner) -> None:
        result = runner.invoke(crash, ["nonexistent.ulg"])
        assert result.exit_code != 0

    def test_normal_flight_text_output(self, runner: CliRunner, normal_flight_ulg: Path) -> None:
        result = runner.invoke(crash, [str(normal_flight_ulg), "--no-color"])
        assert result.exit_code == 0
        assert "Goose" in result.output
        assert "Crash Analysis" in result.output
        # Should contain file name, aircraft info, and score
        assert "File:" in result.output
        assert "Overall Score:" in result.output

    def test_normal_flight_json_output(self, runner: CliRunner, normal_flight_ulg: Path) -> None:
        result = runner.invoke(crash, [str(normal_flight_ulg), "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "crashed" in data
        assert "overall_score" in data
        assert "findings" in data

    def test_motor_failure_detects_crash(self, runner: CliRunner, motor_failure_ulg: Path) -> None:
        if not motor_failure_ulg.exists():
            pytest.skip("Motor failure fixture not available")
        result = runner.invoke(crash, [str(motor_failure_ulg), "--no-color"])
        assert result.exit_code == 0
        assert "Crash Analysis" in result.output

    def test_motor_failure_json(self, runner: CliRunner, motor_failure_ulg: Path) -> None:
        if not motor_failure_ulg.exists():
            pytest.skip("Motor failure fixture not available")
        result = runner.invoke(crash, [str(motor_failure_ulg), "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data["crashed"], bool)

    def test_verbose_flag(self, runner: CliRunner, normal_flight_ulg: Path) -> None:
        result = runner.invoke(crash, [str(normal_flight_ulg), "-v", "--no-color"])
        assert result.exit_code == 0

    def test_output_to_file(self, runner: CliRunner, normal_flight_ulg: Path, tmp_path: Path) -> None:
        outfile = tmp_path / "report.json"
        result = runner.invoke(crash, [str(normal_flight_ulg), "-f", "json", "-o", str(outfile)])
        assert result.exit_code == 0
        assert outfile.exists()
        data = json.loads(outfile.read_text())
        assert "crashed" in data
