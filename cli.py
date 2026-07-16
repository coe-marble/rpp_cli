#!/usr/bin/env python3
"""rpp command line interface."""

from __future__ import annotations

import argparse

from commands import (
    command_completion,
    command_library,
    command_test,
    command_describe,
    command_init_home,
    command_pm,
    command_registry_info,
    command_list_registry,
    command_scaffold,
    command_ws,
    command_ws_create,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="rpp command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-home",
        help="create default ~/.rpp folder structure for plugin metadata",
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
        help="create a new RPP workspace on disk",
    )
    ws_create_parser.add_argument("name", help="workspace name")
    ws_create_parser.add_argument(
        "--root",
        default=".",
        help="root directory where the workspace folder will be created (default: current directory)",
    )
    ws_create_parser.add_argument("--overwrite", action="store_true", help="overwrite an existing empty root")
    ws_create_parser.set_defaults(func=command_ws_create)

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
    registry_list_parser.add_argument("--format", choices=["text", "json"], default="text")
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

    scaffold_parser = registry_subparsers.add_parser(
        "scaffold",
        help="create a starter plugin source file",
    )
    scaffold_parser.add_argument("--language", required=True, choices=["cpp", "python"])
    scaffold_parser.add_argument("--plugin-id", required=True, help="plugin id and default plugin name")
    scaffold_parser.add_argument("--class-name", help="plugin class name override")
    scaffold_parser.add_argument("--output", required=True, help="output source file path")
    scaffold_parser.set_defaults(func=command_scaffold)

    # Library commands
    library_parser = subparsers.add_parser(
        "library",
        help="library-related commands",
    )
    library_parser.add_argument(
        "library_args",
        nargs=argparse.REMAINDER,
        help="library command args, e.g. 'register <lib_path>' or '<lib_name> register <file_name>'",
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


    completion_parser = subparsers.add_parser(
        "completion",
        help="print shell completion script",
    )
    completion_parser.add_argument("--shell", default="bash", choices=["bash"], help="target shell")
    completion_parser.set_defaults(func=command_completion)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    if isinstance(result, int):
        return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
