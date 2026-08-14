"""
Which columns a runtime-prediction model is allowed to use as features.

``oda.job.v0.2.0`` sets ``additionalProperties: true``: any column a dataset
descriptor maps lands in the normalized table. Selecting features by *excluding*
known-bad columns therefore fails open — a new dataset carrying, say, an
``exit_code`` or ``*_alloc`` column silently hands the model information that
does not exist at submit time. ``job_state`` is the extreme case: a job that ran
into its wallclock limit is labelled ``TIMEOUT``, which all but states the target.

So the policy is an allowlist of submission-time concepts, and anything else is
ignored unless a caller opts it in via ``extra_feature_fields``. Two canonical
vocabularies appear in practice — the dataset descriptors' (``num_cores_req``,
``requested_seconds``) and the ingest wizard's (``processors_requested``,
``wallclock_requested``) — so both spellings are listed, mirroring the concept
map already used to serialize rows for embedding
(``hpc_oda_commons.embeddings.serialize``).

Deliberately absent, because they are only known once a job has been dispatched
or has finished: ``job_state``, ``exit_code``, ``allocated_cpus``,
``num_cores_alloc``, ``num_nodes_alloc``, ``allocgpus``, ``start_time``,
``end_time``, ``runtime_seconds``. ``job_id`` is absent as a pure identifier.
"""

from __future__ import annotations

from collections.abc import Iterable

RUNTIME_PREDICTION_FEATURE_FIELDS: frozenset[str] = frozenset(
    {
        # --- Resource requests (chosen by the user at submit time) ---
        "num_nodes_req",
        "nodes_requested",
        "num_cores_req",
        "processors_requested",
        "num_gpus_req",
        "gpus_requested",
        "num_tasks_req",
        "requested_seconds",
        "wallclock_requested",
        "wallclock_requested_seconds",
        "requested_memory_mib",
        "memory_requested",
        # --- Scheduling context (known when the job is queued) ---
        "partition",
        "queue",
        "qos",
        "constraints",
        # --- Identity (known at submit time; usually hashed) ---
        "user",
        "account",
        # --- Job metadata (set by the submitter) ---
        "name",
        "job_name",
        "job_type",
        "platform",
        "machine",
        "machine_name",
        "science_field",
        "science_field_short",
        "award_category",
        "submit_line",
        "work_dir",
        "script",
    }
)


def partition_feature_fields(
    present: Iterable[str], *, extra: Iterable[str] = ()
) -> tuple[list[str], list[str]]:
    """Split the column names present in a table into (usable, ignored).

    ``extra`` admits dataset-specific columns the shared allowlist cannot know
    about. Both lists are sorted, so they are stable to log and to assert on.
    """
    allowed = RUNTIME_PREDICTION_FEATURE_FIELDS | frozenset(extra)
    usable: list[str] = []
    ignored: list[str] = []
    for name in sorted(set(present)):
        (usable if name in allowed else ignored).append(name)
    return usable, ignored
