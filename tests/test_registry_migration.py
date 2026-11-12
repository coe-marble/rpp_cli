from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpp_cli import cli, commands
from rpp_plugin_registrator import migration


def test_migration_preview_does_not_initialize_or_generate(monkeypatch, capsys):
    manager = Mock()
    factory = Mock(return_value=manager)
    monkeypatch.setattr(commands, "LibraryManager", factory)
    monkeypatch.setattr(migration, "plan_registry_migration", Mock(return_value=SimpleNamespace(
        target_version="0.2.0", libraries=("rpp_common", "Consumer"))))
    migrate = Mock()
    monkeypatch.setattr(migration, "migrate_registry", migrate)
    args = cli.build_parser().parse_args(["registry", "migrate", "--dry-run"])

    assert args.func(args) == 0

    factory.assert_called_once_with(skip_layout_check=True, source_libraries=False)
    manager._source_registered_libraries.assert_not_called()
    migrate.assert_not_called()
    assert "rpp_common -> Consumer" in capsys.readouterr().out


def test_migration_failure_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(migration, "plan_registry_migration", Mock(
        side_effect=ValueError("Library dependency cycle")))
    args = cli.build_parser().parse_args(["registry", "migrate"])

    assert commands.command_registry_migrate(args, library_manager=Mock()) == 1
    error = capsys.readouterr().err
    assert "Traceback (most recent call last):" in error
    assert "ValueError: Library dependency cycle" in error


@pytest.mark.parametrize("options, restore_on_error", [([], True), (["--no-restore"], False)])
def test_migration_passes_restore_option(monkeypatch, capsys, options, restore_on_error):
    manager = Mock()
    monkeypatch.setattr(migration, "plan_registry_migration", Mock(return_value=SimpleNamespace(
        target_version="0.2.0", libraries=("rpp_common",))))
    migrate = Mock(return_value="/backup/home")
    monkeypatch.setattr(migration, "migrate_registry", migrate)
    args = cli.build_parser().parse_args(["registry", "migrate", *options])

    assert commands.command_registry_migrate(args, library_manager=manager) == 0

    migrate.assert_called_once_with(manager, restore_on_error=restore_on_error)
    assert "Backup retained at: /backup/home" in capsys.readouterr().out
