import tempfile

from rpp_plugin_registrator.library_manager import LibraryManager
from dataclasses import dataclass
from pathlib import Path
import shutil

@dataclass
class RppHandle:
    td: tempfile.TemporaryDirectory
    out_dir: Path
    home: Path
    library_manager: LibraryManager
    test_lib: str
    plugins: list = None  # Optional: Store the list of plugins if needed


RPP_TESTING_PATH = Path(__file__).parent.parent.resolve() \
    / "rpp_testing" / "rpp_testing"

BLACKLISTED_PLUGINS = [
    "example_plugin_with_dependencies"
]


def setup_tmp_rpp_with_test_plugins(
        out_dir: Path = None,
        override: bool = False,
        component_whitelist: list = None) -> RppHandle:
    td = None
    if out_dir is None:
        td = tempfile.TemporaryDirectory()
        out_dir = Path(td.name)
    else:
        if not Path(out_dir).exists():
            raise ValueError(f"Provided out_dir '{out_dir}' does not exist.")

    test_lib = "test_lib"
    home = Path(out_dir) / ".rpp"
    if home.exists():
        if override:
            shutil.rmtree(home)
        else:
            lm = LibraryManager(rpp_home=home)
            plugins = lm.get_library_plugins(test_lib)
            plugin_return = [{
                "PluginName": plugin["PluginName"], "SourceLanguage": plugin["SourceLanguage"]} for plugin in plugins.values()]
            return RppHandle(td=td, out_dir=out_dir, home=home, library_manager=lm, test_lib=test_lib, plugins=plugin_return)

    home.mkdir(parents=True, exist_ok=True)
    library_manager = LibraryManager(rpp_home=home)
    library = library_manager.get_or_create_plugin_library(test_lib)

    test_data_dir = RPP_TESTING_PATH / "data"
    library_plugins_dir = Path(library.path) / "plugins"
    library_plugins_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(test_data_dir / "example_plugins", library_plugins_dir, dirs_exist_ok=True)
    plugins = []
    for plugin_file in library_plugins_dir.glob("*.py"):
        if plugin_file.stem in BLACKLISTED_PLUGINS:
            continue
        if component_whitelist is not None and plugin_file.name not in component_whitelist:
            continue
        info = library_manager.register_plugin_from_source(plugin_file, test_lib)
        plugins.append({"PluginName": info["PluginName"], "SourceLanguage": info["SourceLanguage"]})
    for plugin_file in library_plugins_dir.glob("*.cpp"):
        if plugin_file.stem in BLACKLISTED_PLUGINS:
            continue
        if component_whitelist is not None and plugin_file.name not in component_whitelist:
            continue
        info = library_manager.register_plugin_from_source(plugin_file, test_lib)
        plugins.append({"PluginName": info["PluginName"], "SourceLanguage": info["SourceLanguage"]})

    return RppHandle(td=td, out_dir=out_dir, home=home, library_manager=library_manager, test_lib=test_lib, plugins=plugins)