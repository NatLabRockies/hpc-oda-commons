"""Dataset ids before #249 and now.

A dataset id used to name a task as well as the data (``dataset.job_runtime.pm100``); now it
names the data only (``dataset.pm100``). Every old id followed that one pattern, so the old
ids are derived from the new rather than listed.
"""

from __future__ import annotations

_RETIRED_TASK_SEGMENTS = ("job_runtime", "job_power")


def legacy_dataset_ids(dataset_id: str) -> tuple[str, ...]:
    """The ids ``dataset_id`` could have had before #249; none for an id of another shape."""
    prefix, _, name = dataset_id.partition(".")
    if prefix != "dataset" or not name or "." in name:
        return ()
    return tuple(f"dataset.{segment}.{name}" for segment in _RETIRED_TASK_SEGMENTS)


def dataset_name(dataset_id: str) -> str:
    """The short name a recipe, a bundle and a card use for a dataset (``lassen``).

    Registry ids (``dataset.lassen``) and the ids from before #249
    (``dataset.job_runtime.lassen``) give the same name, so a recipe may spell its dataset
    either way. Any other id (a path, a free-form label) is returned unchanged.
    """
    prefix, _, rest = dataset_id.partition(".")
    if prefix != "dataset" or not rest:
        return dataset_id
    segment, _, name = rest.partition(".")
    if name and segment in _RETIRED_TASK_SEGMENTS and "." not in name:
        return name
    return rest if "." not in rest else dataset_id
