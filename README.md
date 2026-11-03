# rpp_cli

The `rpp` command-line entry point for registry, library, workspace, component,
configuration, compilation, test-fixture, and GUI operations. It is normally
installed by running `rpp_dev/setup.sh`.

Use `rpp --help` for the command hierarchy and `rpp <command> --help` for
arguments. The integration [CLI guide](../../rpp_docs/docs/cli.md) documents
the command groups, argument forms, Bash completion, and workflow examples.

Select a registry home with `rpp --rpp-home DIRECTORY <command>`. Workspaces
are initialized in registered libraries with `rpp ws create LIBRARY`.

