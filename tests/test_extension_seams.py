"""Tests for Core/Pro extension seams.

Verifies that:
- get_all_plugins() returns Core built-ins and merges Pro-registered plugins
- register_parser() makes a parser available in detection
- Report registry has Core generators registered and supports extension
- Capability system supports Pro tier and extensible capability registration

These tests use only Core code — no Pro packages required.  Pro extension
behaviour is simulated by directly calling the registration functions.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Plugin seam tests
# ---------------------------------------------------------------------------

class TestGetAllPlugins:
    """get_all_plugins() returns Core built-ins and merges Pro extension plugins."""

    def test_returns_all_core_plugins(self):
        from goose.plugins import get_all_plugins, PLUGIN_REGISTRY
        result = get_all_plugins()
        # Must contain every Core plugin
        for pid in PLUGIN_REGISTRY:
            assert pid in result, f"Core plugin '{pid}' missing from get_all_plugins()"

    def test_core_plugin_count(self):
        from goose.plugins import get_all_plugins
        result = get_all_plugins()
        # 17 Core built-ins at minimum
        assert len(result) >= 17

    def test_returns_dict_of_plugin_instances(self):
        from goose.plugins import get_all_plugins
        from goose.plugins.base import Plugin
        result = get_all_plugins()
        assert isinstance(result, dict)
        for pid, plugin in result.items():
            assert isinstance(pid, str)
            assert isinstance(plugin, Plugin), f"Plugin '{pid}' is not a Plugin instance"

    def test_returns_new_dict_each_call(self):
        """Callers may mutate the returned dict safely."""
        from goose.plugins import get_all_plugins
        a = get_all_plugins()
        b = get_all_plugins()
        assert a is not b

    def test_pro_plugins_take_precedence_over_core(self, monkeypatch):
        """Pro plugin with same plugin_id as a Core plugin wins (Pro-upgrade model).

        This is intentional: official Pro packages use identical plugin_ids to
        upgrade Core implementations with enhanced versions. Third-party extensions
        that should NOT override Core should use unique plugin_ids.
        """
        from goose.plugins import get_all_plugins, PLUGIN_REGISTRY
        from goose.plugins.base import Plugin
        from goose.plugins.contract import PluginManifest, PluginCategory, PluginTrustState

        # Build a fake Pro plugin with same id as an existing Core plugin
        core_pid = next(iter(PLUGIN_REGISTRY))  # e.g. "crash_detection"

        class FakeProPlugin(Plugin):
            name = core_pid
            description = "fake pro plugin"
            version = "99.0.0"
            manifest = PluginManifest(
                plugin_id=core_pid,
                name="Fake Pro",
                version="99.0.0",
                author="pro",
                description="fake",
                category=PluginCategory.CRASH,
                supported_vehicle_types=["multirotor"],
                required_streams=[],
                optional_streams=[],
                output_finding_types=[],
            )

            def analyze(self, flight, config):
                return []

        fake_pro_instance = FakeProPlugin()

        # Monkeypatch discover_pro_plugins to return our fake
        import goose.plugins.registry as reg_mod
        monkeypatch.setattr(reg_mod, "discover_pro_plugins", lambda: [fake_pro_instance])

        result = get_all_plugins()
        # Pro plugin must win — same plugin_id → Pro overrides Core
        assert result[core_pid] is fake_pro_instance
        assert result[core_pid].manifest.version == "99.0.0"

    def test_pro_plugins_added_when_not_conflicting(self, monkeypatch):
        """A Pro plugin with a unique plugin_id is included in the merged set."""
        from goose.plugins import get_all_plugins, PLUGIN_REGISTRY
        from goose.plugins.base import Plugin
        from goose.plugins.contract import PluginManifest, PluginCategory, PluginTrustState

        class FakeUniqueProPlugin(Plugin):
            name = "pro_unique_test_plugin"
            description = "unique pro plugin"
            version = "1.0.0"
            manifest = PluginManifest(
                plugin_id="pro_unique_test_plugin",
                name="Pro Unique Test",
                version="1.0.0",
                author="pro",
                description="unique",
                category=PluginCategory.HEALTH,
                supported_vehicle_types=["multirotor"],
                required_streams=[],
                optional_streams=[],
                output_finding_types=[],
                plugin_type="extension",
                trust_state=PluginTrustState.LOCAL_UNSIGNED,
            )

            def analyze(self, flight, config):
                return []

        fake_unique = FakeUniqueProPlugin()

        import goose.plugins.registry as reg_mod
        monkeypatch.setattr(reg_mod, "discover_pro_plugins", lambda: [fake_unique])

        result = get_all_plugins()
        assert "pro_unique_test_plugin" in result
        assert result["pro_unique_test_plugin"] is fake_unique

    def test_all_core_plugins_have_manifests(self):
        from goose.plugins import get_all_plugins
        result = get_all_plugins()
        for pid, plugin in result.items():
            assert hasattr(plugin, "manifest"), f"Plugin '{pid}' missing manifest"
            assert plugin.manifest.plugin_id == pid, (
                f"Plugin '{pid}' manifest.plugin_id mismatch: {plugin.manifest.plugin_id}"
            )


# ---------------------------------------------------------------------------
# Parser seam tests
# ---------------------------------------------------------------------------

class TestRegisterParser:
    """register_parser() makes a parser available in detection."""

    def setup_method(self):
        """Snapshot _ALL_PARSERS length before each test for cleanup."""
        from goose.parsers import detect
        self._orig_count = len(detect._ALL_PARSERS)

    def teardown_method(self):
        """Remove any parsers added during the test."""
        from goose.parsers import detect
        del detect._ALL_PARSERS[self._orig_count:]
        detect._IMPLEMENTED_PARSERS.clear()
        detect._IMPLEMENTED_PARSERS.extend(
            p for p in detect._ALL_PARSERS if p.implemented
        )

    def test_register_parser_adds_to_all_parsers(self):
        from goose.parsers.detect import register_parser, _ALL_PARSERS
        from goose.parsers.base import BaseParser

        class FakeParser(BaseParser):
            format_name = "fake_test_format"
            file_extensions = [".fake_test"]
            implemented = True

            def can_parse(self, path):
                return str(path).endswith(".fake_test")

            def parse(self, path):
                from goose.parsers.diagnostics import ParseDiagnostics, ParseResult
                diag = ParseDiagnostics(
                    parser_selected="FakeParser",
                    detected_format="fake_test_format",
                    format_confidence=1.0,
                    supported=True,
                    parser_confidence=1.0,
                )
                return ParseResult(diagnostics=diag, flight=None)

        fake = FakeParser()
        before = len(_ALL_PARSERS)
        register_parser(fake)
        assert len(_ALL_PARSERS) == before + 1
        assert _ALL_PARSERS[-1] is fake

    def test_register_parser_updates_implemented_cache(self):
        from goose.parsers.detect import register_parser, _IMPLEMENTED_PARSERS
        from goose.parsers.base import BaseParser

        class ImplementedFakeParser(BaseParser):
            format_name = "implemented_fake"
            file_extensions = [".ifake"]
            implemented = True

            def can_parse(self, path):
                return str(path).endswith(".ifake")

            def parse(self, path):
                from goose.parsers.diagnostics import ParseDiagnostics, ParseResult
                diag = ParseDiagnostics(
                    parser_selected="ImplementedFakeParser",
                    detected_format="implemented_fake",
                    format_confidence=1.0,
                    supported=True,
                    parser_confidence=1.0,
                )
                return ParseResult(diagnostics=diag, flight=None)

        fake = ImplementedFakeParser()
        before = len(_IMPLEMENTED_PARSERS)
        register_parser(fake)
        assert len(_IMPLEMENTED_PARSERS) == before + 1
        assert _IMPLEMENTED_PARSERS[-1] is fake

    def test_register_parser_unimplemented_not_in_implemented_cache(self):
        from goose.parsers.detect import register_parser, _IMPLEMENTED_PARSERS
        from goose.parsers.base import BaseParser

        class StubFakeParser(BaseParser):
            format_name = "stub_fake"
            file_extensions = [".sfake"]
            implemented = False

            def can_parse(self, path):
                return False

            def parse(self, path):
                from goose.parsers.diagnostics import ParseDiagnostics, ParseResult
                return ParseResult(diagnostics=ParseDiagnostics(), flight=None)

        stub = StubFakeParser()
        before = len(_IMPLEMENTED_PARSERS)
        register_parser(stub)
        # Not implemented — should NOT appear in _IMPLEMENTED_PARSERS
        assert len(_IMPLEMENTED_PARSERS) == before

    def test_register_parser_raises_on_non_parser(self):
        from goose.parsers.detect import register_parser
        with pytest.raises(TypeError, match="BaseParser"):
            register_parser("not_a_parser")  # type: ignore[arg-type]

    def test_core_parsers_remain_first(self):
        """Core parsers always appear before extension parsers."""
        from goose.parsers.detect import register_parser, _ALL_PARSERS
        from goose.parsers.base import BaseParser
        from goose.parsers.ulog import ULogParser

        class LastFakeParser(BaseParser):
            format_name = "last_fake"
            file_extensions = [".lfake"]
            implemented = True

            def can_parse(self, path):
                return False

            def parse(self, path):
                from goose.parsers.diagnostics import ParseDiagnostics, ParseResult
                return ParseResult(diagnostics=ParseDiagnostics(), flight=None)

        register_parser(LastFakeParser())
        # ULogParser must still be first
        assert isinstance(_ALL_PARSERS[0], ULogParser)


# ---------------------------------------------------------------------------
# Report registry tests
# ---------------------------------------------------------------------------

class TestReportRegistry:
    """Report registry has Core generators registered and supports extension."""

    def test_core_generators_registered(self):
        from goose.forensics.report_registry import list_core_formats
        core_formats = list_core_formats()
        assert "json_findings" in core_formats
        assert "json_hypotheses" in core_formats
        assert "timeline" in core_formats

    def test_list_report_formats_returns_dicts(self):
        from goose.forensics.report_registry import list_report_formats
        formats = list_report_formats()
        assert isinstance(formats, list)
        for entry in formats:
            assert "format_name" in entry
            assert "description" in entry
            assert "is_core" in entry

    def test_get_report_generator_returns_callable(self):
        from goose.forensics.report_registry import get_report_generator
        gen = get_report_generator("json_findings")
        assert gen is not None
        assert callable(gen)

    def test_get_report_generator_returns_none_for_unknown(self):
        from goose.forensics.report_registry import get_report_generator
        assert get_report_generator("__nonexistent_format__") is None

    def test_register_extension_generator(self):
        from goose.forensics import report_registry as rr

        def my_pro_generator(case_dir, run_id):
            return {"format": "my_pro", "case_dir": str(case_dir)}

        rr.register_report_generator(
            "my_pro_format_test",
            my_pro_generator,
            description="Test Pro format",
        )
        gen = rr.get_report_generator("my_pro_format_test")
        assert gen is my_pro_generator

        # Should appear in list_report_formats
        formats = {f["format_name"] for f in rr.list_report_formats()}
        assert "my_pro_format_test" in formats

        # Should appear in extension formats, not Core
        ext = rr.list_extension_formats()
        assert "my_pro_format_test" in ext
        core = rr.list_core_formats()
        assert "my_pro_format_test" not in core

    def test_register_generator_raises_on_empty_name(self):
        from goose.forensics.report_registry import register_report_generator
        with pytest.raises(ValueError, match="non-empty"):
            register_report_generator("", lambda d, r: {})

    def test_register_generator_raises_on_non_callable(self):
        from goose.forensics.report_registry import register_report_generator
        with pytest.raises(TypeError, match="callable"):
            register_report_generator("bad_format", "not_callable")  # type: ignore[arg-type]

    def test_core_generators_are_callable_on_missing_dir(self, tmp_path):
        """Core generators handle missing artifacts gracefully (no raise)."""
        from goose.forensics.report_registry import get_report_generator
        for fmt in ("json_findings", "json_hypotheses", "timeline"):
            gen = get_report_generator(fmt)
            assert gen is not None
            result = gen(tmp_path, None)
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Capability / feature seam tests
# ---------------------------------------------------------------------------

class TestCapabilitySystem:
    """Capability system supports Pro tier and extensible capability registration."""

    def test_oss_core_tier_is_default(self):
        from goose.features import FeatureGate, EntitlementLevel
        assert FeatureGate.current_level() == EntitlementLevel.OSS_CORE

    def test_set_level_to_local_pro(self):
        from goose.features import FeatureGate, EntitlementLevel
        original = FeatureGate.current_level()
        try:
            FeatureGate.set_level(EntitlementLevel.LOCAL_PRO)
            assert FeatureGate.current_level() == EntitlementLevel.LOCAL_PRO
        finally:
            FeatureGate.set_level(original)

    def test_local_pro_features_unlocked_at_local_pro(self):
        from goose.features import FeatureGate, EntitlementLevel, is_feature_enabled
        original = FeatureGate.current_level()
        try:
            FeatureGate.set_level(EntitlementLevel.LOCAL_PRO)
            assert is_feature_enabled("advanced_reports") is True
            assert is_feature_enabled("premium_plugin_packs") is True
        finally:
            FeatureGate.set_level(original)

    def test_local_pro_features_not_available_at_oss_core(self):
        from goose.features import FeatureGate, EntitlementLevel, is_feature_enabled
        original = FeatureGate.current_level()
        try:
            FeatureGate.set_level(EntitlementLevel.OSS_CORE)
            assert is_feature_enabled("advanced_reports") is False
        finally:
            FeatureGate.set_level(original)

    def test_all_four_tiers_exist(self):
        from goose.features import EntitlementLevel
        tiers = [e.value for e in EntitlementLevel]
        assert "oss_core" in tiers
        assert "local_pro" in tiers
        assert "hosted_team" in tiers
        assert "enterprise_gov" in tiers

    def test_register_capability_adds_to_matrix(self):
        from goose.features import register_capability, is_feature_enabled, FEATURE_TIER_MATRIX, EntitlementLevel

        test_feature = "__test_pro_capability_xyz__"
        register_capability(test_feature, EntitlementLevel.LOCAL_PRO)
        assert test_feature in FEATURE_TIER_MATRIX

        original = from_level = None
        from goose.features import FeatureGate
        original = FeatureGate.current_level()
        try:
            FeatureGate.set_level(EntitlementLevel.OSS_CORE)
            assert is_feature_enabled(test_feature) is False

            FeatureGate.set_level(EntitlementLevel.LOCAL_PRO)
            assert is_feature_enabled(test_feature) is True
        finally:
            FeatureGate.set_level(original)
            FEATURE_TIER_MATRIX.pop(test_feature, None)

    def test_unknown_feature_defaults_to_enabled(self):
        from goose.features import is_feature_enabled
        # Unknown features default to enabled so legacy call sites work
        assert is_feature_enabled("__definitely_unknown_feature__") is True

    def test_feature_gate_to_dict_includes_features(self):
        from goose.features import FeatureGate
        d = FeatureGate.to_dict()
        assert "current_level" in d
        assert "capabilities" in d
        assert "features" in d
        assert "feature_requirements" in d
