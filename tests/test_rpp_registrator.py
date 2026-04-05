import argparse
import importlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import rpp_plugin_registrator.registry_paths as rp

def load_registrator_functions():
    import rpp_cli.commands as registrator
    return registrator


class BaseRegistratorTests(unittest.TestCase):
    def setUp(self):
        self.reg = load_registrator_functions()

    @contextmanager
    def _temp_registry_home(self):
        original_home = rp.RPP_HOME
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".rpp"
            home.mkdir(parents=True, exist_ok=True)
            rp.RPP_HOME = home
            try:
                marker_path = home / rp.INITIALIZED_MARKER_FILENAME
                marker_path.write_text(
                    json.dumps({"SchemaVersion": 1, "Initialized": True, "InitializedPlugins": []}) + "\n",
                    encoding="utf-8",
                )
                yield home
            finally:
                rp.RPP_HOME = original_home


class RegistratorTests(BaseRegistratorTests):

    def test_describe_prints_json_to_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "sample_plugin.py"
            source.write_text(
                """
from rpp_common import RPP_Plugin

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
            self.assertEqual(payload["Plugin"]["SourceLanguage"], "python")
            self.assertEqual(payload["Plugin"]["ParamDescription"], [])
            self.assertEqual(payload["Plugin"]["LogDescription"], [])
            self.assertEqual(payload["Plugin"]["InputDescription"], [])
            self.assertEqual(payload["Plugin"]["OutputDescription"], [])

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
        with self._temp_registry_home() as home:
            with tempfile.TemporaryDirectory() as td:
                temp_root = Path(td)
                source = temp_root / "echo_plugin.py"
                source.write_text(
                """
from rpp_common import RPP_Plugin


class EchoPlugin(RPP_Plugin):
    def name(self) -> str:
        return \"echo\"

    def execute(self, input: str) -> str:
        return input
""".strip()
                + "\n",
                encoding="utf-8",
                )

                description_dir = home / "descriptions"
                registry_path = home / "registry" / "rpp_plugin_types.registry.json"

                args = argparse.Namespace(
                    source=str(source),
                    folder=None,
                    language=None,
                    plugin_id=None,
                    description=None,
                    registry=None,
                )
                self.reg.command_register(args)

                description_file = description_dir / "rpp_echo_plugin.plugin.json"
                self.assertTrue(description_file.exists())
                self.assertTrue(registry_path.exists())

                registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
                self.assertIn("rpp_echo_plugin", registry_payload["PluginTypes"])
                self.assertEqual(
                    registry_payload["PluginTypes"]["rpp_echo_plugin"]["DescriptionFile"],
                    str(description_file),
                )

    def test_register_folder_does_not_fail_when_empty(self):
        with self._temp_registry_home() as home:
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
        controller_module = importlib.import_module("rpp_common.common_plugins.Controller")
        dynsystem_module = importlib.import_module("rpp_common.common_plugins.DynSystem")
        disturbance_module = importlib.import_module("rpp_common.common_plugins.DisturbanceGenerator")
        estimator_module = importlib.import_module("rpp_common.common_plugins.Estimator")
        plugin_sources = [
            Path(controller_module.__file__).resolve(),
            Path(dynsystem_module.__file__).resolve(),
            Path(disturbance_module.__file__).resolve(),
            Path(estimator_module.__file__).resolve(),
        ]

        with self._temp_registry_home() as home:
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

            registry_path = home / "registry" / "rpp_plugin_types.registry.json"
            self.assertTrue(registry_path.exists())
            registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))

            expected_ids = {
                "rpp_controller",
                "rpp_dyn_system",
                "rpp_disturbance_generator",
                "rpp_estimator",
            }
            self.assertTrue(expected_ids.issubset(set(registry_payload["PluginTypes"].keys())))

            for plugin_id in expected_ids:
                description_path = Path(registry_payload["PluginTypes"][plugin_id]["DescriptionFile"])
                payload = json.loads(description_path.read_text(encoding="utf-8"))
                plugin = payload["Plugin"]

                self.assertIn("ParamDescription", plugin)
                self.assertIn("LogDescription", plugin)
                self.assertIn("InputDescription", plugin)
                self.assertIn("OutputDescription", plugin)
                self.assertIsInstance(plugin["ParamDescription"], list)
                self.assertIsInstance(plugin["LogDescription"], list)
                self.assertIsInstance(plugin["InputDescription"], list)
                self.assertIsInstance(plugin["OutputDescription"], list)

                method_names = [m["Name"] for m in plugin["Interface"]["Methods"]]
                for name in method_names:
                    self.assertFalse(name.startswith("_"), name)
                    self.assertFalse(name.endswith("_"), name)

            controller_description = Path(registry_payload["PluginTypes"]["rpp_controller"]["DescriptionFile"])
            controller_payload = json.loads(controller_description.read_text(encoding="utf-8"))
            controller_methods = {
                m["Name"] for m in controller_payload["Plugin"]["Interface"]["Methods"]
            }
            self.assertIn("create_data_model", controller_methods)
            self.assertIn("configure", controller_methods)
            self.assertIn("step", controller_methods)
            self.assertIn("reset", controller_methods)

    def test_register_overrides_class_tag_with_plugin_id(self):
        controller_module = importlib.import_module("rpp_common.common_plugins.Controller")
        source = Path(controller_module.__file__).resolve()

        with self._temp_registry_home() as home:
            args = argparse.Namespace(
                source=str(source),
                folder=None,
                language="python",
                plugin_id="controller_override",
                description=None,
                registry=None,
            )
            self.reg.command_register(args)

            registry_path = home / "registry" / "rpp_plugin_types.registry.json"
            registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))

            self.assertIn("controller_override", registry_payload["PluginTypes"])
            self.assertNotIn("rpp_controller", registry_payload["PluginTypes"])

    def test_register_duplicate_tag_raises_error(self):
        with self._temp_registry_home():
            with tempfile.TemporaryDirectory() as td:
                temp_root = Path(td)
                first = temp_root / "first.py"
                first.write_text(
                    """
from rpp_common import RPP_Plugin


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
from rpp_common import RPP_Plugin


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
                    plugin_id="dup",
                    description=None,
                    registry=None,
                )
                self.reg.command_register(args_first)

                args_second = argparse.Namespace(
                    source=str(second),
                    folder=None,
                    language="python",
                    plugin_id="dup",
                    description=None,
                    registry=None,
                )
                with self.assertRaises(ValueError):
                    self.reg.command_register(args_second)

    def test_register_duplicate_class_name_raises_error(self):
        with self._temp_registry_home():
            with tempfile.TemporaryDirectory() as td:
                temp_root = Path(td)
                first = temp_root / "first_class.py"
                first.write_text(
                    """
from rpp_common import RPP_Plugin


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
from rpp_common import RPP_Plugin


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

    def test_registry_info_prints_single_plugin_description(self):
        with self._temp_registry_home() as home:
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

                register_args = argparse.Namespace(
                    source=str(source),
                    folder=None,
                    language=None,
                    plugin_id=None,
                    description=None,
                    registry=None,
                )
                self.reg.command_register(register_args)

                info_args = argparse.Namespace(tag="rpp_echo_plugin", registry=None)
                out = io.StringIO()
                with redirect_stdout(out):
                    self.reg.command_registry_info(info_args)

                payload = json.loads(out.getvalue())
                self.assertEqual(payload["Plugin"]["Id"], "rpp_echo_plugin")

    def test_init_home_forces_initialization_override(self):
        args = argparse.Namespace()
        with mock.patch.object(self.reg.registry_api, "ensure_rpp_layout") as ensure_layout:
            self.reg.command_init_home(args)
        ensure_layout.assert_called_once_with(override_initialization=True)

    def test_pm_command_invokes_gui_main(self):
        args = argparse.Namespace()
        fake_gui_module = mock.Mock()
        fake_gui_module.main.return_value = 0

        with mock.patch("rpp_cli.commands.importlib.import_module", return_value=fake_gui_module) as import_module:
            result = self.reg.command_pm(args)

        import_module.assert_called_once_with("rpp_plugin_registrator.gui")
        fake_gui_module.main.assert_called_once_with()
        self.assertEqual(result, 0)


class LibraryCommandTests(BaseRegistratorTests):

    def test_library_register_path_calls_register_component_library(self):
        with self._temp_registry_home():
            with tempfile.TemporaryDirectory() as td:
                lib_path = Path(td) / "my_lib"
                lib_path.mkdir(parents=True, exist_ok=True)

                manager = mock.Mock()
                manager.register_component_library.return_value = str(lib_path)

                args = argparse.Namespace(library_args=["register", str(lib_path)])
                self.reg.command_library(args, library_manager=manager)

                manager.register_component_library.assert_called_once_with(
                    str(lib_path.resolve()),
                    link_register=False,
                    ask_dialog=False,
                )

    def test_library_unregister_calls_remove_component_library(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            manager.remove_component_library.return_value = "/tmp/my_lib"

            args = argparse.Namespace(library_args=["unregister", "my_lib"])
            self.reg.command_library(args, library_manager=manager)

            manager.remove_component_library.assert_called_once_with("my_lib")

    def test_library_named_register_file_calls_register_component_from_file(self):
        with self._temp_registry_home():
            with tempfile.TemporaryDirectory() as td:
                source = Path(td) / "plugin.py"
                source.write_text("class X: pass\n", encoding="utf-8")

                manager = mock.Mock()
                args = argparse.Namespace(library_args=["data_driven_lib", "register", str(source)])

                self.reg.command_library(args, library_manager=manager)

                manager.register_component_from_file.assert_called_once_with(
                    str(source.resolve()),
                    "data_driven_lib",
                )
                manager.refresh_component_library.assert_called_once_with("data_driven_lib")

    def test_library_named_refresh_calls_refresh_component_library(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            args = argparse.Namespace(library_args=["data_driven_lib", "refresh"])

            self.reg.command_library(args, library_manager=manager)

            manager.refresh_component_library.assert_called_once_with("data_driven_lib")

    def test_library_register_usage_error_when_missing_path(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            args = argparse.Namespace(library_args=["register"])

            with self.assertRaises(ValueError):
                self.reg.command_library(args, library_manager=manager)

    def test_library_empty_args_raises_usage_error(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            args = argparse.Namespace(library_args=[])

            with self.assertRaises(ValueError):
                self.reg.command_library(args, library_manager=manager)

if __name__ == "__main__":
    unittest.main()
