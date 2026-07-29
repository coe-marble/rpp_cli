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
import rpp_plugin_registrator.plugin_type_registrator as ptyp_reg_api


def load_registrator_functions():
    import rpp_cli.commands as registrator
    return registrator

#TODO: Fix this
RPP_TESTING_PATH = Path(__file__).parent.parent.parent.resolve() \
    / "rpp_testing" / "rpp_testing"
FIXTURE_LIB_PATH = RPP_TESTING_PATH / "data" / "test_libs" / "test_lib_nn"

class BaseRegistratorTests(unittest.TestCase):


    def setUp(self):
        super().setUp()
        self.reg = load_registrator_functions()
        self.path_at_start = sys.path.copy()

    def tearDown(self):
        self.reg = None
        sys.path = self.path_at_start

    @contextmanager
    def _temp_registry_home(self, scaffold_languages=None):

        import rpp_plugin_registrator.plugin_type_registrator
        if scaffold_languages is not None:
            rpp_plugin_registrator.plugin_type_registrator.SCAFFOLD_LANGUAGES = scaffold_languages
        else:
            rpp_plugin_registrator.plugin_type_registrator.SCAFFOLD_LANGUAGES = ["python"]

        import rpp_plugin_registrator.registry_config as rp
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".rpp"
            home.mkdir(parents=True, exist_ok=True)
            self.manager = self.reg.LibraryManager(rpp_home=home)
            try:
                yield home
            finally:
                rp.reset_module()
                rpp_plugin_registrator.plugin_type_registrator.reset_module()

class CLICommandsTests(BaseRegistratorTests):

    def test_describe_plugin_prints_json_to_stdout(self):
        with self._temp_registry_home() as td:
            source = Path(td) / "sample_plugin.py"
            source.write_text(
                """
from rpp_plugin_types.rpp_common import MotionController2D

class SamplePlugin(MotionController2D):
    def name(self) -> str:
        return \"sample\"

    def execute(self, input: str) -> str:
        return input
""".strip()
                + "\n",
                encoding="utf-8",
            )

            args = argparse.Namespace(source=str(source))
            out = io.StringIO()
            with redirect_stdout(out):
                self.reg.command_describe(args)

            payload = json.loads(out.getvalue())
            payload = payload[0]
            self.assertEqual(payload["SourceFile"], str(source))
            self.assertEqual(payload["SourceLanguage"], "python")
            self.assertEqual(payload["PluginType"], "rpp_common::MotionController2D")
            self.assertEqual(payload["ClassName"], "SamplePlugin")
            self.assertEqual(payload["ValidationResult"]["IsValid"], True)
            self.assertIsNone(payload["ValidationResult"]["Message"])


    def test_describe_plugin_type_prints_json_to_stdout(self):
        with self._temp_registry_home() as td:
            source = Path(td) / "sample_plugin_type.capnp"
            source.write_text(
                """@0xabcdefabcdefabcdef;
using Anot = import "rpp_common/anot.capnp";
interface SamplePluginType $Anot.plugin("SamplePluginType") {
  item @0 () -> ();
}
""",
                encoding="utf-8",
            )
            args = argparse.Namespace(source=str(source), language=None, plugin_id=None)
            out = io.StringIO()
            with redirect_stdout(out):
                self.reg.command_describe(args)

            payload = json.loads(out.getvalue())
            payload = payload[0]
            self.assertEqual(payload["SourceLanguage"], "capnp")
            self.assertEqual(payload["ClassName"], "SamplePluginType")
            self.assertEqual(payload["ValidationResult"]["IsValid"], True)

    def test_registry_config_set_to_config_requires_uppercase_setting_name(self):
        with self._temp_registry_home() as td:
            with self.assertRaises(ValueError):
                args = argparse.Namespace(expression="lowercase_setting=value")
                self.reg.command_registry_setting(args)

    def test_registry_config_set_to_config_sets_value_in_config_file(self):
        with self._temp_registry_home() as td:
            setting_name = "USE_ROS2_COMPILATION"
            setting_value = "true"
            args = argparse.Namespace(expression=f"{setting_name}={setting_value}")

            import rpp_plugin_registrator.registry_config as rp
            self.assertEqual(rp.get_setting(setting_name), False)
            self.reg.command_registry_setting(args)

            config_path = rp.get_app_config_path()
            self.assertTrue(config_path.exists(), f"Config file does not exist: {config_path}")

            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            self.assertIn(setting_name, config_data)
            self.assertEqual(config_data[setting_name], True)
            self.assertTrue(hasattr(rp, setting_name))
            self.assertEqual(rp.get_setting(setting_name), True)


    def test_init_home_forces_initialization_override(self):
        args = argparse.Namespace(override=True)
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

    def test_library_registers_fixture_from_tests_data(self):
        with self._temp_registry_home() as home:
            fixture_lib = FIXTURE_LIB_PATH
            self.assertTrue(fixture_lib.exists(), f"Missing fixture library: {fixture_lib}")

            args = argparse.Namespace(library_args=["register", str(fixture_lib)])
            self.reg.command_library(args, self.manager)

            libraries = self.manager.list_plugin_libraries()
            library_names = {lib["Name"] for lib in libraries}

            self.assertIn("test_lib_nn", library_names)

    def test_library_registers_fixture_plugin_types_from_plugins_json(self):
        with self._temp_registry_home() as home:
            fixture_lib = FIXTURE_LIB_PATH
            args = argparse.Namespace(library_args=["register", str(fixture_lib)])

            self.reg.command_library(args, self.manager)

            manifest_path = home / "registry" / "libraries" / "test_lib_nn" / "manifest.json"
            self.assertTrue(manifest_path.exists())

            # test plugin type
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("PluginTypes", payload)
            self.assertIn("test_lib_nn::TestNNType", payload["PluginTypes"])
            nn_plugin = payload["PluginTypes"]["test_lib_nn::TestNNType"]
            self.assertEqual(nn_plugin["Library"], "test_lib_nn")
            self.assertEqual(nn_plugin["PluginTypeName"], "test_lib_nn::TestNNType")
            self.assertEqual(nn_plugin["ClassName"], "TestNNType")

            # test plugin1
            self.assertIn("Plugins", payload)
            self.assertIn("test_lib_nn::TestController", payload["Plugins"])
            plugin = payload["Plugins"]["test_lib_nn::TestController"]
            self.assertEqual(plugin["Library"], "test_lib_nn")
            self.assertEqual(plugin["PluginType"], "test_lib_nn::TestNNType")
            self.assertEqual(plugin["PluginName"], "test_lib_nn::TestController")
            self.assertEqual(plugin["SourceLanguage"], "python")

            plugin = payload["Plugins"]["test_lib_nn::TestController_common"]
            self.assertEqual(plugin["Library"], "test_lib_nn")
            self.assertEqual(plugin["PluginType"], "rpp_common::MotionController2D")
            self.assertEqual(plugin["PluginName"], "test_lib_nn::TestController_common")
            self.assertEqual(plugin["SourceLanguage"], "python")

    def test_library_register_path_calls_register_component_library(self):
        with self._temp_registry_home():
            with tempfile.TemporaryDirectory() as td:
                lib_path = Path(td) / "my_lib"
                lib_path.mkdir(parents=True, exist_ok=True)

                manager = mock.Mock()
                manager.register_plugin_library.return_value = str(lib_path)

                args = argparse.Namespace(library_args=["register", str(lib_path)])
                self.reg.command_library(args, library_manager=manager)

                manager.register_plugin_library.assert_called_once_with(
                    str(lib_path.resolve()),
                    link_register=False,
                )

    def test_library_register_path_supports_link_install(self):
        with self._temp_registry_home():
            with tempfile.TemporaryDirectory() as td:
                lib_path = Path(td) / "my_lib"
                lib_path.mkdir(parents=True, exist_ok=True)

                manager = mock.Mock()
                manager.register_plugin_library.return_value = str(lib_path)

                args = argparse.Namespace(library_args=["register", str(lib_path), "--link"])
                self.reg.command_library(args, library_manager=manager)

                manager.register_plugin_library.assert_called_once_with(
                    str(lib_path.resolve()),
                    link_register=True,
                )

    def test_library_register_reports_missing_path(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            missing_path = Path("/tmp/does-not-exist-rpp-library")
            args = argparse.Namespace(library_args=["register", str(missing_path), "--link"])

            out = io.StringIO()
            with redirect_stdout(out):
                result = self.reg.command_library(args, library_manager=manager)

            manager.register_plugin_library.assert_not_called()
            self.assertEqual(result, 1)
            self.assertIn("Library path does not exist:", out.getvalue())

    def test_library_unregister_calls_remove_plugin_library(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            manager.remove_plugin_library.return_value = "/tmp/my_lib"

            args = argparse.Namespace(library_args=["unregister", "my_lib"])
            self.reg.command_library(args, library_manager=manager)

            manager.remove_plugin_library.assert_called_once_with("my_lib")

    def test_library_named_register_file_calls_register_plugin_from_file(self):
        with self._temp_registry_home():
            with tempfile.TemporaryDirectory() as td:
                source = Path(td) / "plugin.py"
                source.write_text("class X: pass\n", encoding="utf-8")

                manager = mock.Mock()
                args = argparse.Namespace(library_args=["data_driven_lib", "register", str(source)])

                self.reg.command_library(args, library_manager=manager)

                manager.register_plugin_from_source.assert_called_once_with(
                    str(source.resolve()),
                    "data_driven_lib",
                )
                manager.refresh_plugin_library.assert_called_once_with("data_driven_lib")

    def test_library_named_refresh_calls_refresh_plugin_library(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            manager.get_library_path.return_value = "/tmp/data_driven_lib"
            args = argparse.Namespace(library_args=["data_driven_lib", "refresh"])

            self.reg.command_library(args, library_manager=manager)

            manager.get_library_path.assert_called_once_with("data_driven_lib")
            manager.refresh_plugin_library.assert_called_once_with("data_driven_lib")

    def test_library_refresh_reports_missing_library(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            manager.get_library_path.return_value = None
            args = argparse.Namespace(library_args=["refresh", "missing_lib"])

            out = io.StringIO()
            with redirect_stdout(out):
                result = self.reg.command_library(args, library_manager=manager)

            manager.get_library_path.assert_called_once_with("missing_lib")
            manager.refresh_plugin_library.assert_not_called()
            self.assertEqual(result, 1)
            self.assertIn("Library 'missing_lib' does not exist.", out.getvalue())

    def test_library_info_calls_get_library_info(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            manager.get_library_info.return_value = {"Library": "rpp_control", "Version": "0.0.1"}
            manager.get_library_path.return_value = "/tmp/rpp_control"
            manager._manifest_path.return_value = "/tmp/rpp_control/autogen/manifest.json"
            args = argparse.Namespace(library_args=["info", "rpp_control"])

            out = io.StringIO()
            with redirect_stdout(out):
                self.reg.command_library(args, library_manager=manager)

            manager.get_library_info.assert_called_once_with("rpp_control", only_registered=True)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["Library"], "rpp_control")
            self.assertIn("Plugins", payload)
            self.assertIn("PluginTypes", payload)

    def test_library_named_info_calls_get_library_info(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            manager.get_library_info.return_value = {"Library": "data_driven_lib", "Version": "0.0.1"}
            manager.get_library_path.return_value = "/tmp/data_driven_lib"
            manager._manifest_path.return_value = "/tmp/data_driven_lib/autogen/manifest.json"
            args = argparse.Namespace(library_args=["data_driven_lib", "info"])

            out = io.StringIO()
            with redirect_stdout(out):
                self.reg.command_library(args, library_manager=manager)

            manager.get_library_info.assert_called_once_with("data_driven_lib", only_registered=True)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["Library"], "data_driven_lib")
            self.assertIn("Plugins", payload)
            self.assertIn("PluginTypes", payload)

    def test_library_list_calls_list_plugin_libraries(self):
        with self._temp_registry_home():
            manager = mock.Mock()
            manager.list_plugin_libraries.return_value = [
                {"Name": "rpp"},
                {"Name": "rpp_control"},
            ]
            args = argparse.Namespace(library_args=["list"])

            out = io.StringIO()
            with redirect_stdout(out):
                self.reg.command_library(args, library_manager=manager)

            manager.list_plugin_libraries.assert_called_once_with()
            payload = json.loads(out.getvalue())
            self.assertEqual([item["Name"] for item in payload], ["rpp", "rpp_control"])

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
