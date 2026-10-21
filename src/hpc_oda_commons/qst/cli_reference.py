"""docs/reference/cli.md is generated from the CLI's own help text (#257).

The help strings are the one home for what each command and option does; this page is
their printed copy. Regenerate it with ``make docs-cli`` after changing a command, and
``tests/unit/test_cli_reference.py`` fails when the committed page differs.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import typer
from typer.cli import get_docs_for_click

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

    command = typer.main.get_command(app)
    ctx = typer.Context(command)
    body = get_docs_for_click(obj=command, ctx=ctx, name="hpc-oda", title="Commands")
    # Typer escapes quotes for HTML; plain characters read better in the Markdown source.
    body = html.unescape(body).strip()
    # Click's "\b" (keep this paragraph's line breaks) means nothing in Markdown.
    body = body.replace("\n\b\n", "\n")
    # The generated title is a level-1 heading; the page already has one.
    body = body.replace("# Commands", "## Commands", 1)
    body = "\n".join(
        "#" + line if line.startswith("## `hpc-oda") else line for line in body.splitlines()
    )
    return INTRO + body + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else CLI_REFERENCE
    out.write_text(render(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
