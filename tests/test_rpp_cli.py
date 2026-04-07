import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from rpp_plugin_registrator import registry_paths as rp
import tempfile


def load_cli_module():
    workspace_root = Path(__file__).resolve().parents[2]
    cli_root = workspace_root / "rpp_cli"
    sys.path.insert(0, str(cli_root))

    import cli

    return cli


class RppCliTests(unittest.TestCase):
    def setUp(self):

        self.cli = load_cli_module()
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = Path(self._home_dir.name)
        self.home.mkdir(parents=True, exist_ok=True)
        self._original_rpp_home = rp.RPP_HOME
        rp.RPP_HOME = self.home

    def tearDown(self):
        rp.RPP_HOME = self._original_rpp_home
        self._home_dir.cleanup()

    def test_registry_list_command_exists(self):
        parser = self.cli.build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertEqual(set(subparser_action.choices.keys()), {"init-home", "pm", "ws", "registry", "library", "completion"})

        registry_parser = subparser_action.choices["registry"]
        registry_subparsers = next(
            action
            for action in registry_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertIn("list", registry_subparsers.choices)
        self.assertIn("info", registry_subparsers.choices)

    def test_pm_command_exists(self):
        parser = self.cli.build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertIn("pm", subparser_action.choices)

    def test_ws_command_exists(self):
        parser = self.cli.build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertIn("ws", subparser_action.choices)
        ws_parser = subparser_action.choices["ws"]
        ws_subparsers = next(
            action
            for action in ws_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertEqual(set(ws_subparsers.choices.keys()), {"create"})
        self.assertTrue(hasattr(ws_parser, "get_default"))

    def test_ws_defaults_to_gui(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws"])

        with patch("commands.workspace_main", return_value=0) as mocked_workspace_main:
            result = args.func(args)

        self.assertEqual(result, 0)
        mocked_workspace_main.assert_called_once_with([])

    def test_ws_root_opens_gui_in_folder(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "--root", "as"])

        with patch("commands.workspace_main", return_value=0) as mocked_workspace_main:
            result = args.func(args)

        self.assertEqual(result, 0)
        mocked_workspace_main.assert_called_once_with(["--root", "as"])

    def test_ws_create_supports_root_flag(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "create", "demo", "--root", "as", "--overwrite"])

        self.assertEqual(args.command, "ws")
        self.assertEqual(args.ws_command, "create")
        self.assertEqual(args.name, "demo")
        self.assertEqual(args.root, "as")
        self.assertTrue(args.overwrite)

    def test_ws_create_calls_command_handler(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "create", "demo", "--root", ".", "--overwrite"])

        with patch("commands.create_workspace") as mocked_create_workspace:
            result = args.func(args)

        self.assertEqual(result, 0)
        mocked_create_workspace.assert_called_once()


if __name__ == "__main__":
    unittest.main()