from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from rpp_plugin_registrator.interface_generators import generate_interface
from rpp_plugin_registrator.plugin_description_api import (
    infer_language_from_path,
    parse_cpp_plugin,
    parse_python_plugin,
    resolve_plugin_id_override,
)
import rpp_plugin_registrator.registry_api as registry_api
from rpp_plugin_registrator.scaffold import scaffold_cpp, scaffold_python


# Allow callers/tests to override home paths via commands.RPP_HOME.
RPP_HOME = registry_api.RPP_HOME


def _describe_source(source_path: Path, language: str | None, plugin_id: str | None) -> Dict:
    resolved_language = language or infer_language_from_path(source_path)
    if resolved_language == "cpp":
        return parse_cpp_plugin(source_path, plugin_id)
    if resolved_language == "python":
        return parse_python_plugin(source_path, plugin_id)
    raise ValueError(f"Unsupported source language '{resolved_language}'.")


def _describe_from_args(args) -> Dict:
    source_path = Path(args.source).expanduser().resolve()
    plugin_id = resolve_plugin_id_override(args)
    return _describe_source(source_path, args.language, plugin_id)


def _prepare_registry_target(args):
    registry_api.RPP_HOME = RPP_HOME
    registry_api.ensure_rpp_layout()
    paths = registry_api.get_rpp_paths()
    return paths, registry_api.resolve_output_path(args.registry, paths["registry"])


def _validate_description_uniqueness(description: Dict, registry_path: Path) -> str:
    registry = registry_api.load_registry(registry_path=registry_path)
    plugins = registry.setdefault("Plugins", {})
    plugin = description.get("Plugin", {})
    plugin_id = plugin.get("Id")
    registry_api.validate_unique_plugin_id(plugin_id, plugins)
    class_name = plugin.get("ClassName")
    registry_api.validate_unique_class_name(class_name, plugin_id, plugins)
    return plugin_id


def command_describe(args) -> None:
    source_path = Path(args.source).resolve()
    description = _describe_source(source_path, args.language, resolve_plugin_id_override(args))
    print(json.dumps(description, indent=2, sort_keys=False))


def command_register(args) -> None:
    paths, registry_path = _prepare_registry_target(args)

    if args.folder:
        folder_path = Path(args.folder).expanduser().resolve()
        registered_files = registry_api.register_descriptions_in_folder(folder_path, registry_path)
        if not registered_files:
            print(f"No plugin description files found in folder: {folder_path}")
        else:
            print(f"Registered {len(registered_files)} plugin descriptions from folder: {folder_path}")
            for file_path in registered_files:
                print(f"- {file_path}")
        print(f"Registry path: {registry_path}")
        return

    if not args.source:
        raise ValueError("Either 'source' or '--folder' must be provided for register command.")

    source_path = Path(args.source).expanduser().resolve()
    if source_path.suffix.lower() == ".json":
        registry_api.register_description(source_path, registry_path)
        print(f"Registered plugin from description: {source_path}")
        print(f"Registry path: {registry_path}")
        return

    description = _describe_from_args(args)
    plugin_id = _validate_description_uniqueness(description, registry_path)
    description_path = registry_api.resolve_output_path(args.description, paths["descriptions"] / f"{plugin_id}.plugin.json")
    registry_api.write_json(description_path, description)
    registry_api.register_description(description_path, registry_path)

    print(f"Described and registered plugin '{plugin_id}'")
    print(f"Source: {source_path}")
    print(f"Description: {description_path}")
    print(f"Registry path: {registry_path}")


def command_unregister(args) -> None:
    _, registry_path = _prepare_registry_target(args)
    removed = registry_api.unregister_plugin(args.plugin_id, registry_path)
    if removed:
        print(f"Unregistered plugin '{args.plugin_id}' from {registry_path}")
    else:
        print(f"Plugin '{args.plugin_id}' not found in {registry_path}")


def command_generate_interface(args) -> None:
    description_path = Path(args.description).resolve()
    output_path = Path(args.output).resolve()
    generate_interface(description_path, args.target_language, output_path)
    print(f"Generated {args.target_language} interface: {output_path}")


def command_scaffold(args) -> None:
    output_path = Path(args.output).resolve()
    class_name = args.class_name or f"{args.plugin_id.title().replace('_', '')}Plugin"
    if args.language == "cpp":
        scaffold_cpp(args.plugin_id, class_name, output_path)
    elif args.language == "python":
        scaffold_python(args.plugin_id, class_name, output_path)
    else:
        raise ValueError(f"Unsupported scaffold language '{args.language}'.")
    print(f"Scaffolded {args.language} plugin source: {output_path}")


def command_init_home(args) -> None:
    registry_api.RPP_HOME = RPP_HOME
    registry_api.ensure_rpp_layout(override_initialization=True)
    paths = registry_api.get_rpp_paths()
    print(f"Initialized rpp home at: {paths['home']}")
    print(f"Descriptions: {paths['descriptions']}")
    print(f"Interfaces: {paths['interfaces']}")
    print(f"Registry: {paths['registry']}")


def command_list_registry(args) -> None:
    paths = registry_api.get_rpp_paths()
    registry_path = registry_api.resolve_output_path(args.registry, paths["registry"])
    registry = registry_api.list_registered_plugins(registry_path)
    plugins = registry.get("Plugins", {})

    if args.format == "json":
        print(json.dumps(registry, indent=2, sort_keys=False))
        return

    print(f"Registry: {registry_path}")
    print(f"Total plugins: {len(plugins)}")
    for plugin_id in sorted(plugins):
        data = plugins[plugin_id]
        source_language = data.get("SourceLanguage", "?")
        plugin_name = data.get("Name", "?")
        print(f"- {plugin_id} [{source_language}] {plugin_name}")


def command_add(args) -> None:
    paths, registry_path = _prepare_registry_target(args)
    description = _describe_from_args(args)
    plugin_id = _validate_description_uniqueness(description, registry_path)

    description_path = registry_api.resolve_output_path(args.description, paths["descriptions"] / f"{plugin_id}.plugin.json")
    registry_api.write_json(description_path, description)
    registry_api.register_description(description_path, registry_path)

    generated_paths = []
    if args.interface_language:
        interfaces_dir = registry_api.resolve_output_path(args.interfaces_dir, paths["interfaces"])
        extension_by_language = {"python": "py", "cpp": "hpp"}
        for target_lang in args.interface_language:
            output_path = interfaces_dir / f"{plugin_id}_plugin_interface.{extension_by_language[target_lang]}"
            generate_interface(description_path, target_lang, output_path)
            generated_paths.append(output_path)

    print(f"Added plugin '{plugin_id}'")
    print(f"Description: {description_path}")
    print(f"Registry: {registry_path}")
    if generated_paths:
        print("Generated interfaces:")
        for path in generated_paths:
            print(f"- {path}")
