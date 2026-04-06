"""Shared fixtures for Goose tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.parsers.ulog import ULogParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def ulog_parser() -> ULogParser:
    return ULogParser()


@pytest.fixture
def normal_flight_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "px4_normal_flight.ulg"


@pytest.fixture
def motor_failure_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "px4_motor_failure.ulg"


@pytest.fixture
def vibration_crash_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "px4_vibration_crash.ulg"
