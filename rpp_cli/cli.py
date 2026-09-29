#!/usr/bin/env python3
"""rpp command line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from rpp_plugin_registrator import registry_config as rp

from .commands import (
    command_completion,
    command_library,
    command_test,
    command_describe,
    command_init_home,
    command_pm,
    command_registry_info,
    command_list_registry,
    command_ws,
    command_ws_create,
    command_ws_info,
    command_ws_list,
    command_ws_component_assign,
    command_ws_component_context,
    command_ws_component_create,
    command_ws_component_duplicate,
    command_ws_component_info,
    command_ws_component_list,
    command_ws_component_parameter_get,
    command_ws_component_parameter_set,
    command_ws_component_remove,
    command_ws_component_rename,
    command_ws_component_subcomponent_assign,
    command_ws_component_subcomponent_create,
    command_ws_component_subcomponent_remove,
    command_ws_component_unassign,
    command_ws_script_config_activate,
    command_ws_script_config_copy,
    command_ws_script_config_create,
    command_ws_script_config_import,
    command_ws_script_config_list,
    command_ws_script_list,
    command_ws_script_config_remove,
    command_ws_script_config_rename,
    command_ws_script_create,
    command_ws_script_load,
    command_ws_script_load_file,
    command_ws_script_remove,
    command_compile,
    command_registry_config_get,
    command_registry_config_list,
    command_registry_config_set,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="rpp command line interface")
    parser.add_argument(
        "--rpp-home",
        default=None,
        help="RPP registry home directory (default: ~/.rpp)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-home",
        help="create default ~/.rpp folder structure for plugin metadata",
    )
    init_parser.add_argument(
        "--override",
        action="store_true",
        help="override existing ~/.rpp folder structure if it exists",
    )
    init_parser.add_argument(
        "--init-anot-only",
        action="store_true",
        help="initialize only the Anot plugin type",
    )
    init_parser.set_defaults(func=command_init_home)

    pm_parser = subparsers.add_parser(
        "pm",
        help="launch the plugin manager GUI",
    )
    pm_parser.set_defaults(func=command_pm)

    ws_parser = subparsers.add_parser(
        "ws",
        help="workspace tools",
    )
    ws_parser.add_argument(
        "--root",
        default=None,
        help="workspace folder to open in the GUI",
    )
    ws_subparsers = ws_parser.add_subparsers(dest="ws_command")

    ws_create_parser = ws_subparsers.add_parser(
        "create",
        help="initialize an RPP workspace in a registered plugin library",
    )
    ws_create_parser.add_argument(
        "library",
        help="registered plugin library name to use as the workspace root",
    )
    ws_create_parser.set_defaults(func=command_ws_create)

    ws_info_parser = ws_subparsers.add_parser(
        "info",
        help="print a workspace summary",
    )
    ws_info_parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="workspace root directory (default: current directory)",
    )
    ws_info_parser.add_argument(
        "--json",
        action="store_true",
        help="print detailed workspace, script, and component data as JSON",
    )
    ws_info_parser.set_defaults(func=command_ws_info)

    ws_list_parser = ws_subparsers.add_parser(
        "list",
        help="list registered libraries that are workspaces",
    )
    ws_list_parser.add_argument(
        "--json",
        action="store_true",
        help="print workspace and script references as JSON",
    )
    ws_list_parser.set_defaults(func=command_ws_list)

    ws_script_parser = ws_subparsers.add_parser(
        "script",
        help="manage workspace scripts",
    )
    ws_script_subparsers = ws_script_parser.add_subparsers(
        dest="ws_script_command",
        required=True,
    )
    ws_script_list_parser = ws_script_subparsers.add_parser(
        "list",
        help="list scripts in a workspace",
    )
    ws_script_list_parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="workspace root directory or registered workspace name",
    )
    ws_script_list_parser.add_argument("--json", action="store_true")
    ws_script_list_parser.set_defaults(func=command_ws_script_list)

    ws_script_create_parser = ws_script_subparsers.add_parser(
        "create",
        help="create a workspace script",
    )
    ws_script_create_parser.add_argument("workspace", help="workspace root directory")
    ws_script_create_parser.add_argument("name", help="script filename without a directory")
    ws_script_create_parser.add_argument(
        "--path",
        default=".",
        help="existing directory relative to the workspace root (default: .)",
    )
    ws_script_create_parser.add_argument(
        "--language",
        choices=("python", "cpp"),
        default="python",
        help="script language when the name has no extension (default: python)",
    )
    ws_script_create_parser.set_defaults(func=command_ws_script_create)

    ws_script_load_parser = ws_script_subparsers.add_parser(
        "load",
        help="load a script from a registered workspace library",
    )
    ws_script_load_parser.add_argument(
        "script_name",
        help="script reference from 'rpp ws list', or a library name with one script",
    )
    ws_script_load_parser.add_argument(
        "--workspace",
        default=".",
        help="target workspace root directory (default: current directory)",
    )
    ws_script_load_parser.set_defaults(func=command_ws_script_load)

    ws_script_load_file_parser = ws_script_subparsers.add_parser(
        "load-file",
        help="load an existing script file into a workspace",
    )
    ws_script_load_file_parser.add_argument(
        "workspace", help="workspace root directory"
    )
    ws_script_load_file_parser.add_argument("source", help="existing script file")
    ws_script_load_file_parser.set_defaults(func=command_ws_script_load_file)

    ws_script_remove_parser = ws_script_subparsers.add_parser(
        "remove",
        help="remove a script from a workspace",
    )
    ws_script_remove_parser.add_argument("workspace", help="workspace root directory")
    ws_script_remove_parser.add_argument(
        "script_name", help="script name or path shown by 'rpp ws info'"
    )
    ws_script_remove_parser.set_defaults(func=command_ws_script_remove)

    ws_script_config_parser = ws_script_subparsers.add_parser(
        "config",
        help="manage script configurations",
    )
    ws_script_config_subparsers = ws_script_config_parser.add_subparsers(
        dest="ws_script_config_command",
        required=True,
    )

    ws_script_config_list_parser = ws_script_config_subparsers.add_parser(
        "list", help="list script configurations"
    )
    ws_script_config_list_parser.add_argument("workspace")
    ws_script_config_list_parser.add_argument("script_name")
    ws_script_config_list_parser.add_argument("--json", action="store_true")
    ws_script_config_list_parser.set_defaults(func=command_ws_script_config_list)

    ws_script_config_create_parser = ws_script_config_subparsers.add_parser(
        "create", help="create a script configuration"
    )
    ws_script_config_create_parser.add_argument("workspace")
    ws_script_config_create_parser.add_argument("script_name")
    ws_script_config_create_parser.add_argument("configuration_name")
    ws_script_config_create_parser.set_defaults(func=command_ws_script_config_create)

    ws_script_config_copy_parser = ws_script_config_subparsers.add_parser(
        "copy", help="copy a script configuration"
    )
    ws_script_config_copy_parser.add_argument("workspace")
    ws_script_config_copy_parser.add_argument("script_name")
    ws_script_config_copy_parser.add_argument("source_configuration_name")
    ws_script_config_copy_parser.add_argument("configuration_name")
    ws_script_config_copy_parser.set_defaults(func=command_ws_script_config_copy)

    ws_script_config_import_parser = ws_script_config_subparsers.add_parser(
        "import",
        help="import a configuration and its components from a linked script",
    )
    ws_script_config_import_parser.add_argument("workspace")
    ws_script_config_import_parser.add_argument(
        "source_script_name",
        help="linked source script shown by rpp ws list",
    )
    ws_script_config_import_parser.add_argument("configuration_name")
    ws_script_config_import_parser.set_defaults(
        func=command_ws_script_config_import
    )

    ws_script_config_rename_parser = ws_script_config_subparsers.add_parser(
        "rename", help="rename a script configuration"
    )
    ws_script_config_rename_parser.add_argument("workspace")
    ws_script_config_rename_parser.add_argument("script_name")
    ws_script_config_rename_parser.add_argument("configuration_name")
    ws_script_config_rename_parser.add_argument("new_configuration_name")
    ws_script_config_rename_parser.set_defaults(func=command_ws_script_config_rename)

    ws_script_config_remove_parser = ws_script_config_subparsers.add_parser(
        "remove", help="remove a script configuration"
    )
    ws_script_config_remove_parser.add_argument("workspace")
    ws_script_config_remove_parser.add_argument("script_name")
    ws_script_config_remove_parser.add_argument("configuration_name")
    ws_script_config_remove_parser.set_defaults(func=command_ws_script_config_remove)

    ws_script_config_activate_parser = ws_script_config_subparsers.add_parser(
        "activate", help="activate a script configuration"
    )
    ws_script_config_activate_parser.add_argument("workspace")
    ws_script_config_activate_parser.add_argument("script_name")
    ws_script_config_activate_parser.add_argument("configuration_name")
    ws_script_config_activate_parser.set_defaults(func=command_ws_script_config_activate)

    ws_component_parser = ws_subparsers.add_parser(
        "component",
        help="manage workspace components",
    )
    ws_component_subparsers = ws_component_parser.add_subparsers(
        dest="ws_component_command",
        required=True,
    )
    ws_component_create_parser = ws_component_subparsers.add_parser(
        "create",
        help="create a workspace component from a registered plugin",
    )
    ws_component_create_parser.add_argument("workspace")
    ws_component_create_parser.add_argument("component_name")
    ws_component_create_parser.add_argument("plugin_name")
    ws_component_create_parser.set_defaults(func=command_ws_component_create)

    ws_component_list_parser = ws_component_subparsers.add_parser(
        "list",
        help="list workspace components",
    )
    ws_component_list_parser.add_argument("workspace")
    ws_component_list_parser.add_argument(
        "--json",
        action="store_true",
        help="print detailed component data as JSON",
    )
    ws_component_list_parser.set_defaults(func=command_ws_component_list)

    ws_component_info_parser = ws_component_subparsers.add_parser(
        "info",
        help="print detailed component data",
    )
    ws_component_info_parser.add_argument("workspace")
    ws_component_info_parser.add_argument(
        "component_reference",
        help="component name or ID from 'rpp ws component list'",
    )
    ws_component_info_parser.set_defaults(func=command_ws_component_info)

    ws_component_rename_parser = ws_component_subparsers.add_parser(
        "rename",
        help="rename a workspace component",
    )
    ws_component_rename_parser.add_argument("workspace")
    ws_component_rename_parser.add_argument("component_reference")
    ws_component_rename_parser.add_argument("new_name")
    ws_component_rename_parser.set_defaults(func=command_ws_component_rename)

    ws_component_duplicate_parser = ws_component_subparsers.add_parser(
        "duplicate",
        help="duplicate a workspace component",
    )
    ws_component_duplicate_parser.add_argument("workspace")
    ws_component_duplicate_parser.add_argument("component_reference")
    ws_component_duplicate_parser.add_argument(
        "new_name",
        nargs="?",
        default=None,
        help="name for the duplicate (default: original name with _copy)",
    )
    ws_component_duplicate_parser.set_defaults(func=command_ws_component_duplicate)

    ws_component_remove_parser = ws_component_subparsers.add_parser(
        "remove",
        help="remove a workspace component",
    )
    ws_component_remove_parser.add_argument("workspace")
    ws_component_remove_parser.add_argument("component_reference")
    ws_component_remove_parser.set_defaults(func=command_ws_component_remove)

    ws_component_assign_parser = ws_component_subparsers.add_parser(
        "assign",
        help="assign a component to a script slot",
    )
    ws_component_assign_parser.add_argument("workspace")
    ws_component_assign_parser.add_argument(
        "script_name",
        help="script name, filename, or path shown by 'rpp ws info'",
    )
    ws_component_assign_parser.add_argument("slot_name")
    ws_component_assign_parser.add_argument("component_reference")
    ws_component_assign_parser.add_argument(
        "--configuration",
        dest="configuration_name",
        default=None,
        help="script configuration (default: active configuration)",
    )
    ws_component_assign_parser.set_defaults(func=command_ws_component_assign)

    ws_component_unassign_parser = ws_component_subparsers.add_parser(
        "unassign",
        help="remove a component assignment from a script",
    )
    ws_component_unassign_parser.add_argument("workspace")
    ws_component_unassign_parser.add_argument(
        "script_name",
        help="script name, filename, or path shown by 'rpp ws info'",
    )
    ws_component_unassign_parser.add_argument("component_reference")
    ws_component_unassign_parser.add_argument(
        "--slot",
        dest="slot_name",
        default=None,
        help="remove only from this script slot (default: all slots)",
    )
    ws_component_unassign_parser.add_argument(
        "--configuration",
        dest="configuration_name",
        default=None,
        help="script configuration (default: active configuration)",
    )
    ws_component_unassign_parser.set_defaults(func=command_ws_component_unassign)

    ws_component_subcomponent_parser = ws_component_subparsers.add_parser(
        "subcomponent",
        help="manage subcomponents assigned to a parent component",
    )
    ws_component_subcomponent_subparsers = (
        ws_component_subcomponent_parser.add_subparsers(
            dest="ws_component_subcomponent_command",
            required=True,
        )
    )

    ws_subcomponent_create_parser = (
        ws_component_subcomponent_subparsers.add_parser(
            "create",
            help="create a child component in a parent slot",
        )
    )
    ws_subcomponent_create_parser.add_argument("workspace")
    ws_subcomponent_create_parser.add_argument("parent_component")
    ws_subcomponent_create_parser.add_argument("slot_name")
    ws_subcomponent_create_parser.add_argument("component_name")
    ws_subcomponent_create_parser.add_argument("plugin_name")
    ws_subcomponent_create_parser.set_defaults(
        func=command_ws_component_subcomponent_create
    )

    ws_subcomponent_assign_parser = (
        ws_component_subcomponent_subparsers.add_parser(
            "assign",
            help="assign an existing component to a parent slot",
        )
    )
    ws_subcomponent_assign_parser.add_argument("workspace")
    ws_subcomponent_assign_parser.add_argument("parent_component")
    ws_subcomponent_assign_parser.add_argument("slot_name")
    ws_subcomponent_assign_parser.add_argument("component_reference")
    ws_subcomponent_assign_parser.set_defaults(
        func=command_ws_component_subcomponent_assign
    )

    ws_subcomponent_remove_parser = (
        ws_component_subcomponent_subparsers.add_parser(
            "remove",
            help="remove a child component from a parent slot",
        )
    )
    ws_subcomponent_remove_parser.add_argument("workspace")
    ws_subcomponent_remove_parser.add_argument("parent_component")
    ws_subcomponent_remove_parser.add_argument("slot_name")
    ws_subcomponent_remove_parser.add_argument("component_reference")
    ws_subcomponent_remove_parser.set_defaults(
        func=command_ws_component_subcomponent_remove
    )

    ws_component_parameter_parser = ws_component_subparsers.add_parser(
        "parameter",
        help="get or set persisted component parameters",
    )
    ws_component_parameter_subparsers = (
        ws_component_parameter_parser.add_subparsers(
            dest="ws_component_parameter_command",
            required=True,
        )
    )

    ws_component_parameter_get_parser = (
        ws_component_parameter_subparsers.add_parser(
            "get",
            help="print one persisted parameter or all parameters",
        )
    )
    ws_component_parameter_get_parser.add_argument("workspace")
    ws_component_parameter_get_parser.add_argument("component_reference")
    ws_component_parameter_get_parser.add_argument(
        "parameter_name",
        nargs="?",
        default=None,
    )
    ws_component_parameter_get_parser.set_defaults(
        func=command_ws_component_parameter_get
    )

    ws_component_parameter_set_parser = (
        ws_component_parameter_subparsers.add_parser(
            "set",
            help="set one persisted parameter; JSON values retain their type",
        )
    )
    ws_component_parameter_set_parser.add_argument("workspace")
    ws_component_parameter_set_parser.add_argument("component_reference")
    ws_component_parameter_set_parser.add_argument("parameter_name")
    ws_component_parameter_set_parser.add_argument("value")
    ws_component_parameter_set_parser.set_defaults(
        func=command_ws_component_parameter_set
    )

    ws_component_context_parser = ws_component_subparsers.add_parser(
        "context",
        help="print the component folder and parameter file paths used by the GUI",
    )
    ws_component_context_parser.add_argument("workspace")
    ws_component_context_parser.add_argument("component_reference")
    ws_component_context_parser.set_defaults(func=command_ws_component_context)

    ws_parser.set_defaults(func=command_ws)

    # Registry commands
    registry_parser = subparsers.add_parser(
        "registry",
        help="registry-related commands",
    )
    registry_subparsers = registry_parser.add_subparsers(dest="registry_command", required=True)

    describe_parser = registry_subparsers.add_parser(
        "describe",
        help="print plugin description JSON inferred from source (read-only)",
    )
    describe_parser.add_argument("source", help="path to plugin source file (.cpp or .py)")
    describe_parser.add_argument("--language", choices=["cpp", "python"], help="source language override")
    describe_parser.add_argument("--plugin-id", "--id", dest="plugin_id", help="override plugin id")
    describe_parser.set_defaults(func=command_describe)

    registry_list_parser = registry_subparsers.add_parser(
        "list",
        help="list plugins currently registered in the rpp registry",
    )
    registry_list_parser.add_argument(
        "--registry",
        default=None,
        help="path to registry JSON file",
    )
    registry_list_parser.add_argument("--json",
        action="store_true", help="output registry as JSON")
    registry_list_parser.add_argument("--plugins",
        action="store_true", help="list plugins instead of plugin types")
    registry_list_parser.set_defaults(func=command_list_registry)

    registry_info_parser = registry_subparsers.add_parser(
        "info",
        help="print registered plugin description JSON by plugin tag",
    )
    registry_info_parser.add_argument("tag", help="plugin tag/id to inspect")
    registry_info_parser.add_argument(
        "--registry",
        default=None,
        help="path to registry JSON file",
    )
    registry_info_parser.set_defaults(func=command_registry_info)

    registry_config_parser = registry_subparsers.add_parser(
        "config",
        help="manage registry configuration",
    )
    registry_config_subparsers = registry_config_parser.add_subparsers(
        dest="registry_config_command",
    )
    registry_config_parser.set_defaults(func=command_registry_config_list)

    registry_config_list_parser = registry_config_subparsers.add_parser(
        "list",
        help="print configured registry settings",
    )
    registry_config_list_parser.set_defaults(func=command_registry_config_list)

    registry_config_get_parser = registry_config_subparsers.add_parser(
        "get",
        help="print one registry setting",
    )
    registry_config_get_parser.add_argument("setting_name")
    registry_config_get_parser.set_defaults(func=command_registry_config_get)

    registry_config_set_parser = registry_config_subparsers.add_parser(
        "set",
        help="set one registry setting",
    )
    registry_config_set_parser.add_argument("setting_name")
    registry_config_set_parser.add_argument("setting_value")
    registry_config_set_parser.set_defaults(func=command_registry_config_set)


    # Library commands
    library_parser = subparsers.add_parser(
        "library",
        help="library-related commands",
    )
    library_parser.add_argument(
        "library_args",
        nargs=argparse.REMAINDER,
        help=(
            "library command args, e.g. 'register <lib_path>' or "
            "'<library> register <source> [--type]'"
        ),
    )
    library_parser.set_defaults(func=command_library)

    test_parser = subparsers.add_parser(
        "test",
        help="test related commands",
    )

    test_parser.add_argument(
        "test_args",
        nargs=argparse.REMAINDER,
        help="test command args, e.g. ''",
    )
    test_parser.set_defaults(func=command_test)


    compile_parser = subparsers.add_parser(
        "compile",
        help="compile plugin source file into a shared library",
    )
    compile_parser.add_argument("source", help="path to plugin source file (.cpp or .py)")
    compile_parser.add_argument("--plugin-type-name", help="plugin type name for C++ plugin compilation")
    compile_parser.add_argument("--library", help="Library name for C++ plugin compilation")
    compile_parser.add_argument("--verbose", help="enable verbose output", action="store_true")
    compile_parser.add_argument("--type",
        choices=["plugin", "plugin-type"],
        default="plugin",
        help="type of source to compile (default: plugin)")
    compile_parser.set_defaults(func=command_compile)


    completion_parser = subparsers.add_parser(
        "completion",
        help="print shell completion script",
    )
    completion_parser.add_argument("--shell", default="bash", choices=["bash"], help="target shell")
    completion_parser.set_defaults(func=command_completion)

    return parser


def configure_rpp_home(rpp_home: str | None) -> None:
    if rpp_home is None:
        return
    rp.RPP_HOME = Path(rpp_home).expanduser().resolve()
    rp.reset_module()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_rpp_home(args.rpp_home)
    result = args.func(args)
    if isinstance(result, int):
        return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
