"""Write a made-up Slurm accounting export to try `benchmark-your-data.md` on.

It has the shape of `sacct -a -X -P -o <fields>` run with TZ=UTC: one job per line, fields
separated by `|`. 240 days of jobs from 30 users, with energy readings. Each user has habits
(partition, job size, requested time, typical runtime and power), so the models have
something to learn. Seeded, so every run writes the same file.

    python docs/how-to/benchmark-your-data/make_example_export.py exports/
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = (
    "JobID|User|Account|Partition|QOS|JobName|Submit|Start|End|ElapsedRaw|TimelimitRaw"
    "|ReqNodes|NNodes|ReqCPUS|ConsumedEnergyRaw|State"
)
DAYS = 240
JOBS_PER_DAY = 40
START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%S")


def write_export(path: Path, *, seed: int = 255) -> Path:
    rng = random.Random(seed)
    users = []
    for u in range(30):
        users.append(
            {
                "user": f"user{u:02d}",
                "account": f"proj{u % 10}",
                "partition": rng.choice(["standard", "standard", "gpu", "debug"]),
                "apps": [f"app{rng.randrange(12)}" for _ in range(3)],
                "nodes": rng.choice([1, 1, 2, 4, 8]),
                "minutes": rng.choice([30, 60, 120, 240, 480, 1440]),
                "fill": rng.uniform(0.2, 0.9),
                "watts": rng.uniform(250.0, 700.0),
            }
        )
    lines = [FIELDS]
    job = 100000
    for day in range(DAYS):
        for _ in range(rng.randint(JOBS_PER_DAY - 15, JOBS_PER_DAY + 15)):
            who = rng.choice(users)
            app = rng.choice(who["apps"])
            nodes = max(1, who["nodes"] * rng.choice([1, 1, 1, 2]) // rng.choice([1, 1, 2]))
            limit = who["minutes"]
            app_factor = 0.5 + (int(app[3:]) % 5) / 4
            runtime = int(limit * 60 * min(1.0, who["fill"] * app_factor * rng.uniform(0.6, 1.4)))
            runtime = max(30, runtime)
            state = (
                "TIMEOUT" if runtime >= limit * 60 else rng.choice(["COMPLETED"] * 9 + ["FAILED"])
            )
            submit = START + timedelta(days=day, seconds=rng.randrange(86400))
            start = submit + timedelta(seconds=rng.randrange(0, 7200))
            end = start + timedelta(seconds=runtime)
            # Joules over the job's nodes; some jobs have no reading (0), as on shared nodes.
            watts = who["watts"] * (0.8 + 0.1 * (int(app[3:]) % 4)) * rng.uniform(0.9, 1.1)
            energy = 0 if rng.random() < 0.05 else int(watts * nodes * runtime)
            lines.append(
                "|".join(
                    str(v)
                    for v in (
                        job,
                        who["user"],
                        who["account"],
                        who["partition"],
                        "normal" if who["partition"] != "debug" else "debug",
                        f"{app}_run",
                        _iso(submit),
                        _iso(start),
                        _iso(end),
                        runtime,
                        limit,
                        nodes,
                        nodes,
                        nodes * 36,
                        energy,
                        state,
                    )
                )
            )
            job += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "exports")
    print(write_export(out / "example_cluster_sacct.txt"))
