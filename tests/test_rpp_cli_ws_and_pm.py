import argparse
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rpp_plugin_registrator import registry_config as rp


def load_cli_module():
    workspace_root = Path(__file__).resolve().parents[2]
    cli_root = workspace_root / "rpp_cli"
    sys.path.insert(0, str(cli_root))

    import rpp_cli.cli as cli

    return cli


class RppCliCommandTests(unittest.TestCase):
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

    def test_global_rpp_home_configures_registry_home(self):
        target_home = self.home / "isolated-rpp-home"
        self.cli.configure_rpp_home(str(target_home))

        self.assertEqual(rp.RPP_HOME, target_home.resolve())

    def test_global_rpp_home_is_parsed_before_command(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "--rpp-home", "/tmp/rpp-home", "library", "list"
        ])

        self.assertEqual(args.rpp_home, "/tmp/rpp-home")
        self.assertEqual(args.command, "library")
        self.assertEqual(args.library_args, ["list"])

    def test_registry_list_command_exists(self):
        parser = self.cli.build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertEqual(set(subparser_action.choices.keys()),
            {"init-home", "compile", "pm", "ws", \
             "registry", "library", "completion", "test"})

        registry_parser = subparser_action.choices["registry"]
        registry_subparsers = next(
            action
            for action in registry_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertIn("list", registry_subparsers.choices)
        self.assertIn("info", registry_subparsers.choices)

    def test_registry_config_parser_accepts_structured_commands(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "registry",
            "config",
            "set",
            "USE_ROS2_COMPILATION",
            "true",
        ])

        self.assertEqual(args.registry_config_command, "set")
        self.assertEqual(args.setting_name, "USE_ROS2_COMPILATION")
        self.assertEqual(args.setting_value, "true")

    def test_registry_config_defaults_to_list(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["registry", "config"])

        self.assertIsNone(args.registry_config_command)
        self.assertEqual(args.func.__name__, "command_registry_config_list")


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

        self.assertEqual(
            set(ws_subparsers.choices.keys()),
            {"component", "create", "info", "list", "script"},
        )
        self.assertTrue(hasattr(ws_parser, "get_default"))

    def test_ws_defaults_to_gui(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws"])

        with patch("rpp_cli.commands.workspace_main", return_value=0) as mocked_workspace_main:
            result = args.func(args)

        self.assertEqual(result, 0)
        mocked_workspace_main.assert_called_once_with([])

    def test_ws_root_opens_gui_in_folder(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "--root", "as"])

        with patch("rpp_cli.commands.workspace_main", return_value=0) as mocked_workspace_main:
            result = args.func(args)

        self.assertEqual(result, 0)
        mocked_workspace_main.assert_called_once_with(["--root", "as"])

    def test_ws_info_parser_accepts_workspace_root(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "info", "demo-workspace", "--json"])

        self.assertEqual(args.ws_command, "info")
        self.assertEqual(args.workspace, "demo-workspace")
        self.assertTrue(args.json)
        self.assertEqual(args.func.__name__, "command_ws_info")

    def test_ws_info_prints_workspace_summary(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "info", "demo-workspace", "--json"])

        first_script = Mock()
        first_script.path = Path("/tmp/demo-workspace/demo.py")
        first_script.load_description.return_value = {
            "ScriptPath": "demo.py",
            "Language": "python",
        }
        first_component = Mock()
        first_component.folder = Path("/tmp/demo-workspace/.rppws/parts/main")
        first_component.to_dict.return_value = {
            "Id": "main",
            "Name": "Main",
        }
        workspace = Mock()
        workspace.name = "demo-workspace"
        workspace.root = Path("/tmp/demo-workspace")
        workspace.list_scripts.return_value = [first_script]
        workspace.get_part_records.return_value = {"main": first_component}
        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            output = io.StringIO()
            with patch("sys.stdout", output):
                result = args.func(args)

        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "Name": "demo-workspace",
                "Root": "/tmp/demo-workspace",
                "ScriptCount": 1,
                "Scripts": [
                    {
                        "ScriptPath": "demo.py",
                        "Language": "python",
                        "ResolvedPath": "/tmp/demo-workspace/demo.py",
                    }
                ],
                "ComponentCount": 1,
                "Components": [
                    {
                        "Id": "main",
                        "Name": "Main",
                        "Folder": "/tmp/demo-workspace/.rppws/parts/main",
                    }
                ],
            },
        )


    def test_ws_info_defaults_to_current_workspace_and_prints_names(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "info"])
        script = Mock()
        script.path = Path("/tmp/demo-workspace/demo.py")
        script.load_description.return_value = {"ScriptName": "Demo"}
        component = Mock()
        component.folder = Path("/tmp/demo-workspace/.rppws/parts/main")
        component.to_dict.return_value = {"Name": "Main"}
        workspace = Mock()
        workspace.root = Path("/tmp/demo-workspace")
        workspace.list_scripts.return_value = [script]
        workspace.get_part_records.return_value = {"main": component}
        output = io.StringIO()

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace), patch(
            "sys.stdout", output
        ):
            result = args.func(args)

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "Scripts:\n- Demo\nComponents:\n- Main\n")


    def test_ws_script_create_uses_workspace_relative_directory(self):
        parser = self.cli.build_parser()
        with tempfile.TemporaryDirectory() as td:
            workspace_root = Path(td)
            scripts_path = workspace_root / "scripts"
            scripts_path.mkdir()
            args = parser.parse_args([
                "ws",
                "script",
                "create",
                str(workspace_root),
                "demo",
                "--path",
                "scripts",
                "--language",
                "python",
            ])
            workspace = Mock()
            workspace.root = workspace_root
            script = Mock()
            script.path = scripts_path / "demo.py"
            workspace.create_script.return_value = script

            with patch(
                "rpp_cli.commands.Workspace.workspace_exists", return_value=True
            ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
                result = args.func(args)

            self.assertEqual(result, 0)
            workspace.create_script.assert_called_once_with(
                scripts_path / "demo.py", language="python"
            )


    def test_ws_list_filters_registered_workspace_libraries(self):
        parser = self.cli.build_parser()
        with tempfile.TemporaryDirectory() as td:
            workspace_root = Path(td) / "workspace-library"
            workspace_root.mkdir()
            (workspace_root / ".rppws").mkdir()
            non_workspace_root = Path(td) / "plain-library"
            non_workspace_root.mkdir()
            manager = Mock()
            manager.list_plugin_libraries.return_value = [
                {
                    "Name": "workspace_library",
                    "Path": str(workspace_root),
                    "Type": "link",
                    "Version": "0.1.0",
                },
                {
                    "Name": "plain_library",
                    "Path": str(non_workspace_root),
                    "Type": "install",
                    "Version": "0.1.0",
                },
            ]
            catalog = Mock()
            catalog.list_library_scripts.return_value = []
            output = io.StringIO()
            args = parser.parse_args(["ws", "list"])

            with patch("rpp_cli.commands.ScriptCatalog", return_value=catalog), patch(
                "sys.stdout", output
            ):
                result = self.cli.command_ws_list(args, library_manager=manager)

            self.assertEqual(result, 0)
            self.assertEqual(
                output.getvalue(),
                f"- workspace_library: {workspace_root.resolve()}\n",
            )

    def test_ws_script_load_links_registered_script(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws",
            "script",
            "load",
            "source_library::controller",
            "--workspace",
            "target-workspace",
        ])
        workspace = Mock()
        workspace.name = "target_library"
        registered_script = Mock()
        registered_script.script_name = "source_library::controller"
        registered_script.library = "source_library"
        registered_script.path = Path("/tmp/source_library/controller.py")
        registered_script.language = "python"
        catalog = Mock()
        catalog.list_registered_scripts.return_value = [registered_script]

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace), patch(
            "rpp_cli.commands.ScriptCatalog", return_value=catalog
        ):
            result = args.func(args)

        self.assertEqual(result, 0)
        workspace.link_registered_script.assert_called_once_with(
            registered_script.path,
            "source_library::controller",
            "source_library",
            "python",
        )


    def test_ws_component_create_prefers_registered_workspace_name(self):
        workspace = Mock()
        component = Mock()
        component.name = "Controller"
        component.id = "controller-id"
        workspace.create_component.return_value = component
        manager = Mock()
        manager.get_library_path.return_value = "/tmp/jetski"
        args = argparse.Namespace(
            workspace="jetski",
            component_name="Controller",
            plugin_name="rpp_control::Controller",
        )

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists",
            return_value=True,
        ), patch(
            "rpp_cli.commands.open_workspace", return_value=workspace
        ) as open_workspace:
            result = self.cli.command_ws_component_create(
                args, library_manager=manager
            )

        self.assertEqual(result, 0)
        manager.get_library_path.assert_called_once_with("jetski")
        open_workspace.assert_called_once_with(Path("/tmp/jetski").resolve())
        workspace.create_component.assert_called_once_with(
            "Controller", "rpp_control::Controller"
        )


    def test_ws_component_create_calls_workspace_api(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws",
            "component",
            "create",
            "workspace",
            "Controller",
            "rpp_control::Controller",
        ])
        workspace = Mock()
        component = Mock()
        component.name = "Controller"
        component.id = "controller-id"
        workspace.create_component.return_value = component

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            result = args.func(args)

        self.assertEqual(result, 0)
        workspace.create_component.assert_called_once_with(
            "Controller", "rpp_control::Controller"
        )


    def test_ws_script_config_create_resolves_script_and_creates_configuration(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws",
            "script",
            "config",
            "create",
            "workspace",
            "Demo",
            "Alternative",
        ])
        script = Mock()
        script.path = Path("/tmp/workspace/demo.py")
        script.load_description.return_value = {"ScriptName": "Demo"}
        workspace = Mock()
        workspace.root = Path("/tmp/workspace")
        workspace.list_scripts.return_value = [script]

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            result = args.func(args)

        self.assertEqual(result, 0)
        workspace.create_script_configuration.assert_called_once_with(
            script, "Alternative"
        )

    def test_ws_script_config_list_marks_active_configuration(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws", "script", "config", "list", "workspace", "Demo"
        ])
        script = Mock()
        script.path = Path("/tmp/workspace/demo.py")
        script.load_description.return_value = {
            "ScriptName": "Demo",
            "ActiveConfiguration": "Default",
            "Configurations": {"Default": {}, "Alternative": {}},
        }
        workspace = Mock()
        workspace.root = Path("/tmp/workspace")
        workspace.list_scripts.return_value = [script]
        output = io.StringIO()

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace), patch(
            "sys.stdout", output
        ):
            result = args.func(args)

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "* Default\n  Alternative\n")


    def test_ws_script_remove_resolves_script_name(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws", "script", "remove", "workspace", "Demo"
        ])
        script = Mock()
        script.path = Path("/tmp/workspace/demo.py")
        script.load_description.return_value = {"ScriptName": "Demo"}
        workspace = Mock()
        workspace.root = Path("/tmp/workspace")
        workspace.list_scripts.return_value = [script]

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            result = args.func(args)

        self.assertEqual(result, 0)
        workspace.remove_script.assert_called_once_with(script.path)


    def test_ws_script_load_registers_existing_source(self):
        parser = self.cli.build_parser()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "loaded.py"
            source.write_text("class Loaded: pass\n", encoding="utf-8")
            args = parser.parse_args([
                "ws",
                "script",
                "load-file",
                "workspace",
                str(source),
            ])
            workspace = Mock()
            script = Mock()
            script.path = source
            workspace.load_script.return_value = script

            with patch(
                "rpp_cli.commands.Workspace.workspace_exists", return_value=True
            ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
                result = args.func(args)

            self.assertEqual(result, 0)
            workspace.load_script.assert_called_once_with(source.resolve())


    def test_ws_create_requires_a_library_name(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "create", "jetski"])

        self.assertEqual(args.command, "ws")
        self.assertEqual(args.ws_command, "create")
        self.assertEqual(args.library, "jetski")
        self.assertEqual(args.func.__name__, "command_ws_create")

    def test_ws_create_initializes_the_selected_library(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ws", "create", "jetski"])
        library_root = Path("/tmp/libraries/jetski")
        manager = Mock()
        manager.get_library_path.return_value = str(library_root)
        manager.is_valid_plugin_library.return_value = True

        with patch("rpp_cli.commands.create_workspace") as mocked_create_workspace:
            result = self.cli.command_ws_create(args, library_manager=manager)

        self.assertEqual(result, 0)
        manager.get_library_path.assert_called_once_with("jetski")
        manager.is_valid_plugin_library.assert_called_once_with(
            str(library_root)
        )
        mocked_create_workspace.assert_called_once_with(
            library_root, name="jetski"
        )


    def test_ws_component_parser_accepts_full_component_workflow(self):
        parser = self.cli.build_parser()

        assign_args = parser.parse_args([
            "ws",
            "component",
            "assign",
            "workspace",
            "Controller",
            "actuator",
            "Thruster",
            "--configuration",
            "Maneuver",
        ])
        subcomponent_args = parser.parse_args([
            "ws",
            "component",
            "subcomponent",
            "create",
            "workspace",
            "Vehicle",
            "sensor",
            "Dvl",
            "sensors::Dvl",
        ])
        parameter_args = parser.parse_args([
            "ws",
            "component",
            "parameter",
            "set",
            "workspace",
            "Vehicle",
            "gain",
            "2.5",
        ])

        self.assertEqual(assign_args.func.__name__, "command_ws_component_assign")
        self.assertEqual(assign_args.script_name, "Controller")
        self.assertEqual(assign_args.configuration_name, "Maneuver")
        self.assertEqual(
            subcomponent_args.func.__name__,
            "command_ws_component_subcomponent_create",
        )
        self.assertEqual(
            parameter_args.func.__name__,
            "command_ws_component_parameter_set",
        )

    def test_ws_component_assign_resolves_displayed_script_name(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws",
            "component",
            "assign",
            "workspace",
            "Controller",
            "actuator",
            "Thruster",
        ])
        script = Mock()
        script.path = Path("/tmp/workspace/controller.py")
        script.load_description.return_value = {"ScriptName": "Controller"}
        component = Mock()
        component.id = "thruster-id"
        component.name = "Thruster"
        component.plugin_type = "VehicleActuator"
        workspace = Mock()
        workspace.root = Path("/tmp/workspace")
        workspace.list_scripts.return_value = [script]
        workspace.get_component.return_value = component

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            result = args.func(args)

        self.assertEqual(result, 0)
        workspace.assign_component_to_script.assert_called_once_with(
            script,
            "actuator",
            "thruster-id",
            configuration_name=None,
        )

    def test_ws_component_lifecycle_uses_component_name_references(self):
        parser = self.cli.build_parser()
        component = Mock()
        component.id = "thruster-id"
        component.name = "Thruster"
        component.plugin_type = "VehicleActuator"
        component.folder = Path("/tmp/workspace/.rppws/parts/thruster")
        duplicate = Mock()
        duplicate.id = "copy-id"
        duplicate.name = "Thruster Copy"
        workspace = Mock()
        workspace.get_component.return_value = component
        workspace.duplicate_component.return_value = duplicate

        rename_args = parser.parse_args([
            "ws", "component", "rename", "workspace", "Thruster", "Main Thruster"
        ])
        duplicate_args = parser.parse_args([
            "ws", "component", "duplicate", "workspace", "Thruster", "Thruster Copy"
        ])
        remove_args = parser.parse_args([
            "ws", "component", "remove", "workspace", "Thruster"
        ])

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            self.assertEqual(rename_args.func(rename_args), 0)
            self.assertEqual(duplicate_args.func(duplicate_args), 0)
            self.assertEqual(remove_args.func(remove_args), 0)

        workspace.write_part_descriptor.assert_called_once_with(
            component.folder, component
        )
        workspace.duplicate_component.assert_called_once_with(
            "thruster-id", "Thruster Copy"
        )
        workspace.remove_component.assert_called_once_with("thruster-id")

    def test_ws_component_subcomponent_remove_uses_parent_slot_assignment(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws",
            "component",
            "subcomponent",
            "remove",
            "workspace",
            "Vehicle",
            "sensor",
            "Dvl",
        ])
        subcomponent_info = Mock()
        subcomponent_info.id = "dvl-link-id"
        parent = Mock()
        parent.id = "vehicle-id"
        parent.name = "Vehicle"
        parent.subcomponents = {"sensor": subcomponent_info}
        subcomponent = Mock()
        subcomponent.id = "dvl-link-id"
        subcomponent.name = "Dvl"
        workspace = Mock()
        workspace.get_component.return_value = parent
        workspace.get_part_record_by_id.return_value = subcomponent

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            result = args.func(args)

        self.assertEqual(result, 0)
        workspace.remove_subcomponent.assert_called_once_with(
            "vehicle-id",
            "sensor",
            "dvl-link-id",
            handle_parent_update=True,
        )

    def test_ws_component_parameter_set_persists_json_values(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "ws",
            "component",
            "parameter",
            "set",
            "workspace",
            "Vehicle",
            "gain",
            "2.5",
        ])
        component = Mock()
        component.id = "vehicle-id"
        component.name = "Vehicle"
        source_folder = Path("/tmp/workspace/.rppws/parts/vehicle")
        parameters_path = source_folder / "params.py"
        workspace = Mock()
        workspace.get_component.return_value = component
        workspace.resolve_linked_folder.return_value = source_folder
        workspace.component_parameter_store.load.return_value = {"enabled": True}
        workspace.component_parameter_store.save.return_value = parameters_path

        with patch(
            "rpp_cli.commands.Workspace.workspace_exists", return_value=True
        ), patch("rpp_cli.commands.open_workspace", return_value=workspace):
            result = args.func(args)

        self.assertEqual(result, 0)
        workspace.component_parameter_store.save.assert_called_once_with(
            source_folder,
            {"enabled": True, "gain": 2.5},
        )


if __name__ == "__main__":
    unittest.main()