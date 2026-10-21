"""Runs `docs/how-to/benchmark-your-data.md` as written (#255), so it can't go stale.

Every `bash` block in the guide runs, in order, in a fresh project folder, except the blocks
the guide marks "not run by the test" (setting up the folder, `sacct`, `open`). Three
substitutions keep it fast and offline, and nothing else changes:

- the embedding model is `stub`, so nothing is downloaded;
- `hpc-oda recipes write` writes four models (the window mean, the memorizer and the two
  embedding models) instead of all of them; `tests/unit/test_recipe_writer.py` checks the
  full set;
- there's no browser to `open`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "how-to" / "benchmark-your-data.md"
QUICK_MODELS = "--model baseline --model signature_memorizer --model embedding_knn --model uopc"


def guide_blocks() -> list[str]:
    """The guide's bash blocks the test runs, in order."""
    lines = GUIDE.read_text(encoding="utf-8").splitlines()
    blocks, current, skip, previous = [], None, False, ""
    for line in lines:
        stripped = line.strip()
        if current is None and stripped == "```bash":
            current, skip = [], previous.startswith("<!-- not run by the test")
        elif current is not None and stripped == "```":
            if not skip:
                blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(stripped)
        if stripped:
            previous = stripped
    return blocks


def _as_tested(block: str) -> str:
    block = block.replace("--model microsoft/harrier-oss-v1-0.6b", "--model stub")
    if "hpc-oda recipes write" in block:
        block = re.sub(r"--out recipes\b", f"--out recipes {QUICK_MODELS}", block)
    return block


def test_the_guide_marks_what_it_skips() -> None:
    blocks = guide_blocks()
    assert len(blocks) >= 10
    assert not any("sacct" in b or b.startswith("open ") for b in blocks)


@pytest.mark.integration
def test_the_guide_runs_as_written(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "REPO": str(ROOT),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    for block in guide_blocks():
        done = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", _as_tested(block)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, (
            f"{block}\n--- stdout\n{done.stdout}\n--- stderr\n{done.stderr}"
        )

    board = json.loads((tmp_path / "leaderboard" / "leaderboard.json").read_text())
    assert board["excluded"] == []
    tables = {t["target"]: t for t in board["tables"]}
    for target in ("runtime_seconds", "avgpcon_per_node"):
        rows = tables[target]["rows"]
        assert tables[target]["datasets"] == ["example_cluster"]
        assert {r["model"] for r in rows} >= {"model.baseline", "model.signature_memorizer"}
        assert all(r["cells"]["example_cluster"]["headroom"] is not None for r in rows)
    card = (tmp_path / "cards" / "example_cluster.md").read_text()
    assert "### Job runtime" in card and "### Average power per node" in card
