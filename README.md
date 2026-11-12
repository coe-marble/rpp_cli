# rpp_cli

The `rpp` command-line entry point for registry, library, workspace, component,
configuration, compilation, test-fixture, and GUI operations. It is normally
installed by running `rpp_dev/setup.sh`.

Use `rpp --help` for the command hierarchy and `rpp <command> --help` for
arguments. The integration [CLI guide](../../rpp_docs/docs/cli.md) documents
the command groups, argument forms, Bash completion, and workflow examples.

Select a registry home with `rpp --rpp-home DIRECTORY <command>`. Workspaces
are initialized in registered libraries with `rpp ws create LIBRARY`.

After installing a new `rpp-plugin-registrator` version, preview and migrate an
existing registry with:

```bash
rpp registry migrate --dry-run
rpp registry migrate
# Keep the partially migrated registry on failure, retaining the backup:
rpp registry migrate --no-restore
# For a different registry:
rpp --rpp-home /path/to/.rpp registry migrate
```

Stop plugin managers and processes using generated interfaces before migrating,
then restart them afterward. Migration regenerates bundled native libraries
(`rpp_common`, `rpp_testing`) and refreshes every registered user library in
dependency order, even libraries already marked current. This can compile C++
plugins and requires their usual compiler and dependencies. It targets the
installed registrator version; it does not install or upgrade Python packages.

The command keeps library registrations, linked source paths, and workspace
data. Before regeneration it saves a full registry-home backup in a sibling
directory and prints its path. A regeneration failure or interruption restores
the registry's generated files and library registrations from that backup;
`--no-restore` skips this restoration and leaves migration changes in place.
The backup is retained in both modes, on success and failure. Failures print
the full Python traceback, including chained exceptions. Linked source files are read in
place, not copied or rewritten. Missing dependencies, dependency cycles,
missing declared sources, and libraries registered by a newer registrator are
reported before regeneration. The preview does not write files or compile.
To restore manually with all RPP processes stopped, copy the contents of the
printed backup directory back to the selected registry home.

Use migration to upgrade an existing registry. `rpp init-home --override` resets
the registry and removes installed libraries.

