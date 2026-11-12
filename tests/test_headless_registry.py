import json
import os
import subprocess
import sys
import textwrap


def test_build_can_write_runtime_path_without_importing_workspace_cli_or_qt(tmp_path):
    # A fresh process cannot hide eager GUI imports behind cached modules.
    program = textwrap.dedent("""\
        import importlib.abc
        import sys

        class RejectGuiImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if (fullname == "rpp_orchestrator.cli"
                        or fullname.startswith("rpp_orchestrator.gui")
                        or fullname == "rpp_plugin_registrator.gui"
                        or fullname == "PyQt6" or fullname.startswith("PyQt6.")):
                    raise ImportError(f"GUI import attempted by registry command: {fullname}")

        sys.meta_path.insert(0, RejectGuiImports())
        from rpp_cli.cli import main
        raise SystemExit(main())
        """)
    registry_home = tmp_path / "registry"
    runtime_path = tmp_path / "rpp_cpp"
    result = subprocess.run(
        [sys.executable, "-c", program, "--rpp-home", str(registry_home),
         "registry", "config", "set", "RPP_CPP_CORE_PATH", str(runtime_path)],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads((registry_home / "config.json").read_text())
    assert config["RPP_CPP_CORE_PATH"] == str(runtime_path)
