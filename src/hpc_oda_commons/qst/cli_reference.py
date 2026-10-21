"""docs/reference/cli.md is generated from the CLI's own help text (#257).

The help strings are the one home for what each command and option does; this page is
their printed copy. Regenerate it with ``make docs-cli`` after changing a command, and
``tests/unit/test_cli_reference.py`` fails when the committed page differs.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import click
import typer

CLI_REFERENCE = Path("docs/reference/cli.md")

INTRO = """\
# CLI reference

Every `hpc-oda` command and option, generated from the CLI's own `--help` text. Don't edit
this page: change the help text in `src/hpc_oda_commons/qst/` and run `make docs-cli`.

Run the commands from the root of a checkout. Several defaults are paths in the repository,
such as `docs/benchmarking/datasets` and `docs/models`.

For the workflows these commands make up, see the [quickstart](../how-to/quickstart.md) and
[Benchmark your own data](../how-to/benchmark-your-data.md).

## Environment variables

| Variable | Effect |
|---|---|
| `HPC_ODA_OFFLINE` | `1` makes `datasets fetch` and `datasets prepare` refuse the network. The integration tests set it. |
| `HPC_ODA_CACHE_DIR` | Where fetched datasets are cached. Default `.hpc_oda/cache/datasets`. |
| `HPC_ODA_PREPROCESSING_CACHE` | Where the rolling tabular models keep their preprocessing between runs. Default `.hpc_oda/cache/preprocessing`; `off` turns it off. |
| `HPC_ODA_HASH_SALT` | The salt for hashed identifiers, when a mapping names it in `salt_env` (the ingest wizard does). |

"""


def render() -> str:
    """The page, as `make docs-cli` writes it."""
    from hpc_oda_commons.qst.cli import app

    root = typer.main.get_command(app)
    lines = ["## Commands", "", _help(root), ""]
    lines += [f"- `{name}`: {_summary(sub)}" for name, sub in root.commands.items()]  # type: ignore[attr-defined]
    lines += [""]
    for path, command in _walk(root, ["hpc-oda"]):
        lines += _command(path, command)
    return INTRO + "\n".join(lines).rstrip() + "\n"


# The page is built from the click objects directly, not by typer's own docs command:
# that renders option types differently from one typer or click release to the next,
# and the page must read the same wherever the test runs.


def _walk(command: click.Command, path: list[str]):
    for name, sub in getattr(command, "commands", {}).items():
        yield [*path, name], sub
        yield from _walk(sub, [*path, name])


def _help(command: click.Command) -> str:
    text = inspect.cleandoc(command.help or "")
    # Click's "\b" (keep this paragraph's line breaks) means nothing in Markdown.
    return "\n".join(line for line in text.splitlines() if line != "\b")


def _summary(command: click.Command) -> str:
    """A command's first line of help."""
    return _help(command).split("\n")[0]


def _command(path: list[str], command: click.Command) -> list[str]:
    params = [p for p in command.params if not getattr(p, "hidden", False)]
    arguments = [p for p in params if p.param_type_name == "argument"]
    options = [p for p in params if not p.param_type_name == "argument"]
    subcommands = getattr(command, "commands", {})
    usage = " ".join(
        [*path]
        + (["[OPTIONS]"] if options else [])
        + [str(p.name).upper() for p in arguments]
        + (["COMMAND"] if subcommands else [])
    )
    out = [f"### `{' '.join(path)}`", "", _help(command), "", "```console", usage, "```", ""]
    if arguments:
        out += ["**Arguments:**", ""] + [_param(p) for p in arguments] + [""]
    if options:
        out += ["**Options:**", ""] + [_param(p) for p in options] + [""]
    if subcommands:
        out += ["**Commands:**", ""]
        out += [f"- `{name}`: {_summary(sub)}" for name, sub in subcommands.items()]
        out += [""]
    return out


def _kind(kind: object) -> str:
    """A value's kind by its type's class name: typer may carry its own click, and click's
    type names differ between releases."""
    names = {k.__name__ for k in type(kind).__mro__}
    if names & {"Path", "TyperPath"}:
        return "PATH"
    if names & {"IntParamType", "IntRange"}:
        return "INTEGER"
    if names & {"FloatParamType", "FloatRange"}:
        return "NUMBER"
    return "TEXT"


def _param(param: click.Parameter) -> str:
    if param.param_type_name == "argument":
        names = str(param.name).upper()
    else:
        value = "" if getattr(param, "is_flag", False) else f" {_kind(param.type)}"
        names = ", ".join(f"`{opt}{value}`" for opt in [*param.opts, *param.secondary_opts])
    if param.param_type_name == "argument":
        names = f"`{names}`"
    text = getattr(param, "help", None) or ""
    notes = []
    if param.required:
        notes.append("Required.")
    if param.multiple:
        notes.append("Repeatable.")
    default = param.default
    flag = getattr(param, "is_flag", False)
    if flag and param.secondary_opts and default is not None:
        notes.append(f"Default: `{param.opts[0] if default else param.secondary_opts[0]}`.")
    elif not flag and default not in (None, "", ()) and not param.required:
        notes.append(f"Default: `{default}`.")
    return f"- {names}: " + " ".join(x for x in [text, *notes] if x)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else CLI_REFERENCE
    out.write_text(render(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
