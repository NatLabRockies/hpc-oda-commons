#!/usr/bin/env python3
"""Small wrapper to detect hardware and write YAML/env files at repo root.

Usage: python3 scripts/detect_hardware_and_write.py
"""

from pathlib import Path

from hpc_oda_commons.utils import hardware


def main() -> int:
    out_yaml = Path(".hpc_oda_hardware.yaml")
    out_env = Path(".hpc_oda_hardware.env")
    info = hardware.detect_hardware()
    hardware.write_yaml(out_yaml, info)
    hardware.write_env_file(out_env, info)
    print(f"Wrote {out_yaml} and {out_env}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
