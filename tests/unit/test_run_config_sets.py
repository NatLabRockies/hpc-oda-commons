"""Set-valued config is recorded as a sorted list, the same in every process (#211).

``to_jsonable`` used to fall through to ``str()`` for sets, so ``run_config`` carried
``"frozenset()"``, and a non-empty set's elements came out in hash-seed order:
``bench-matrix rank`` could then key one arm two ways.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from hpc_oda_commons.benchmark.results import _normalize_legacy_sets
from hpc_oda_commons.benchmark.runner import resolved_run_config
from hpc_oda_commons.kernel.serialization import to_jsonable
from hpc_oda_commons.models.job_runtime_tfidf_knn.model import (
    JobRuntimeTfidfKnnConfig,
    JobRuntimeTfidfKnnModel,
)


def test_sets_become_sorted_lists() -> None:
    assert to_jsonable(frozenset()) == []
    assert to_jsonable({"user", "partition", "qos"}) == ["partition", "qos", "user"]
    assert to_jsonable({"nested": frozenset({2, 1})}) == {"nested": [1, 2]}


def test_mixed_types_still_sort() -> None:
    """Ordered by type name, then value, so ints and strings never compare directly."""
    assert to_jsonable({"b", 2, "a", 1}) == [1, 2, "a", "b"]


def test_the_output_does_not_depend_on_the_hash_seed() -> None:
    code = (
        "import json; from hpc_oda_commons.kernel.serialization import to_jsonable; "
        "print(json.dumps(to_jsonable(frozenset({'user', 'partition', 'qos', 'account'}))))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in range(6)
    }
    assert outputs == {'["account", "partition", "qos", "user"]\n'}


def test_run_config_records_extra_feature_fields_as_a_list() -> None:
    model = JobRuntimeTfidfKnnModel(
        JobRuntimeTfidfKnnConfig(extra_feature_fields=frozenset({"qos", "account"}))
    )
    config = resolved_run_config(model)

    assert config["extra_feature_fields"] == ["account", "qos"]
    assert resolved_run_config(JobRuntimeTfidfKnnModel())["extra_feature_fields"] == []
    json.dumps(config)  # and it is plain JSON


def test_legacy_set_reprs_read_as_the_list_written_now() -> None:
    config = {
        "empty": "frozenset()",
        "some": "frozenset({'user', 'qos'})",
        "plain_set": "set()",
        "k": 5,
        "name": "not a set",
        "looks_like_one": "frozenset(__import__('os'))",
    }
    assert _normalize_legacy_sets(config) == {
        "empty": [],
        "some": ["qos", "user"],
        "plain_set": [],
        "k": 5,
        "name": "not a set",
        "looks_like_one": "frozenset(__import__('os'))",  # not a literal: left alone
    }
