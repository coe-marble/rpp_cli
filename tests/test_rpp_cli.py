import argparse
import sys
import unittest
from pathlib import Path

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

        self.assertEqual(set(subparser_action.choices.keys()), {"init-home", "pm", "registry", "library", "completion"})

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


if __name__ == "__main__":
    unittest.main()