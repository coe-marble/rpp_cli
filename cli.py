#!/usr/bin/env python3
"""rpp command line interface."""

from __future__ import annotations

import argparse

from commands import (
    command_add,
    command_describe,
    command_generate_interface,
    command_init_home,
    command_list_registry,
    command_register,
    command_scaffold,
    command_unregister,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="rpp command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-home",
        help="create default ~/.rpp folder structure for plugin metadata",
    )
    init_parser.set_defaults(func=command_init_home)

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

    register_parser = registry_subparsers.add_parser(
        "register",
        help="describe plugin source and register it (or register existing description json)",
    )
    register_parser.add_argument("source", nargs="?", help="path to plugin source (.cpp/.py) or description JSON file")
    register_parser.add_argument(
        "--folder",
        help="register all description JSON files from a folder",
    )
    register_parser.add_argument("--language", choices=["cpp", "python"], help="source language override")
    register_parser.add_argument(
        "--plugin-id",
        "--id",
        dest="plugin_id",
        help="override plugin id when describing from source",
    )
    register_parser.add_argument(
        "--description",
        help="description file output path when describing from source",
    )
    register_parser.add_argument(
        "--registry",
        default=None,
        help="path to registry JSON file",
    )
    register_parser.set_defaults(func=command_register)

    unregister_parser = registry_subparsers.add_parser(
        "unregister",
        help="remove a plugin from the rpp registry by plugin id",
    )
    unregister_parser.add_argument("plugin_id", help="plugin id to remove")
    unregister_parser.add_argument(
        "--registry",
        default=None,
        help="path to registry JSON file",
    )
    unregister_parser.set_defaults(func=command_unregister)

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

    interface_parser = registry_subparsers.add_parser(
        "generate-interface",
        help="generate a language interface from a plugin description",
    )
    interface_parser.add_argument("description", help="path to plugin description JSON file")
    interface_parser.add_argument("--target-language", required=True, choices=["python", "cpp"])
    interface_parser.add_argument("--output", required=True, help="output interface file path")
    interface_parser.set_defaults(func=command_generate_interface)

    scaffold_parser = registry_subparsers.add_parser(
        "scaffold",
        help="create a starter plugin source file",
    )
    scaffold_parser.add_argument("--language", required=True, choices=["cpp", "python"])
    scaffold_parser.add_argument("--plugin-id", required=True, help="plugin id and default plugin name")
    scaffold_parser.add_argument("--class-name", help="plugin class name override")
    scaffold_parser.add_argument("--output", required=True, help="output source file path")
    scaffold_parser.set_defaults(func=command_scaffold)

    add_parser = registry_subparsers.add_parser(
        "add",
        help="describe + register a plugin source with optional interface generation",
    )
    add_parser.add_argument("source", help="path to plugin source file (.cpp or .py)")
    add_parser.add_argument("--plugin-id", "--id", dest="plugin_id", help="override plugin id")
    add_parser.add_argument("--language", choices=["cpp", "python"], help="source language override")
    add_parser.add_argument("--description", help="output plugin description JSON file")
    add_parser.add_argument(
        "--registry",
        default=None,
        help="path to registry JSON file",
    )
    add_parser.add_argument(
        "--interface-language",
        action="append",
        choices=["python", "cpp"],
        help="generate interface(s) for selected target language(s); repeatable",
    )
    add_parser.add_argument(
        "--interfaces-dir",
        default=None,
        help="directory where generated interfaces are stored",
    )
    add_parser.set_defaults(func=command_add)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
