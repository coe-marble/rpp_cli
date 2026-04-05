from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Dict

from rpp_plugin_registrator.interface_generators import generate_interface
from rpp_plugin_registrator.plugin_descriptors import (
    parse_plugin_file,
    resolve_plugin_id_override,
)
from rpp_plugin_registrator.library_manager import LibraryManager
import rpp_plugin_registrator.plugin_type_registrator as registry_api
from rpp_plugin_registrator.scaffold import scaffold_cpp, scaffold_python
from rpp_plugin_registrator.utils import to_snake_case


def _describe_source(source_path: Path, language: str | None, plugin_id: str | None) -> Dict:
    return parse_plugin_file(source_path, plugin_id_override=plugin_id)  # type: ignore


def _get_library_manager(library_manager=None) -> LibraryManager:
    return library_manager if library_manager is not None else LibraryManager()


def command_describe(args) -> None:
    source_path = Path(args.source).resolve()
    description = _describe_source(source_path, args.language, resolve_plugin_id_override(args))
    print(json.dumps(description, indent=2, sort_keys=False))


def command_register(args, library_manager=None) -> None:
    if hasattr(args, "lib_path") and getattr(args, "lib_path") is not None:
        manager = _get_library_manager(library_manager)
        lib_path = Path(args.lib_path).expanduser().resolve()
        registered_path = manager.register_component_library(str(lib_path), link_register=False, ask_dialog=False)
        print(f"Registered library: {registered_path}")
        return

    # Backward-compatible form used by older tests/programmatic callers:
    # register plugin descriptions/sources into registry.
    registry_api.ensure_rpp_layout()
    paths = registry_api.get_rpp_paths()
    registry_path = registry_api.resolve_output_path(getattr(args, "registry", None), paths["registry"])
    library = getattr(args, "library", "legacy")

    folder = getattr(args, "folder", None)
    if folder:
        folder_path = Path(folder).expanduser().resolve()
        registered_files = registry_api.register_plugin_types_in_folder(folder_path, registry_path, library=library)
        if not registered_files:
            print(f"No plugin description files found in folder: {folder_path}")
        else:
            print(f"Registered {len(registered_files)} plugin descriptions from folder: {folder_path}")
            for file_path in registered_files:
                print(f"- {file_path}")
        print(f"Registry path: {registry_path}")
        return

    source = getattr(args, "source", None)
    if not source:
        raise ValueError("Either 'lib_path' or one of 'source'/'folder' must be provided for register command.")

    source_path = Path(source).expanduser().resolve()
    if source_path.suffix.lower() == ".json":
        registry_api.register_plugin_type(source_path, registry_path, library=library)
        print(f"Registered plugin from description: {source_path}")
        print(f"Registry path: {registry_path}")
        return

    plugin_id_override = resolve_plugin_id_override(args)
    description = parse_plugin_file(source_path, plugin_id_override=plugin_id_override)
    plugin = description.get("Plugin", {})
    plugin_id = plugin.get("Id") or plugin_id_override or f"rpp_{to_snake_case(plugin.get('ClassName') or plugin.get('Name') or source_path.stem)}"
    if not plugin_id:
        raise ValueError(f"Plugin description for '{source_path}' does not include Plugin.Id")

    plugin["Id"] = plugin_id

    registry = registry_api.load_registry()
    plugins = registry.setdefault("PluginTypes", {})
    registry_api.validate_unique_plugin_id(plugin_id, plugins)
    registry_api.validate_unique_class_name(plugin.get("ClassName"), plugin_id, plugins)

    description_path = registry_api.resolve_output_path(
        getattr(args, "description", None),
        paths["descriptions"] / f"{plugin_id}.plugin.json",
    )
    registry_api.write_json(description_path, description)
    registry_api.register_plugin_type(description_path, registry_path, library=library)

    print(f"Described and registered plugin '{plugin_id}'")
    print(f"Source: {source_path}")
    print(f"Description: {description_path}")
    print(f"Registry path: {registry_path}")


def command_unregister(args, library_manager=None) -> None:
    # New form: library removal by name.
    if hasattr(args, "lib_name") and getattr(args, "lib_name") is not None:
        manager = _get_library_manager(library_manager)
        removed = manager.remove_component_library(args.lib_name)
        print(f"Removed library: {removed}")
        return

    # Backward-compatible form: unregister plugin type from registry.
    plugin_id = getattr(args, "plugin_id", None)
    if not plugin_id:
        raise ValueError("Either 'lib_name' or 'plugin_id' must be provided for unregister command.")

    registry_api.ensure_rpp_layout()
    paths = registry_api.get_rpp_paths()
    registry_path = registry_api.resolve_output_path(getattr(args, "registry", None), paths["registry"])
    library = getattr(args, "library", "legacy")
    removed = registry_api.unregister_plugin_type(plugin_id, registry_path, library=library)
    if removed:
        print(f"Unregistered plugin '{plugin_id}' from {registry_path}")
    else:
        print(f"Plugin '{plugin_id}' not found in {registry_path}")


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


def command_library_refresh(args, library_manager=None) -> None:
    library = args.library
    manager = _get_library_manager(library_manager)
    manager.refresh_component_library(library)
    print(f"Refreshing library '{library}'...")
    print(f"Library: {library}")
    print("Library refresh completed.")


def command_library_register_component(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    source_path = Path(args.file_name).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Plugin source file does not exist: {source_path}")
    manager.register_component_from_file(str(source_path), args.library)
    manager.refresh_component_library(args.library)
    print(f"Registered plugin file '{source_path}' into library '{args.library}'")


def command_library(args, library_manager=None) -> None:
    tokens = args.library_args or []
    if not tokens:
        raise ValueError(
            "Usage: rpp library register <lib_path> | rpp library unregister <lib_name> | "
            "rpp library <lib_name> register <file_name> | rpp library <lib_name> refresh"
        )

    if tokens[0] == "register":
        if len(tokens) != 2:
            raise ValueError("Usage: rpp library register <lib_path>")
        return command_register(argparse.Namespace(lib_path=tokens[1]), library_manager=library_manager)

    if tokens[0] == "unregister":
        if len(tokens) != 2:
            raise ValueError("Usage: rpp library unregister <lib_name>")
        return command_unregister(argparse.Namespace(lib_name=tokens[1]), library_manager=library_manager)

    library = tokens[0]
    if len(tokens) < 2:
        raise ValueError("Usage: rpp library <lib_name> register <file_name> | rpp library <lib_name> refresh")

    action = tokens[1]
    if action == "register":
        if len(tokens) != 3:
            raise ValueError("Usage: rpp library <lib_name> register <file_name>")
        return command_library_register_component(
            argparse.Namespace(library=library, file_name=tokens[2]),
            library_manager=library_manager,
        )

    if action == "refresh":
        if len(tokens) != 2:
            raise ValueError("Usage: rpp library <lib_name> refresh")
        return command_library_refresh(argparse.Namespace(library=library), library_manager=library_manager)

    raise ValueError(
        "Unknown library action. Expected one of: register, unregister, refresh. "
        "Supported forms: rpp library register <lib_path> or rpp library <lib_name> register <file_name>."
    )


def command_init_home(args) -> None:
    registry_api.ensure_rpp_layout(override_initialization=True)
    paths = registry_api.get_rpp_paths()
    print(f"Initialized rpp home at: {paths['home']}")
    print(f"Descriptions: {paths['descriptions']}")
    print(f"Interfaces: {paths['interfaces']}")
    print(f"Registry: {paths['registry']}")


def command_pm(args) -> int:
    plugin_manager_module = importlib.import_module("rpp_plugin_registrator.gui")
    result = plugin_manager_module.main()
    return int(result or 0)


def command_list_registry(args) -> None:
    paths = registry_api.get_rpp_paths()
    registry_path = registry_api.resolve_output_path(args.registry, paths["registry"])
    registry = registry_api.list_registered_plugin_types(registry_path)
    plugins = registry.get("PluginTypes", {})

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


def command_registry_info(args) -> None:
    paths = registry_api.get_rpp_paths()
    registry_path = registry_api.resolve_output_path(args.registry, paths["registry"])
    registry = registry_api.list_registered_plugin_types(registry_path)
    plugins = registry.get("PluginTypes", {})

    plugin_data = plugins.get(args.tag)
    if plugin_data is None:
        raise ValueError(f"Plugin '{args.tag}' not found in registry: {registry_path}")

    description_file = plugin_data.get("DescriptionFile")
    if not description_file:
        raise ValueError(f"Plugin '{args.tag}' has no DescriptionFile in registry.")

    description_payload = registry_api.load_json(Path(description_file).expanduser().resolve())
    print(json.dumps(description_payload, indent=2, sort_keys=False))


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
    # rpp library <lib_name> register <file_name>
    # rpp library <lib_name> refresh
    if [[ "${COMP_WORDS[1]}" == "library" ]]; then
        local libs
        if [[ -d "$HOME/.rpp/libraries" ]]; then
            libs=$(ls -1 "$HOME/.rpp/libraries" 2>/dev/null | sed 's/\.json$//' | sort -u)
        else
            libs=""
        fi

        if [[ ${cword} -eq 2 ]]; then
            COMPREPLY=( $(compgen -W "register unregister ${libs}" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library register <lib_path>
        if [[ "${COMP_WORDS[2]}" == "register" ]]; then
            COMPREPLY=( $(compgen -d -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library unregister <lib_name>
        if [[ "${COMP_WORDS[2]}" == "unregister" ]]; then
            COMPREPLY=( $(compgen -W "${libs}" -- "$cur") )
            _rpp_gate_compreply "$cur"
            return 0
        fi

        # rpp library <lib_name> register <file_name>
        # rpp library <lib_name> refresh
        if [[ ${cword} -eq 3 ]]; then
            COMPREPLY=( $(compgen -W "register refresh" -- "$cur") )
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
