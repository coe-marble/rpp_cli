from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import re
import os
import tempfile
from typing import Any, Dict, Optional, Tuple


from rpp_plugin_registrator.payload_builders import build_plugin_type_info_payload
from rpp_plugin_registrator.plugin_descriptors import (
    parse_plugin_file, parse_plugin_type_file
)
from rpp_plugin_registrator.plugin_validators import validate_plugin, validate_plugin_type
from rpp_plugin_registrator.library_manager import LibraryManager
import rpp_plugin_registrator.plugin_type_registrator as registry_api
import rpp_plugin_registrator.registry_config as rp
from rpp_plugin_registrator.plugin_descriptors.core import PluginTypeInfo, PluginInfo, plugin_id_from_name
from rpp_orchestrator.cli import main as workspace_main
from rpp_orchestrator.script_catalog import ScriptCatalog
from rpp_orchestrator.script_handle import language_spec
from rpp_orchestrator.workspace import Workspace, create_workspace, open_workspace
from rpp_plugin_registrator.supported_plugins_and_types import (
    get_supported_plugin_type_extensions,
    get_supported_plugin_extensions
)

from .testing import setup_tmp_rpp_with_test_plugins


def _make_description_payload(parsed, validation_result, is_plugin=False) -> Dict:
    payload = {
        "SourceFile": str(parsed.get("SourceFile")),
        "SourceLanguage": parsed.get("SourceLanguage"),
        "ClassName": parsed.get("ClassName"),
        "ValidationResult": {
            "IsValid": validation_result.is_valid,
            "Message": validation_result.message,
        },
    }
    if is_plugin and validation_result.is_valid:
        payload["PluginType"] = validation_result.validation_data.plugin_type
    else:
        pass
    return payload

def _describe_source(source_path: Path) -> Dict:
    plugin_type_extensions = get_supported_plugin_type_extensions()
    source_ext = source_path.suffix.lower()
    descriptions = []
    if source_ext in plugin_type_extensions:
        parsed = parse_plugin_type_file(source_path)
        if not parsed.is_valid or not parsed.data.plugins:
            return descriptions
        for p in parsed.data.plugins:
            iface_desc = parsed.data.interfaces.get(p.interface_name)
            desc = PluginTypeInfo(
                info=build_plugin_type_info_payload(p, iface_desc, source_path),
                register_data=None
            )
            validation_result = validate_plugin_type(desc)
            descriptions.append(_make_description_payload(desc.info, validation_result, is_plugin=False))
        return descriptions
    plugin_extensions = get_supported_plugin_extensions()
    if source_ext in plugin_extensions:
        parsed = parse_plugin_file(source_path)
        if not parsed.is_valid or not parsed.data.plugins:
            return descriptions
        plugin_types = registry_api.get_plugin_types()
        for p in parsed.data.plugins:
            desc = PluginInfo(
                info=p,
                register_data=None
            )
            validation_result = validate_plugin(desc, plugin_types)
            descriptions.append(_make_description_payload(p, validation_result, is_plugin=True))
    return descriptions



def _get_library_manager(library_manager=None) -> LibraryManager:
    return library_manager if library_manager is not None else LibraryManager()

def command_describe(args) -> None:
    lm = _get_library_manager()
    source_path = Path(args.source).resolve()
    description = _describe_source(source_path)
    print(json.dumps(description, indent=2, sort_keys=False))


def command_library_register(args, library_manager=None) -> int:
    if hasattr(args, "lib_path") and getattr(args, "lib_path") is not None:
        manager = _get_library_manager(library_manager)
        lib_path = Path(args.lib_path).expanduser().resolve()
        if not lib_path.exists():
            print(f"Library path does not exist: {lib_path}")
            return 1

        link_register = bool(getattr(args, "link", False))
        registered_path = manager.register_plugin_library(str(lib_path), link_register=link_register)
        if link_register:
            print(f"Linked library: {registered_path}")
        else:
            print(f"Registered library: {registered_path}")
        return 0
    return 1


def command_library_unregister(args, library_manager: LibraryManager = None) -> None:
    if hasattr(args, "lib_name") and getattr(args, "lib_name") is not None:
        manager = _get_library_manager(library_manager)
        removed = manager.remove_plugin_library(args.lib_name)
        print(f"Removed library: {removed}")
        return

def command_library_create(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    library_root = getattr(args, "path", None)
    if library_root is None:
        created_library = manager.get_or_create_plugin_library(args.lib_name)
    else:
        library_root = Path(library_root).expanduser().resolve()
        if not library_root.is_dir():
            raise ValueError(
                f"Linked library path is not an existing directory: {library_root}"
            )
        created_library = manager.get_or_create_plugin_library(
            args.lib_name, str(library_root)
        )
    print(f"Created library: {args.lib_name} at {created_library.path}")




def _registry_setting_name(setting_name: str) -> str:
    normalized_name = setting_name.strip()
    if not normalized_name.isupper():
        raise ValueError(f"Setting name must be uppercase: {normalized_name}")
    return normalized_name


def command_registry_config_list(args) -> None:
    config = rp.get_config()
    print(json.dumps(config, indent=2, sort_keys=False))


def command_registry_config_get(args) -> None:
    setting_name = _registry_setting_name(args.setting_name)
    persisted_config = rp.get_config()
    if setting_name in persisted_config:
        value = persisted_config[setting_name]
    else:
        value = rp.get_setting(setting_name)
    print(json.dumps({setting_name: value}, indent=2, sort_keys=False))


def command_registry_config_set(args) -> int:
    setting_name = _registry_setting_name(args.setting_name)
    if rp.set_to_config(setting_name, args.setting_value):
        return 0
    return 1


def command_registry_setting(args) -> int | None:
    """Handle the former KEY=VALUE interface for direct Python callers."""
    expression = getattr(args, "expression", None)

    if expression is None:
        return command_registry_config_list(args)

    setting_name, separator, setting_value = expression.partition("=")
    if not separator:
        raise ValueError(
            "Configuration expressions require KEY=VALUE; "
            "use 'rpp registry config set KEY VALUE' from the CLI"
        )

    args.setting_name = setting_name
    args.setting_value = setting_value
    return command_registry_config_set(args)


def command_library_refresh(args, library_manager=None) -> None:
    library = args.library
    manager = _get_library_manager(library_manager)
    library_path = manager.get_library_path(library)
    if library_path is None:
        print(f"Library '{library}' does not exist.")
        return 1

    manager.refresh_plugin_library(library)
    print(f"Refreshing library '{library}'...")
    print(f"Library: {library}")
    print("Library refresh completed.")
    return 0


def command_library_info(args, library_manager=None) -> None:
    library = args.library
    manager = _get_library_manager(library_manager)
    info = manager.get_library_info(library, only_registered=True)
    plugins = {}
    plugin_types = {}

    try:
        library_path = manager.get_library_path(library)
        if library_path:
            manifest_path = Path(manager._manifest_path(library_path))
            if manifest_path.exists():
                manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugins = manifest_payload.get("Plugins", {})
                plugin_types = manifest_payload.get("PluginTypes", {})
    except Exception:
        pass

    info = dict(info)
    info["Plugins"] = plugins
    info["PluginTypes"] = plugin_types
    print(json.dumps(info, indent=2, sort_keys=False))


def command_library_list(args, library_manager=None) -> None:
    del args
    manager = _get_library_manager(library_manager)
    libraries = manager.list_plugin_libraries()
    print(json.dumps(libraries, indent=2, sort_keys=False))


def command_library_register_plugin(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    source_path = Path(args.file_name).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Plugin source file does not exist: {source_path}")
    manager.register_plugin_from_source(str(source_path), args.library)
    print(f"Registered plugin file '{source_path}' into library '{args.library}'")

def command_library_refresh_plugin(args, library_manager=None) -> int:
    manager = _get_library_manager(library_manager)
    library_path_text = manager.get_library_path(args.library)
    if library_path_text is None:
        print(f"Library '{args.library}' does not exist.")
        return 1

    plugin = manager.get_plugin_info_from_lib(args.plugin_name, args.library)
    plugin_name = plugin.get("PluginName")
    source_file = plugin.get("SourceFile")
    if not plugin_name or not source_file:
        raise ValueError(
            f"Plugin '{args.plugin_name}' in library '{args.library}' has incomplete source metadata."
        )

    library_path = Path(library_path_text).resolve()
    source_path = (library_path / source_file).resolve()
    if not source_path.is_relative_to(library_path):
        raise ValueError(
            f"Plugin '{plugin_name}' source file is outside library '{args.library}': "
            f"{source_path}"
        )
    if not source_path.is_file():
        raise ValueError(f"Plugin source file does not exist: {source_path}")

    manager.unregister_plugin(plugin_name, args.library, remove_from_json=False)
    manager.register_plugin_from_source(str(source_path), args.library)
    print(f"Refreshed plugin '{plugin_name}' in library '{args.library}'")
    return 0


def command_library_unregister_plugin(args, library_manager=None) -> int:
    manager = _get_library_manager(library_manager)
    plugin_name = args.plugin_name
    library = args.library
    manager.unregister_plugin(plugin_name, library)
    print(f"Unregistered plugin '{plugin_name}' from library '{library}'")
    return 0


def command_library_list_plugins(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    plugins = manager.get_library_plugins(args.library)
    print(json.dumps(plugins, indent=2, sort_keys=False))


def command_library_info_plugin(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    plugin = manager.get_plugin_info_from_lib(args.plugin_name, args.library)
    print(json.dumps(plugin, indent=2, sort_keys=False))


def command_library_register_plugin_type(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    source_path = Path(args.file_name).expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"Plugin type source file does not exist: {source_path}")
    if not manager.is_supported_plugin_type_file(source_path):
        raise ValueError(f"Unsupported plugin type source file: {source_path}")

    registered_types = manager.register_plugin_type_from_source(
        source_path,
        args.library,
        override=bool(getattr(args, "override", False)),
    )
    for plugin_type in registered_types:
        plugin_type_name = plugin_type.get("PluginTypeName", source_path.stem)
        print(f"Registered plugin type '{plugin_type_name}' in library '{args.library}'")


def command_library_unregister_plugin_type(args, library_manager=None) -> int:
    manager = _get_library_manager(library_manager)
    plugin_type_name = args.plugin_type_name
    if "::" not in plugin_type_name:
        plugin_type_name = f"{args.library}::{plugin_type_name}"
    if not manager.unregister_plugin_type(plugin_type_name):
        print(f"Plugin type '{plugin_type_name}' was not found.")
        return 1
    print(f"Unregistered plugin type '{plugin_type_name}'")
    return 0


def command_library_list_plugin_types(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    library = getattr(args, "library", None)
    if library is None:
        plugin_types = registry_api.list_registered_plugin_types().get(
            "PluginTypes", {}
        )
    else:
        plugin_types = manager.get_library_plugin_types(library)
    print(json.dumps(plugin_types, indent=2, sort_keys=False))


def command_library_info_plugin_type(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    plugin_type = manager.get_plugin_type_info_from_lib(
        args.plugin_type_name, args.library
    )
    print(json.dumps(plugin_type, indent=2, sort_keys=False))


def command_library(args, library_manager=None) -> None:
    tokens = args.library_args or []
    if not tokens:
        print(
            "Error: No library command provided. Expected one of: "
            "register, create, unregister, refresh, info, list, or <lib_name>\n\n"
            "Usage: rpp library register <lib_path> | rpp library create <lib_name> [--path <directory>] | "
            "rpp library unregister <lib_name> | "
            "rpp library refresh <lib_name> | rpp library info <lib_name> | rpp library list | "
            "rpp library <lib_name> <register|refresh|unregister|list|info> [--type]"
        )
        return 1

    if tokens[0] == "register":
        link_register = False
        register_tokens = tokens[1:]
        if "--link" in register_tokens:
            link_register = True
            register_tokens = [token for token in register_tokens if token != "--link"]

        if len(register_tokens) != 1:
            print(
                "Error: Invalid number of arguments for 'register' command. Expected one argument."
                + " Usage: rpp library register <lib_path> [--link]")
            return 1
        return command_library_register(
            argparse.Namespace(lib_path=register_tokens[0], link=link_register),
            library_manager=library_manager,
        )

    if tokens[0] == "create":
        create_tokens = tokens[1:]
        if len(create_tokens) == 1:
            library_path = None
        elif len(create_tokens) == 3 and create_tokens[1] == "--path":
            library_path = create_tokens[2]
        else:
            print(
                "Usage: rpp library create <lib_name> [--path <directory>]"
            )
            return 1
        return command_library_create(
            argparse.Namespace(lib_name=create_tokens[0], path=library_path),
            library_manager=library_manager,
        )


    if tokens[0] == "unregister":
        if len(tokens) != 2:
            print("Error: Invalid number of arguments for 'unregister' command. Expected one argument."
                + " Usage: rpp library unregister <lib_name>")
            return 1
        return command_library_unregister(argparse.Namespace(lib_name=tokens[1]), library_manager=library_manager)

    if tokens[0] == "refresh":
        if len(tokens) != 2:
            print("Error: Invalid number of arguments for 'refresh' command. Expected one argument."
                + " Usage: rpp library refresh <lib_name>")
            return 1
        return command_library_refresh(argparse.Namespace(library=tokens[1]), library_manager=library_manager)

    if tokens[0] == "info":
        if len(tokens) != 2:
            print("Error: Invalid number of arguments for 'info' command. Expected one argument."
                + " Usage: rpp library info <lib_name>")
            return 1

        return command_library_info(argparse.Namespace(library=tokens[1]), library_manager=library_manager)

    if tokens[0] == "list":
        if len(tokens) != 1:
            print("Error: Invalid number of arguments for 'list' command. Expected no arguments."
                + " Usage: rpp library list")
            return 1
        return command_library_list(argparse.Namespace(), library_manager=library_manager)

    if len(tokens) < 2:
        print(
            "Error: No action provided for library. Expected one of: register, "
            "refresh, unregister, list, or info."
        )
        return 1

    library = tokens[0]
    action = tokens[1]
    action_tokens = tokens[2:]
    is_plugin_type = "--type" in action_tokens
    override = "--override" in action_tokens
    action_tokens = [
        token for token in action_tokens
        if token not in {"--type", "--override"}
    ]

    if action == "register":
        if len(action_tokens) != 1 or (override and not is_plugin_type):
            print(
                "Usage: rpp library <library> register <source> "
                "[--type] [--override]"
            )
            return 1
        if is_plugin_type:
            return command_library_register_plugin_type(
                argparse.Namespace(
                    library=library,
                    file_name=action_tokens[0],
                    override=override,
                ),
                library_manager=library_manager,
            )
        return command_library_register_plugin(
            argparse.Namespace(library=library, file_name=action_tokens[0]),
            library_manager=library_manager,
        )

    if action == "refresh":
        if len(action_tokens) != 1 or is_plugin_type or override:
            print("Usage: rpp library <library> refresh <plugin-name>")
            return 1
        return command_library_refresh_plugin(
            argparse.Namespace(library=library, plugin_name=action_tokens[0]),
            library_manager=library_manager,
        )

    if action == "unregister":
        if len(action_tokens) != 1 or override:
            print(
                "Usage: rpp library <library> unregister <name> [--type]"
            )
            return 1
        if is_plugin_type:
            return command_library_unregister_plugin_type(
                argparse.Namespace(
                    library=library,
                    plugin_type_name=action_tokens[0],
                ),
                library_manager=library_manager,
            )
        return command_library_unregister_plugin(
            argparse.Namespace(library=library, plugin_name=action_tokens[0]),
            library_manager=library_manager,
        )

    if action == "list":
        if action_tokens or override:
            print("Usage: rpp library <library> list [--type]")
            return 1
        if is_plugin_type:
            return command_library_list_plugin_types(
                argparse.Namespace(library=library),
                library_manager=library_manager,
            )
        return command_library_list_plugins(
            argparse.Namespace(library=library),
            library_manager=library_manager,
        )

    if action == "info":
        if len(action_tokens) != 1 or override:
            print("Usage: rpp library <library> info <name> [--type]")
            return 1
        if is_plugin_type:
            return command_library_info_plugin_type(
                argparse.Namespace(
                    library=library,
                    plugin_type_name=action_tokens[0],
                ),
                library_manager=library_manager,
            )
        return command_library_info_plugin(
            argparse.Namespace(library=library, plugin_name=action_tokens[0]),
            library_manager=library_manager,
        )

    print(
        "Unknown library action. Expected one of: register, refresh, unregister, "
        "list, or info. Use 'rpp library <library> <action> --type' for plugin types."
    )
    return 1

def command_test(args) -> None:
    tokens = args.test_args or []
    if not tokens:
        raise ValueError(
            "Usage: rpp test <test_name> [<test_args> or rpp test <command> <command_args>]"
        )


    if tokens[0] == "setup_tmp_rpp_with_test_plugins":
        test_args = tokens[1:] if len(tokens) > 1 else []
        override = "--override" in test_args
        test_args = [arg for arg in test_args if arg != "--override"]
        if len(test_args) >= 1:
            out_dir = Path(test_args[0]).expanduser().resolve()
            handle = setup_tmp_rpp_with_test_plugins(out_dir, override=override)
        else:
            handle = setup_tmp_rpp_with_test_plugins(override=override)
        json_payload = {
            "home": str(handle.home),
            "test_lib": handle.test_lib,
            "out_dir": str(handle.out_dir),
            "plugins": handle.plugins
        }
        print(json.dumps(json_payload, indent=2, sort_keys=False))
        return

    raise ValueError(
        "Unknown test action. Expected one of: setup_tmp_rpp_with_test_plugins. "
        "Supported forms: rpp test setup_tmp_rpp_with_test_plugins."
    )


def command_init_home(args) -> None:
    use_ros2_compilation = os.environ.get("RPP_USE_ROS2_COMPILATION", None)
    if use_ros2_compilation is not None:
        print(f"Setting USE_ROS2_COMPILATION to '{use_ros2_compilation}'"
              f" from environment variable RPP_USE_ROS2_COMPILATION")
        rp.set_to_config("USE_ROS2_COMPILATION", str(use_ros2_compilation).lower())

    registry_api.ensure_rpp_layout(
        override_initialization=args.override,
        init_anot_only=args.init_anot_only,
    )
    paths = registry_api.get_rpp_paths()
    print(f"Initialized rpp home at: {paths['home']}")
    print(f"Descriptions: {paths['descriptions']}")
    print(f"Interfaces: {paths['interfaces']}")
    print(f"Registry: {paths['registry']}")


def command_pm(args) -> int:
    plugin_manager_module = importlib.import_module("rpp_plugin_registrator.gui")
    result = plugin_manager_module.main()
    return int(result or 0)


def command_ws(args) -> int:
    workspace_root = getattr(args, "root", None)
    if workspace_root:
        return int(workspace_main(["--root", workspace_root]) or 0)
    return int(workspace_main([]) or 0)


def _open_existing_workspace(
        workspace_path: str | Path, library_manager=None
) -> Workspace:
    manager = _get_library_manager(library_manager)
    registered_path = manager.get_library_path(str(workspace_path))
    if registered_path is not None:
        workspace_root = Path(registered_path).expanduser().resolve()
        if Workspace.workspace_exists(workspace_root):
            return open_workspace(workspace_root)

    requested_path = Path(workspace_path).expanduser().resolve()
    if Workspace.workspace_exists(requested_path):
        return open_workspace(requested_path)

    raise ValueError(
        f"Workspace '{workspace_path}' was not found. Expected a workspace path "
        "or a registered library containing .rppws."
    )


def _workspace_path_from_args(args) -> str:
    workspace_path = getattr(args, "workspace", ".")
    if workspace_path == "." and getattr(args, "root", None):
        return args.root
    return workspace_path


def command_ws_list(args, library_manager=None) -> int:
    manager = _get_library_manager(library_manager)
    catalog = ScriptCatalog(manager)
    workspaces = []
    for library in manager.list_plugin_libraries():
        library_path = Path(library["Path"]).expanduser().resolve()
        if not Workspace.workspace_exists(library_path):
            continue
        scripts = catalog.list_library_scripts(library["Name"])
        workspaces.append({
            "Name": library["Name"],
            "Path": str(library_path),
            "Type": library["Type"],
            "Version": library["Version"],
            "Scripts": [script.script_name for script in scripts],
        })

    workspaces.sort(key=lambda workspace: workspace["Name"])
    if args.json:
        print(json.dumps(workspaces, indent=2, sort_keys=False))
        return 0

    if not workspaces:
        print("No registered workspaces found.")
        return 0

    for workspace in workspaces:
        print(f"- {workspace['Name']}: {workspace['Path']}")
        for script_name in workspace["Scripts"]:
            print(f"  - {script_name}")
    return 0


def command_ws_info(args) -> int:
    workspace = _open_existing_workspace(_workspace_path_from_args(args))
    scripts = []
    for script in workspace.list_scripts():
        script_info = dict(script.load_description())
        script_info["ResolvedPath"] = str(script.path)
        scripts.append(script_info)

    components = []
    for component in workspace.get_part_records().values():
        component_info = dict(component.to_dict())
        component_info["Folder"] = str(component.folder)
        components.append(component_info)

    if not args.json:
        print("Scripts:")
        for script in scripts:
            print(f"- {script.get('ScriptName', Path(script['ResolvedPath']).stem)}")
        print("Components:")
        for component in components:
            print(f"- {component['Name']}")
        return 0

    summary = {
        "Name": workspace.name,
        "Root": str(workspace.root),
        "ScriptCount": len(scripts),
        "Scripts": scripts,
        "ComponentCount": len(components),
        "Components": components,
    }
    print(json.dumps(summary, indent=2, sort_keys=False))
    return 0


def _find_workspace_script(workspace: Workspace, script_reference: str):
    matches = []
    for script in workspace.list_scripts():
        description = script.load_description()
        references = {
            str(script.path),
            script.path.name,
            script.path.stem,
            description.get("ScriptName"),
        }
        try:
            references.add(script.path.relative_to(workspace.root).as_posix())
        except ValueError:
            pass
        if script_reference in references:
            matches.append(script)

    if not matches:
        raise ValueError(f"Workspace script '{script_reference}' was not found.")
    if len(matches) > 1:
        options = ", ".join(str(script.path) for script in matches)
        raise ValueError(
            f"Workspace script reference '{script_reference}' is ambiguous: {options}"
        )
    return matches[0]


def _workspace_script_from_args(args) -> tuple[Workspace, object]:
    workspace = _open_existing_workspace(args.workspace)
    return workspace, _find_workspace_script(workspace, args.script_name)


def command_ws_component_create(args, library_manager=None) -> int:
    workspace = _open_existing_workspace(args.workspace, library_manager)
    component = workspace.create_component(args.component_name, args.plugin_name)
    print(f"Created component: {component.name} ({component.id})")
    return 0


def _find_workspace_component(workspace: Workspace, component_reference: str):
    """Resolve a workspace component by its persistent ID or displayed name."""
    return workspace.get_component(component_reference)


def _component_summary(component) -> dict[str, Any]:
    """Build JSON-safe component data for CLI inspection."""
    payload = dict(component.to_dict())
    payload["Folder"] = str(component.folder)
    return payload


def _component_parameter_source_folder(workspace: Workspace, component) -> Path:
    """Return the parameter source folder used by the workspace editor."""
    source_folder = workspace.resolve_linked_folder(component.id)
    if source_folder is None:
        raise ValueError(
            f"Could not resolve parameter source for component '{component.id}'."
        )
    return Path(source_folder)


def _parse_component_parameter_value(value: str) -> Any:
    """Use JSON for structured values while keeping bare console values strings."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _validate_component_parameter_name(parameter_name: str) -> str:
    normalized_name = parameter_name.strip()
    if not normalized_name.isidentifier():
        raise ValueError(
            "Component parameter names must be valid Python identifiers: "
            f"{parameter_name}"
        )
    return normalized_name


def _find_parent_subcomponent(
        workspace: Workspace, parent, slot_name: str, component_reference: str):
    if not hasattr(parent, "subcomponents"):
        raise ValueError(
            f"Component '{parent.id}' cannot contain subcomponents."
        )

    slot_components = parent.subcomponents.get(slot_name)
    if slot_components is None:
        raise ValueError(
            f"Slot '{slot_name}' has no assigned subcomponents on '{parent.name}'."
        )
    if not isinstance(slot_components, list):
        slot_components = [slot_components]

    matches = []
    for subcomponent_info in slot_components:
        record = workspace.get_part_record_by_id(subcomponent_info.id)
        if record is None:
            continue
        if component_reference in {record.id, record.name}:
            matches.append(record)

    if not matches:
        raise ValueError(
            f"Subcomponent '{component_reference}' was not found in slot "
            f"'{slot_name}' on '{parent.name}'."
        )
    if len(matches) > 1:
        options = ", ".join(record.id for record in matches)
        raise ValueError(
            f"Subcomponent reference '{component_reference}' is ambiguous in "
            f"slot '{slot_name}': {options}"
        )
    return matches[0]


def command_ws_component_list(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    components = [
        _component_summary(component)
        for component in workspace.get_part_records().values()
    ]
    components.sort(key=lambda component: (component["Name"], component["Id"]))

    if args.json:
        print(json.dumps(components, indent=2, sort_keys=False))
        return 0

    if not components:
        print("No components found.")
        return 0

    for component in components:
        print(f"- {component['Name']} ({component['Id']})")
    return 0


def command_ws_component_info(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    component = _find_workspace_component(workspace, args.component_reference)
    print(json.dumps(_component_summary(component), indent=2, sort_keys=False))
    return 0


def command_ws_component_rename(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    component = _find_workspace_component(workspace, args.component_reference)
    if not hasattr(component, "plugin_type"):
        raise ValueError("A linked subcomponent cannot be renamed.")
    new_name = args.new_name.strip()
    if not new_name:
        raise ValueError("Component name cannot be empty.")

    component.name = new_name
    workspace.write_part_descriptor(component.folder, component)
    print(f"Renamed component: {component.name} ({component.id})")
    return 0


def command_ws_component_duplicate(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    component = _find_workspace_component(workspace, args.component_reference)
    duplicate = workspace.duplicate_component(component.id, args.new_name)
    print(f"Duplicated component: {duplicate.name} ({duplicate.id})")
    return 0


def command_ws_component_remove(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    component = _find_workspace_component(workspace, args.component_reference)
    workspace.remove_component(component.id)
    print(f"Removed component: {component.name} ({component.id})")
    return 0


def command_ws_component_assign(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    script = _find_workspace_script(workspace, args.script_name)
    component = _find_workspace_component(workspace, args.component_reference)
    if not hasattr(component, "plugin_type"):
        raise ValueError(
            "A linked subcomponent cannot be assigned to a script. "
            "Use its source component instead."
        )
    workspace.assign_component_to_script(
        script,
        args.slot_name,
        component.id,
        configuration_name=args.configuration_name,
    )
    print(
        f"Assigned component '{component.name}' to slot '{args.slot_name}' "
        f"of {script.path}"
    )
    return 0


def command_ws_component_unassign(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    script = _find_workspace_script(workspace, args.script_name)
    component = _find_workspace_component(workspace, args.component_reference)
    workspace.remove_component_from_script(
        script,
        component.id,
        component_key=args.slot_name,
        configuration_name=args.configuration_name,
    )
    print(f"Removed component '{component.name}' from {script.path}")
    return 0


def command_ws_component_subcomponent_create(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    parent = _find_workspace_component(workspace, args.parent_component)
    if not hasattr(parent, "subcomponents"):
        raise ValueError(
            f"Component '{parent.id}' cannot contain subcomponents."
        )
    subcomponent = workspace.create_subcomponent(
        parent.folder,
        args.slot_name,
        args.component_name,
        args.plugin_name,
    )
    print(f"Created subcomponent: {subcomponent.name} ({subcomponent.id})")
    return 0


def command_ws_component_subcomponent_assign(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    parent = _find_workspace_component(workspace, args.parent_component)
    component = _find_workspace_component(workspace, args.component_reference)
    if not hasattr(parent, "subcomponents"):
        raise ValueError(
            f"Component '{parent.id}' cannot contain subcomponents."
        )
    _, assigned_component = workspace.assign_subcomponent_to_parent(
        parent.id,
        args.slot_name,
        component.id,
    )
    print(
        f"Assigned subcomponent: {assigned_component.name} "
        f"({assigned_component.id})"
    )
    return 0


def command_ws_component_subcomponent_remove(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    parent = _find_workspace_component(workspace, args.parent_component)
    subcomponent = _find_parent_subcomponent(
        workspace, parent, args.slot_name, args.component_reference
    )
    workspace.remove_subcomponent(
        parent.id,
        args.slot_name,
        subcomponent.id,
        handle_parent_update=True,
    )
    print(f"Removed subcomponent: {subcomponent.name} ({subcomponent.id})")
    return 0


def command_ws_component_parameter_get(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    component = _find_workspace_component(workspace, args.component_reference)
    source_folder = _component_parameter_source_folder(workspace, component)
    parameters = workspace.component_parameter_store.load(source_folder)

    if args.parameter_name is None:
        print(json.dumps(parameters, indent=2, sort_keys=False))
        return 0

    parameter_name = _validate_component_parameter_name(args.parameter_name)
    if parameter_name not in parameters:
        raise ValueError(
            f"Parameter '{parameter_name}' was not found on component "
            f"'{component.name}'."
        )
    print(json.dumps(parameters[parameter_name], indent=2, sort_keys=False))
    return 0


def command_ws_component_parameter_set(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    component = _find_workspace_component(workspace, args.component_reference)
    parameter_name = _validate_component_parameter_name(args.parameter_name)
    source_folder = _component_parameter_source_folder(workspace, component)
    parameters = workspace.component_parameter_store.load(source_folder)
    parameters[parameter_name] = _parse_component_parameter_value(args.value)
    parameters_path = workspace.component_parameter_store.save(
        source_folder, parameters
    )
    print(f"Saved parameter '{parameter_name}' to {parameters_path}")
    return 0


def command_ws_component_context(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    component = _find_workspace_component(workspace, args.component_reference)
    source_folder = _component_parameter_source_folder(workspace, component)
    parameters_path = workspace.component_parameter_store.ensure_parameters_file(
        source_folder
    )
    description_path = workspace.part_description_path(component.folder)
    print(json.dumps({
        "ComponentFolder": str(component.folder),
        "ParameterSourceFolder": str(source_folder),
        "ParametersPath": str(parameters_path),
        "DescriptionPath": str(description_path) if description_path else None,
    }, indent=2, sort_keys=False))
    return 0


def command_ws_script_config_list(args) -> int:
    _, script = _workspace_script_from_args(args)
    description = script.load_description()
    configurations = description["Configurations"]
    active_configuration = description["ActiveConfiguration"]

    if args.json:
        print(json.dumps({
            "ActiveConfiguration": active_configuration,
            "Configurations": configurations,
        }, indent=2, sort_keys=False))
        return 0

    for configuration_name in configurations:
        prefix = "*" if configuration_name == active_configuration else " "
        print(f"{prefix} {configuration_name}")
    return 0


def command_ws_script_config_create(args) -> int:
    workspace, script = _workspace_script_from_args(args)
    workspace.create_script_configuration(script, args.configuration_name)
    print(f"Created configuration '{args.configuration_name}' for {script.path}")
    return 0


def command_ws_script_config_copy(args) -> int:
    workspace, script = _workspace_script_from_args(args)
    workspace.duplicate_script_configuration(
        script, args.source_configuration_name, args.configuration_name
    )
    print(
        f"Copied configuration '{args.source_configuration_name}' to "
        f"'{args.configuration_name}' for {script.path}"
    )
    return 0


def command_ws_script_config_rename(args) -> int:
    workspace, script = _workspace_script_from_args(args)
    workspace.rename_script_configuration(
        script, args.configuration_name, args.new_configuration_name
    )
    print(
        f"Renamed configuration '{args.configuration_name}' to "
        f"'{args.new_configuration_name}' for {script.path}"
    )
    return 0


def command_ws_script_config_remove(args) -> int:
    workspace, script = _workspace_script_from_args(args)
    workspace.delete_script_configuration(script, args.configuration_name)
    print(f"Removed configuration '{args.configuration_name}' from {script.path}")
    return 0


def command_ws_script_config_activate(args) -> int:
    workspace, script = _workspace_script_from_args(args)
    workspace.set_active_script_configuration(script, args.configuration_name)
    print(f"Activated configuration '{args.configuration_name}' for {script.path}")
    return 0


def command_ws_script_remove(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    script = _find_workspace_script(workspace, args.script_name)
    workspace.remove_script(script.path)
    print(f"Removed script: {script.path}")
    return 0


def command_ws_script_load(args, library_manager=None) -> int:
    workspace = _open_existing_workspace(_workspace_path_from_args(args))
    catalog = ScriptCatalog(_get_library_manager(library_manager))
    scripts = catalog.list_registered_scripts(
        exclude_library=workspace.name, workspace=workspace
    )
    matches = [script for script in scripts if script.script_name == args.script_name]
    if not matches:
        matches = [script for script in scripts if script.library == args.script_name]
    if not matches:
        raise ValueError(f"Registered script '{args.script_name}' was not found.")
    if len(matches) > 1:
        options = ", ".join(script.script_name for script in matches)
        raise ValueError(
            f"Library '{args.script_name}' has multiple scripts. Choose one: {options}"
        )

    selected_script = matches[0]
    script = workspace.link_registered_script(
        selected_script.path,
        selected_script.script_name,
        selected_script.library,
        selected_script.language,
    )
    print(f"Loaded script: {script.path}")
    return 0


def command_ws_script_load_file(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    source_path = Path(args.source).expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"Script source file does not exist: {source_path}")

    script = workspace.load_script(source_path)
    print(f"Loaded script: {script.path}")
    return 0


def command_ws_script_create(args) -> int:
    workspace = _open_existing_workspace(args.workspace)
    script_name = Path(args.name)
    if script_name.is_absolute() or script_name.parent != Path("."):
        raise ValueError("Script name must not include a directory path.")

    relative_directory = Path(args.path)
    if relative_directory.is_absolute():
        raise ValueError("Script path must be relative to the workspace root.")
    script_directory = (workspace.root / relative_directory).resolve()
    if not script_directory.is_relative_to(workspace.root):
        raise ValueError("Script path must remain within the workspace root.")
    if not script_directory.is_dir():
        raise ValueError(f"Script directory does not exist: {script_directory}")

    script_path = script_directory / script_name
    if not script_path.suffix:
        script_path = script_path.with_suffix(language_spec(args.language).extension)
    if script_path.exists():
        raise FileExistsError(f"Script already exists: {script_path}")

    script = workspace.create_script(script_path, language=args.language)
    print(f"Created script: {script.path}")
    return 0


def command_ws_create(args, library_manager=None) -> int:
    manager = _get_library_manager(library_manager)
    library_path = manager.get_library_path(args.library)
    if library_path is None:
        raise ValueError(
            f"Library '{args.library}' was not found. Register or create the "
            "library before creating its workspace."
        )

    workspace_root = Path(library_path).expanduser().resolve()
    if not manager.is_valid_plugin_library(str(workspace_root)):
        raise ValueError(
            f"Workspace root must be a valid plugin library: {workspace_root}"
        )

    create_workspace(workspace_root, name=workspace_root.name)
    print(f"Created workspace in library '{args.library}': {workspace_root}")
    return 0


def command_list_registry(args) -> None:
    registry = registry_api.list_registered_plugin_types()

    if args.plugins:
        plugins = registry.get("Plugins", {})
    else:
        plugins = registry.get("PluginTypes", {})

    if args.json:
        print(json.dumps(registry, indent=2, sort_keys=False))
        return

    print(f"Total plugins: {len(plugins)}")
    for plugin_name in sorted(plugins):
        data = plugins[plugin_name]
        source_language = data.get("SourceLanguage", "?")
        name = data.get("Name", "?")
        print(f"- {plugin_name} [{source_language}] {name}")


def command_registry_info(args) -> None:
    path = rp.get_app_registry_plugin_type_json_path(args.tag)

    if not path.exists():
        print(f"No registry info found for tag '{args.tag}' at path: {path}")
        return
    description_payload = registry_api.load_json(
        rp.get_app_registry_plugin_type_json_path(args.tag))
    print(json.dumps(description_payload, indent=2, sort_keys=False))


def command_compile(args) -> None:
    rp.load_and_set_config(LibraryManager())
    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Plugin source file does not exist: {source_path}")

    plugin_type_extensions = get_supported_plugin_type_extensions()
    plugin_extensions = get_supported_plugin_extensions()
    source_ext = source_path.suffix.lower()

    if args.type == "plugin-type":
        if source_ext not in plugin_type_extensions:
            raise ValueError(f"Invalid plugin type source file extension:"
                + f" {source_ext}. Supported extensions: {plugin_type_extensions}")
        print(f"Compiled plugin type source: {source_path}")
        return
    if source_ext in [".cpp", ".hpp"]:
        from rpp_plugin_registrator.plugin_registrator.cpp import compile_cpp_plugin

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_out_dir = Path(tmp_dir)

            if args.plugin_type_name is None:
                succ, plugin_type, class_name = \
                    _cpp_try_extract_plugin_type_name_and_class_name_from_source(source_path)
            else:
                plugin_type = args.plugin_type_name
                class_name = None
                succ = True
            if succ is False or plugin_type is None:
                raise ValueError(f"Failed to extract plugin type name from source: {source_path}."
                    + " Compile with --plugin-type-name to specify the plugin type name.")

            plugin_type_library = plugin_type.split("::")[0]
            err_msg, compile_cmd, out_file_path = compile_cpp_plugin(source_path, args.library,
                plugin_type, plugin_type_library, tmp_out_dir,
                class_name=class_name, suppress_warnings=False,
                print_to_console=True, verbose=args.verbose)
        if not err_msg:
            print(f"Successfully compiled plugin source: {source_path}")
        return

    raise ValueError("Unsupported plugin source file extension:"
        +f" {source_ext}. Supported extensions: {plugin_type_extensions + plugin_extensions}")

def _cpp_try_extract_plugin_type_name_and_class_name_from_source(source_path: Path) \
         -> Tuple[bool, Optional[str], Optional[str]]:
    plugin_type_imports_re = r'^[ \t]*#[ \t]*include[ \t]*["<]([^">]*rpp_plugin_types[^">]*)[">]'
    base_class_pattern = re.compile(r"""
        class\s+
        (\S+)
        \s*:\s*
        (?:public|private|protected)?
        \s+(\S+)
    """, re.VERBOSE | re.DOTALL)
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()


    imports = re.findall(plugin_type_imports_re, content, re.MULTILINE)
    base_classes = base_class_pattern.findall(content)

    for b in base_classes:
        base_class = b[1]
        plugin_type = base_class
        plugin_name = plugin_type.split("::")[-1]
        class_name = b[0]
        for imp in imports:
            if plugin_name in imp:
                print("[RPP COMPILE]:"
                      + f" Found plugin type '{plugin_type}' in source: {source_path}\n")
                return True, plugin_type, class_name
    return False, None, None


def _render_bash_completion() -> str:
    return r'''# Show full completion list only when second Tab is pressed within 1 second
# on the same command line/position.
__rpp_last_complete_ms=0
__rpp_last_complete_key=""
__rpp_allow_list=0

_rpp_now_ms() {
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        # EPOCHREALTIME format: seconds.microseconds
        local sec="${EPOCHREALTIME%%.*}"
        local usec="${EPOCHREALTIME#*.}"
        usec="${usec%%[^0-9]*}"
        printf '%d\n' "$((10#$sec * 1000 + 10#${usec:0:3}))"
    else
        printf '%d\n' "$(( $(date +%s) * 1000 ))"
    fi
}

_rpp_tab_list_gate() {
    local now_ms key delta
    now_ms="$(_rpp_now_ms)"
    key="${COMP_LINE}:${COMP_POINT}"
    delta=$(( now_ms - __rpp_last_complete_ms ))

    if [[ "$key" == "$__rpp_last_complete_key" ]] && (( delta >= 0 && delta <= 1000 )); then
        __rpp_allow_list=1
    else
        __rpp_allow_list=0
    fi

    __rpp_last_complete_ms="$now_ms"
    __rpp_last_complete_key="$key"
}

_rpp_gate_compreply() {
    local cur_word="$1"
    local n i prefix

    n=${#COMPREPLY[@]}
    if (( __rpp_allow_list == 1 || n <= 1 )); then
        return 0
    fi

    prefix="${COMPREPLY[0]}"
    for ((i = 1; i < n; i++)); do
        while [[ -n "$prefix" && "${COMPREPLY[i]}" != "$prefix"* ]]; do
            prefix="${prefix%?}"
        done
    done

    if [[ -n "$prefix" && "$prefix" != "$cur_word" ]]; then
        COMPREPLY=("$prefix")
    else
        COMPREPLY=()
    fi
}

_rpp_completion() {
    local cur prev cword
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cword=${COMP_CWORD}

    _rpp_tab_list_gate

    # Top-level commands.
    if [[ ${cword} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "init-home pm registry library" -- "$cur") )
        _rpp_gate_compreply "$cur"
        return 0
    fi

    # Registry command completion.
    if [[ "${COMP_WORDS[1]}" == "registry" ]]; then
        if [[ ${cword} -eq 2 ]]; then
            COMPREPLY=( $(compgen -W "describe list info generate-interface scaffold" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi
        case "${COMP_WORDS[2]}" in
            describe)
                COMPREPLY=( $(compgen -f -- "$cur") )
                _rpp_gate_compreply "$cur"
                return 0
                ;;
            info)
                COMPREPLY=( $(compgen -f -- "$cur") )
                _rpp_gate_compreply "$cur"
                return 0
                ;;
            generate-interface)
                COMPREPLY=( $(compgen -f -- "$cur") )
                _rpp_gate_compreply "$cur"
                return 0
                ;;
            scaffold)
                if [[ "$prev" == "--language" ]]; then
                    COMPREPLY=( $(compgen -W "cpp python" -- "$cur") )
                    _rpp_gate_compreply "$cur"
                    return 0
                fi
                COMPREPLY=( $(compgen -f -- "$cur") )
                _rpp_gate_compreply "$cur"
                return 0
                ;;
        esac
    fi

    # Library command completion supporting:
    # rpp library register <lib_path>
    # rpp library unregister <lib_name>
    # rpp library refresh <lib_name>
    # rpp library info <lib_name>
    # rpp library list
    # rpp library <lib_name> register <file_name>
    # rpp library <lib_name> refresh
    # rpp library <lib_name> info
    if [[ "${COMP_WORDS[1]}" == "library" ]]; then
        local libs
        if [[ -d "$HOME/.rpp/libraries" ]]; then
            libs=$(ls -1 "$HOME/.rpp/libraries" 2>/dev/null | sed 's/\.json$//' | sort -u)
        else
            libs=""
        fi

        if [[ ${cword} -eq 2 ]]; then
            COMPREPLY=( $(compgen -W "register unregister refresh info list ${libs}" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library list
        if [[ "${COMP_WORDS[2]}" == "list" ]]; then
            COMPREPLY=()
            return 0
        fi

        # rpp library register <lib_path>
        if [[ "${COMP_WORDS[2]}" == "register" ]]; then
            if [[ "$prev" == "register" || "$prev" == "--link" ]]; then
                COMPREPLY=( $(compgen -d -- "$cur") )
            else
                COMPREPLY=( $(compgen -W "--link" -- "$cur") )
            fi
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library unregister <lib_name>
        if [[ "${COMP_WORDS[2]}" == "unregister" ]]; then
            COMPREPLY=( $(compgen -W "${libs}" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library refresh <lib_name>
        if [[ "${COMP_WORDS[2]}" == "refresh" ]]; then
            COMPREPLY=( $(compgen -W "${libs}" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library info <lib_name>
        if [[ "${COMP_WORDS[2]}" == "info" ]]; then
            COMPREPLY=( $(compgen -W "${libs}" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library <lib_name> register <file_name>
        # rpp library <lib_name> refresh
        if [[ ${cword} -eq 3 ]]; then
            COMPREPLY=( $(compgen -W "register refresh info" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        if [[ "${COMP_WORDS[3]}" == "register" ]]; then
            COMPREPLY=( $(compgen -f -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi
    fi
}

complete -F _rpp_completion rpp
'''


def command_completion(args) -> None:
    shell = (args.shell or "bash").lower()
    if shell != "bash":
        raise ValueError("Only bash completion is currently supported.")
    print(_render_bash_completion(), end="")
