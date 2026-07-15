"""Unit tests for job-script residual reduction (strip #SBATCH + set-common lines)."""

from __future__ import annotations

import pytest

from hpc_oda_commons.embeddings.script_residual import compute_residuals, strip_sbatch


def test_strip_sbatch_drops_directives_keeps_body():
    script = "#!/bin/bash\n#SBATCH -N 4\n  #SBATCH --qos=normal\nmodule load foo\nsrun ./a.out"
    body = strip_sbatch(script)
    assert body == ["#!/bin/bash", "module load foo", "srun ./a.out"]  # #SBATCH lines gone


def test_group_residual_keeps_only_distinguishing_lines():
    # three prose-twins sharing a template, each with one unique line
    common = "#!/bin/bash\nmodule load foo\nsrun ./run.sh"
    scripts = [
        common + "\nINPUT=a.dat",
        common + "\nINPUT=b.dat",
        common + "\nINPUT=c.dat",
    ]
    keys = ["same", "same", "same"]
    residuals, stats = compute_residuals(scripts, keys)
    assert residuals == ["INPUT=a.dat", "INPUT=b.dat", "INPUT=c.dat"]  # template stripped
    assert stats.groups == 1
    assert stats.singletons == 0
    assert stats.empty_residual_rows == 0


def test_sbatch_stripped_before_grouping():
    # #SBATCH lines differ but are directives -> removed first, so residual is the body delta
    scripts = [
        "#SBATCH -N 4\nmodule load foo\nINPUT=a",
        "#SBATCH -N 8\nmodule load foo\nINPUT=b",
    ]
    residuals, _ = compute_residuals(scripts, ["k", "k"])
    assert residuals == ["INPUT=a", "INPUT=b"]  # shared 'module load foo' + all #SBATCH gone


def test_singleton_keeps_whole_stripped_script():
    scripts = ["#SBATCH -N 1\nmodule load bar\nsrun ./x", "#SBATCH -N 2\nfoo\nbar"]
    residuals, stats = compute_residuals(scripts, ["unique_a", "unique_b"])
    assert residuals[0] == "module load bar\nsrun ./x"  # #SBATCH stripped, rest kept
    assert residuals[1] == "foo\nbar"
    assert stats.singletons == 2
    assert stats.groups == 2


def test_identical_scripts_in_group_yield_empty_residuals():
    scripts = ["module load foo\nsrun ./a", "module load foo\nsrun ./a"]
    residuals, stats = compute_residuals(scripts, ["k", "k"])
    assert residuals == ["", ""]  # everything common -> nothing distinguishing
    assert stats.empty_residual_rows == 2


def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        compute_residuals(["a"], ["k1", "k2"])
