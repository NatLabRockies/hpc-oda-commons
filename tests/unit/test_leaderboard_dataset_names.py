"""A run is listed under its dataset, not the table folder it read (#257)."""

from __future__ import annotations

from hpc_oda_commons.benchmark.results import _registered_dataset

REGISTERED = ["fdata_fugaku", "nlr_eagle", "nrel_eagle", "pm100"]


def test_a_registered_name_is_kept() -> None:
    assert _registered_dataset("pm100", REGISTERED) == "pm100"


def test_a_slice_or_embedded_copy_takes_its_dataset() -> None:
    assert _registered_dataset("nlr_eagle_power_embedded", REGISTERED) == "nlr_eagle"
    assert _registered_dataset("pm100_power_embedded", REGISTERED) == "pm100"
    assert _registered_dataset("fdata_fugaku_uopc", REGISTERED) == "fdata_fugaku"


def test_a_table_of_no_registered_dataset_keeps_its_name() -> None:
    assert _registered_dataset("example_cluster", REGISTERED) == "example_cluster"
    assert _registered_dataset("nlr", REGISTERED) == "nlr"
