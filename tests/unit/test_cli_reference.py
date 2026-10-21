"""docs/reference/cli.md is generated from the CLI's help text (#257); this keeps it so."""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.qst import cli_reference

ROOT = Path(__file__).resolve().parents[2]


def test_committed_cli_reference_is_what_the_generator_writes() -> None:
    """Change a command or its help text without running `make docs-cli`, and this fails."""
    committed = (ROOT / cli_reference.CLI_REFERENCE).read_text(encoding="utf-8")
    assert committed == cli_reference.render(), "stale CLI reference: run `make docs-cli`"


def test_every_command_is_on_the_page() -> None:
    import typer

    from hpc_oda_commons.qst.cli import app

    page = cli_reference.render()
    command = typer.main.get_command(app)
    for name, sub in command.commands.items():  # type: ignore[attr-defined]
        assert f"### `hpc-oda {name}`" in page
        for child in getattr(sub, "commands", {}):
            assert f"### `hpc-oda {name} {child}`" in page
