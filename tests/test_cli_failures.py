"""User-facing failures must return errors before making changes."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpp_cli import cli, commands


@pytest.mark.parametrize("arguments", [
    ["library", "create"],
    ["library", "register", "one", "two"],
])
def test_invalid_library_usage_exits_nonzero_without_initializing_registry(
        arguments, monkeypatch, capsys):
    manager = Mock()
    monkeypatch.setattr(commands, "_get_library_manager", manager)
    monkeypatch.setattr(sys, "argv", ["rpp", *arguments])

    assert cli.main() == 1

    assert "Usage:" in capsys.readouterr().out
    manager.assert_not_called()


@pytest.mark.parametrize("arguments", [
    ["ws", "script"],
    ["ws", "component", "parameter", "set", "workspace", "Vehicle", "gain"],
])
def test_incomplete_workspace_command_reports_usage_on_stderr(arguments, capsys):
    with pytest.raises(SystemExit) as caught:
        cli.build_parser().parse_args(arguments)

    assert caught.value.code == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("arguments", [
    ["../escape.py"],
    ["safe.py", "--path", "../outside"],
])
def test_script_create_rejects_paths_outside_workspace(tmp_path, monkeypatch, arguments):
    workspace = Mock(root=tmp_path)
    monkeypatch.setattr(commands, "_open_existing_workspace", Mock(return_value=workspace))
    args = cli.build_parser().parse_args(["ws", "script", "create", "workspace", *arguments])

    with pytest.raises(ValueError, match="directory path|within the workspace"):
        args.func(args)

    workspace.create_script.assert_not_called()
    assert not (tmp_path.parent / "escape.py").exists()


def test_script_create_rejects_symlink_to_external_directory(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    workspace = Mock(root=root)
    monkeypatch.setattr(commands, "_open_existing_workspace", Mock(return_value=workspace))
    args = cli.build_parser().parse_args([
        "ws", "script", "create", "workspace", "safe.py", "--path", "linked",
    ])

    with pytest.raises(ValueError, match="within the workspace"):
        args.func(args)

    workspace.create_script.assert_not_called()
    assert list(outside.iterdir()) == []


def test_ambiguous_script_reference_does_not_remove_either_script(tmp_path, monkeypatch):
    workspace = Mock(root=tmp_path)
    scripts = [SimpleNamespace(
        path=tmp_path / folder / "control.py",
        load_description=lambda: {"ScriptName": "control"},
    ) for folder in ("first", "second")]
    workspace.list_scripts.return_value = scripts
    monkeypatch.setattr(commands, "_open_existing_workspace", Mock(return_value=workspace))
    args = cli.build_parser().parse_args(["ws", "script", "remove", "workspace", "control"])

    with pytest.raises(ValueError, match="ambiguous") as caught:
        args.func(args)

    assert all(str(script.path) in str(caught.value) for script in scripts)
    workspace.remove_script.assert_not_called()


@pytest.mark.parametrize("source", [None, "missing.py", "../external.py"])
def test_plugin_refresh_checks_source_before_unregistering(tmp_path, source):
    library = tmp_path / "library"
    library.mkdir()
    (tmp_path / "external.py").write_text("# Outside the library\n", encoding="utf-8")
    manager = Mock()
    manager.get_library_path.return_value = str(library)
    manager.get_plugin_info_from_lib.return_value = {
        "PluginName": "Demo::Controller", "SourceFile": source,
    }
    args = SimpleNamespace(library="Demo", plugin_name="Controller")

    with pytest.raises(ValueError, match="incomplete source metadata|does not exist|outside library"):
        commands.command_library_refresh_plugin(args, library_manager=manager)

    manager.unregister_plugin.assert_not_called()
    manager.register_plugin_from_source.assert_not_called()


def test_failed_plugin_refresh_keeps_the_registered_plugin(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    (library / "controller.py").write_text("# Cannot be imported\n", encoding="utf-8")
    registered = {"Demo::Controller"}

    class Manager:
        def get_library_path(self, library_name):
            return str(library)

        def get_plugin_info_from_lib(self, plugin_name, library_name):
            return {"PluginName": "Demo::Controller", "SourceFile": "controller.py"}

        def unregister_plugin(self, plugin_name, library_name, remove_from_json=True):
            registered.discard(plugin_name)

        def register_plugin_from_source(self, source_file, library_name):
            raise ValueError("Failed to import plugin class")

    args = SimpleNamespace(library="Demo", plugin_name="Controller")

    with pytest.raises(ValueError, match="Failed to import plugin class"):
        commands.command_library_refresh_plugin(args, library_manager=Manager())

    assert registered == {"Demo::Controller"}


def test_invalid_parameter_name_does_not_save_parameters(tmp_path, monkeypatch):
    workspace = Mock(root=tmp_path)
    monkeypatch.setattr(commands, "_open_existing_workspace", Mock(return_value=workspace))
    args = cli.build_parser().parse_args([
        "ws", "component", "parameter", "set", "workspace", "Vehicle", "invalid-name", "1",
    ])

    with pytest.raises(ValueError, match="valid Python identifiers"):
        args.func(args)

    workspace.component_parameter_store.save.assert_not_called()


@pytest.mark.parametrize("compiler_error, expected_status", [
    ("compiler rejected source", 1), (None, 0),
], ids=["compiler-failure", "success"])
def test_compile_exit_status_and_diagnostics(
        tmp_path, monkeypatch, capsys, compiler_error, expected_status):
    from rpp_plugin_registrator.plugin_registrator import cpp

    source = tmp_path / "controller.cpp"
    source.write_text("// Compiler failure is simulated below.\n", encoding="utf-8")
    monkeypatch.setattr(commands, "LibraryManager", Mock())
    monkeypatch.setattr(commands.rp, "load_and_set_config", Mock())
    monkeypatch.setattr(cpp, "compile_cpp_plugin", Mock(return_value=(
        compiler_error, ["g++"], tmp_path / "controller.so",
    )))
    monkeypatch.setattr(sys, "argv", [
        "rpp", "compile", str(source), "--plugin-type-name", "Types::Controller",
        "--library", "Demo",
    ])

    assert cli.main() == expected_status
    output = capsys.readouterr()
    if compiler_error:
        assert compiler_error in output.err
        assert "Successfully compiled" not in output.out
    else:
        assert "Successfully compiled" in output.out
        assert output.err == ""
