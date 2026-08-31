from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import re
import tempfile
from typing import Dict, Optional, Tuple


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
from rpp_orchestrator.workspace import create_workspace
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
    if hasattr(args, "path") and getattr(args, "path") is not None:
        lib_path = Path(args.path).expanduser().resolve()
    else:
        lib_path = Path.cwd()
    if not lib_path.exists():
        lib_path.mkdir(parents=True, exist_ok=True)
    print(lib_path)
    created_path = manager.get_or_create_plugin_library(args.lib_name, str(lib_path))
    print(f"Created library: {args.lib_name} at {created_path}")




def command_registry_setting(args) -> None:
    expression = args.expression

    if expression is None:
        config = rp.get_config()
        print(json.dumps(config, indent=2, sort_keys=False))
        return

    setting_name, setting_value = expression.split("=")
    setting_name = setting_name.strip()
    setting_value = setting_value.strip()

    if not setting_name.isupper():
        raise ValueError(f"Setting name must be uppercase: {setting_name}")
    if rp.set_to_config(setting_name, setting_value):
        return 0
    return 1


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

def command_library_unregister_plugin(args, library_manager=None) -> None:
    manager = _get_library_manager(library_manager)
    plugin_name = args.plugin_name
    library = args.library
    removed = manager.unregister_plugin(plugin_name, library)
    if removed:
        print(f"Unregistered plugin '{plugin_name}' from library '{library}'")
    else:
        print(f"Plugin '{plugin_name}' not found in library '{library}'")


def command_library(args, library_manager=None) -> None:
    tokens = args.library_args or []
    if not tokens:
        print(
            "Error: No library command provided. Expected one of: "
            "register, unregister, refresh, info, list, or <lib_name>\n\n"
            "Usage: rpp library register <lib_path> | rpp library unregister <lib_name> | "
            "rpp library refresh <lib_name> | rpp library info <lib_name> | rpp library list | "
            "rpp library <lib_name> register <file_name> | rpp library <lib_name> unregister <plugin_name>"
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
        if len(tokens) != 2 and len(tokens) != 4:
            print("Error: Invalid number of arguments for 'create' command. Expected one argument."
                + " Usage: rpp library create <lib_name>")
            return 1
        return command_library_create(
            argparse.Namespace(lib_name=tokens[1], path=tokens[3] if len(tokens) == 4 else None),
            library_manager=library_manager
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

    library = tokens[0]
    action = tokens[1]
    if action == "register":
        if len(tokens) != 3:
            print("Error: Invalid number of arguments for 'register' command. Expected one argument."
                + " Usage: rpp library <lib_name> register <file_name>")
            return 1
        return command_library_register_plugin(
            argparse.Namespace(library=library, file_name=tokens[2]),
            library_manager=library_manager,
        )
    if action == "unregister":
        if len(tokens) != 3:
            print("Error: Invalid number of arguments for 'unregister' command. Expected one argument."
                + " Usage: rpp library <lib_name> unregister <plugin_name>")
            return 1
        return command_library_unregister_plugin(
            argparse.Namespace(library=library, plugin_name=tokens[2]),
            library_manager=library_manager,
        )

    print(
        "Unknown library action. Expected one of: register, unregister, refresh, info, list. "
        "Supported forms: rpp library register <lib_path> [--link], rpp library refresh <lib_name>, "
        "rpp library info <lib_name>, rpp library list, or rpp library <lib_name> register <file_name>."
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
    registry_api.ensure_rpp_layout(override_initialization=args.override)
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


def command_ws_create(args) -> int:
    base_root = Path(getattr(args, "root", ".")).expanduser().resolve()
    workspace_root = base_root / args.name
    create_workspace(workspace_root, name=args.name, overwrite=args.overwrite)
    print(f"Created workspace: {workspace_root}")
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
