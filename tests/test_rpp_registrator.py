import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def load_registrator_functions():
    workspace_root = Path(__file__).resolve().parents[2]
    registrator_root = workspace_root / "rpp_plugin_registrator"
    if str(registrator_root) not in sys.path:
        sys.path.insert(0, str(registrator_root))

    import rpp_cli.commands as registrator

    return registrator


class RegistratorTests(unittest.TestCase):
    def setUp(self):
        self.reg = load_registrator_functions()
        self._original_home = self.reg.RPP_HOME
        self._original_registry_home = self.reg.registry_api.RPP_HOME
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = Path(self._home_dir.name)
        self.reg.RPP_HOME = self.home
        self.reg.registry_api.RPP_HOME = self.home

    def tearDown(self):
        self.reg.RPP_HOME = self._original_home
        self.reg.registry_api.RPP_HOME = self._original_registry_home
        self._home_dir.cleanup()

    def test_describe_prints_json_to_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "sample_plugin.py"
            source.write_text(
                """
from rpp_common.py.RPP_Plugin import RPP_Plugin

class SamplePlugin(RPP_Plugin):
    def name(self) -> str:
        return \"sample\"

    def execute(self, input: str) -> str:
        return input
""".strip()
                + "\n",
                encoding="utf-8",
            )

            args = argparse.Namespace(source=str(source), language=None, plugin_id=None)
            out = io.StringIO()
            with redirect_stdout(out):
                self.reg.command_describe(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(payload["plugin"]["id"], "sample")
            self.assertEqual(payload["plugin"]["source_language"], "python")
            self.assertEqual(payload["plugin"]["param_description"], [])
            self.assertEqual(payload["plugin"]["log_description"], [])
            self.assertEqual(payload["plugin"]["input_description"], [])
            self.assertEqual(payload["plugin"]["output_description"], [])

    def test_scaffold_python_creates_source_file(self):
        with tempfile.TemporaryDirectory() as td:
            output_path = Path(td) / "generated" / "hello_plugin.py"
            args = argparse.Namespace(
                language="python",
                plugin_id="hello",
                class_name=None,
                output=str(output_path),
            )

            self.reg.command_scaffold(args)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("from rpp_common.py.RPP_Plugin import RPP_Plugin", content)
            self.assertIn("param_description = []", content)
            self.assertIn("log_description = []", content)
            self.assertIn("input_description = []", content)
            self.assertIn("output_description = []", content)
            self.assertIn("class HelloPlugin", content)
            self.assertIn('return "hello"', content)

    def test_scaffold_cpp_creates_source_file(self):
        with tempfile.TemporaryDirectory() as td:
            output_path = Path(td) / "generated" / "hello_plugin.cpp"
            args = argparse.Namespace(
                language="cpp",
                plugin_id="hello",
                class_name=None,
                output=str(output_path),
            )

            self.reg.command_scaffold(args)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("class HelloPlugin", content)
            self.assertIn('return "hello"', content)

    def test_register_from_source_writes_description_and_registry(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            source = temp_root / "echo_plugin.py"
            source.write_text(
                """
from rpp_common.py.RPP_Plugin import RPP_Plugin


class EchoPlugin(RPP_Plugin):
    def name(self) -> str:
        return \"echo\"

    def execute(self, input: str) -> str:
        return input
""".strip()
                + "\n",
                encoding="utf-8",
            )

            description_dir = self.home / "descriptions"
            registry_path = self.home / "registry" / "rpp_plugins.registry.json"

            args = argparse.Namespace(
                source=str(source),
                folder=None,
                language=None,
                plugin_id=None,
                description=None,
                registry=None,
            )
            self.reg.command_register(args)

            description_file = description_dir / "echo.plugin.json"
            self.assertTrue(description_file.exists())
            self.assertTrue(registry_path.exists())

            registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertIn("echo", registry_payload["plugins"])
            self.assertEqual(
                registry_payload["plugins"]["echo"]["description_file"],
                str(description_file),
            )

    def test_register_folder_does_not_fail_when_empty(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            descriptions = temp_root / "descriptions"
            descriptions.mkdir(parents=True, exist_ok=True)

            args = argparse.Namespace(
                source=None,
                folder=str(descriptions),
                language=None,
                plugin_id=None,
                description=None,
                registry=None,
            )

            out = io.StringIO()
            with redirect_stdout(out):
                self.reg.command_register(args)
            text = out.getvalue()

            self.assertIn("No plugin description files found in folder", text)

    def test_register_csbenchlab_fixture_plugins_include_public_methods(self):
        fixtures_root = Path(__file__).resolve().parent / "data" / "csbenchlab_plugin"
        plugin_sources = [
            fixtures_root / "Controller.py",
            fixtures_root / "DynSystem.py",
            fixtures_root / "DisturbanceGenerator.py",
            fixtures_root / "Estimator.py",
        ]

        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)

            for source in plugin_sources:
                args = argparse.Namespace(
                    source=str(source),
                    folder=None,
                    language="python",
                    plugin_id=None,
                    description=None,
                    registry=None,
                )
                self.reg.command_register(args)

            registry_path = self.home / "registry" / "rpp_plugins.registry.json"
            self.assertTrue(registry_path.exists())
            registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))

            expected_ids = {"ctl", "sys", "dist", "est"}
            self.assertTrue(expected_ids.issubset(set(registry_payload["plugins"].keys())))

            for plugin_id in expected_ids:
                description_path = Path(registry_payload["plugins"][plugin_id]["description_file"])
                payload = json.loads(description_path.read_text(encoding="utf-8"))
                plugin = payload["plugin"]

                self.assertIn("param_description", plugin)
                self.assertIn("log_description", plugin)
                self.assertIn("input_description", plugin)
                self.assertIn("output_description", plugin)
                self.assertIsInstance(plugin["param_description"], list)
                self.assertIsInstance(plugin["log_description"], list)
                self.assertIsInstance(plugin["input_description"], list)
                self.assertIsInstance(plugin["output_description"], list)

                method_names = [m["name"] for m in plugin["interface"]["methods"]]
                for name in method_names:
                    self.assertFalse(name.startswith("_"), name)
                    self.assertFalse(name.endswith("_"), name)

            controller_description = Path(
                registry_payload["plugins"]["ctl"]["description_file"]
            )
            controller_payload = json.loads(controller_description.read_text(encoding="utf-8"))
            controller_methods = {
                m["name"] for m in controller_payload["plugin"]["interface"]["methods"]
            }
            self.assertIn("create_data_model", controller_methods)
            self.assertIn("configure", controller_methods)
            self.assertIn("step", controller_methods)
            self.assertIn("reset", controller_methods)

    def test_register_overrides_class_tag_with_plugin_id(self):
        fixtures_root = Path(__file__).resolve().parent / "data" / "csbenchlab_plugin"
        source = fixtures_root / "Controller.py"

        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)

            args = argparse.Namespace(
                source=str(source),
                folder=None,
                language="python",
                plugin_id="controller_override",
                description=None,
                registry=None,
            )
            self.reg.command_register(args)

            registry_path = self.home / "registry" / "rpp_plugins.registry.json"
            registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))

            self.assertIn("controller_override", registry_payload["plugins"])
            self.assertNotIn("ctl", registry_payload["plugins"])

    def test_register_duplicate_tag_raises_error(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)

            first = temp_root / "first.py"
            first.write_text(
                """
from rpp_common.py.RPP_Plugin import RPP_Plugin


class FirstPlugin(RPP_Plugin):
    tag = "dup"

    def run(self):
        return 1
""".strip()
                + "\n",
                encoding="utf-8",
            )

            second = temp_root / "second.py"
            second.write_text(
                """
from rpp_common.py.RPP_Plugin import RPP_Plugin


class SecondPlugin(RPP_Plugin):
    tag = "dup"

    def run(self):
        return 2
""".strip()
                + "\n",
                encoding="utf-8",
            )

            args_first = argparse.Namespace(
                source=str(first),
                folder=None,
                language="python",
                plugin_id=None,
                description=None,
                registry=None,
            )
            self.reg.command_register(args_first)

            args_second = argparse.Namespace(
                source=str(second),
                folder=None,
                language="python",
                plugin_id=None,
                description=None,
                registry=None,
            )
            with self.assertRaises(ValueError):
                self.reg.command_register(args_second)

    def test_register_duplicate_class_name_raises_error(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)

            first = temp_root / "first_class.py"
            first.write_text(
                """
from rpp_common.py.RPP_Plugin import RPP_Plugin


class SameClass(RPP_Plugin):
    tag = "same_a"

    def run(self):
        return 1
""".strip()
                + "\n",
                encoding="utf-8",
            )

            second = temp_root / "second_class.py"
            second.write_text(
                """
from rpp_common.py.RPP_Plugin import RPP_Plugin


class SameClass(RPP_Plugin):
    tag = "same_b"

    def run(self):
        return 2
""".strip()
                + "\n",
                encoding="utf-8",
            )

            args_first = argparse.Namespace(
                source=str(first),
                folder=None,
                language="python",
                plugin_id=None,
                description=None,
                registry=None,
            )
            self.reg.command_register(args_first)

            args_second = argparse.Namespace(
                source=str(second),
                folder=None,
                language="python",
                plugin_id=None,
                description=None,
                registry=None,
            )
            with self.assertRaises(ValueError):
                self.reg.command_register(args_second)

if __name__ == "__main__":
    unittest.main()
