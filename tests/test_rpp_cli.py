import argparse
import sys
import unittest
from pathlib import Path


def load_cli_module():
    workspace_root = Path(__file__).resolve().parents[2]
    cli_root = workspace_root / "rpp_cli"
    registrator_root = workspace_root / "rpp_plugin_registrator"
    for root in (cli_root, registrator_root):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

    import cli

    return cli


class RppCliTests(unittest.TestCase):
    def setUp(self):
        self.cli = load_cli_module()

    def test_registry_list_command_exists(self):
        parser = self.cli.build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertEqual(set(subparser_action.choices.keys()), {"init-home", "registry"})
        self.assertIn("registry", subparser_action.choices)

        registry_parser = subparser_action.choices["registry"]
        registry_subparsers = next(
            action
            for action in registry_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertIn("list", registry_subparsers.choices)


if __name__ == "__main__":
    unittest.main()