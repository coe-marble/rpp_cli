"""Recovery and reuse of the generated C++ integration-test registry."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from rpp_cli import testing


@pytest.fixture
def setup_environment(tmp_path, monkeypatch):
    examples = tmp_path / "fixtures/data/example_plugins"
    examples.mkdir(parents=True)
    (examples / "python_example.py").touch()
    (examples / "cpp_example.cpp").touch()
    monkeypatch.setattr(testing, "RPP_TESTING_PATH", examples.parents[1])
    monkeypatch.setattr(testing.rc, "get_config", lambda: {"RPP_CPP_CORE_PATH": "/core"})
    state = SimpleNamespace(builds=0, registrations=[], failure=None)

    class Manager:
        def __init__(self, rpp_home=None, skip_layout_check=False):
            self.home = rpp_home
            if not skip_layout_check:
                state.builds += 1
                if state.failure == "layout":
                    (self.home / "partial_adapter.hpp").touch()
                    raise RuntimeError("adapter compilation failed")

        def get_or_create_plugin_library(self, name):
            return SimpleNamespace(path=self.home / "libraries" / name)

        def register_plugin_from_source(self, source, name):
            if state.failure == "registration":
                raise RuntimeError("plugin compilation failed")
            state.registrations.append(source.name)
            return {"PluginName": source.stem, "SourceLanguage": source.suffix}

        def get_library_plugins(self, name):
            return {str(index): {"PluginName": Path(source).stem,
                                 "SourceLanguage": Path(source).suffix}
                    for index, source in enumerate(state.registrations)}

    monkeypatch.setattr(testing, "LibraryManager", Manager)
    return state


@pytest.mark.parametrize("failure", ["layout", "registration"])
def test_retry_rebuilds_failed_setup(tmp_path, setup_environment, failure):
    state = setup_environment
    state.failure = failure
    with pytest.raises(RuntimeError, match="compilation failed"):
        testing.setup_tmp_rpp_with_test_plugins(tmp_path)
    home = tmp_path / ".rpp"
    assert not (home / testing.TEST_SETUP_MARKER).exists()
    state.failure = None

    handle = testing.setup_tmp_rpp_with_test_plugins(tmp_path)

    assert state.builds == 2
    assert {plugin["PluginName"] for plugin in handle.plugins} == {
        "python_example", "cpp_example"}
    assert (home / testing.TEST_SETUP_MARKER).is_file()
    assert not (home / "partial_adapter.hpp").exists()


def test_rebuilds_legacy_partial_directory(tmp_path, setup_environment):
    home = tmp_path / ".rpp"
    home.mkdir()
    (home / "obsolete_adapter.hpp").touch()

    testing.setup_tmp_rpp_with_test_plugins(tmp_path)

    assert setup_environment.builds == 1
    assert not (home / "obsolete_adapter.hpp").exists()


def test_reuses_complete_setup(tmp_path, setup_environment):
    first = testing.setup_tmp_rpp_with_test_plugins(tmp_path)
    second = testing.setup_tmp_rpp_with_test_plugins(tmp_path)

    assert setup_environment.builds == 1
    assert first.plugins == second.plugins


def test_override_rebuilds_complete_setup(tmp_path, setup_environment):
    testing.setup_tmp_rpp_with_test_plugins(tmp_path)
    testing.setup_tmp_rpp_with_test_plugins(tmp_path, override=True)

    assert setup_environment.builds == 2
