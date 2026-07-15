import json
from pathlib import Path

from hpc_oda_commons.utils import hardware


def test_detect_hardware_shape_and_summary_consistency():
    info = hardware.detect_hardware()

    expected = {
        "platform",
        "python_version",
        "cpu_count_logical",
        "system_memory_bytes",
        "torch_available",
        "cuda_available",
        "cuda_device_count",
        "cuda_devices",
        "mps_available",
        "summary",
    }
    assert expected.issubset(set(info.keys()))
    assert isinstance(info["platform"], str) and info["platform"]
    assert isinstance(info["python_version"], str) and info["python_version"]
    assert isinstance(info["cuda_devices"], list)
    assert isinstance(info["summary"], dict)

    summary = info["summary"]
    assert summary["has_cuda"] == info["cuda_available"]
    assert summary["cuda_count"] == info["cuda_device_count"]
    assert summary["has_mps"] == info["mps_available"]
    assert summary["cpu_count"] == info["cpu_count_logical"]


def test_write_and_read_env_file_roundtrip(tmp_path: Path):
    info = hardware.detect_hardware()
    out = tmp_path / "hardware.env"
    hardware.write_env_file(out, info)
    parsed = hardware.read_env_file(out)

    # Ensure key outputs are present and aligned with summary/data values.
    summary = info["summary"]
    assert parsed["HAS_CUDA"] == summary["has_cuda"]
    assert parsed["CUDA_COUNT"] == info["cuda_device_count"]
    assert parsed["HAS_MPS"] == summary["has_mps"]
    assert parsed["CPU_COUNT"] == info["cpu_count_logical"]


def test_write_yaml_outputs_parseable_content(tmp_path: Path):
    info = hardware.detect_hardware()
    out = tmp_path / "hardware.yaml"
    hardware.write_yaml(out, info)
    text = out.read_text(encoding="utf-8")

    # Accept either YAML (preferred) or JSON fallback; both should be parseable.
    if text.lstrip().startswith("{"):
        loaded = json.loads(text)
    else:
        # yaml is optional at import time, but if YAML text is written then parser should exist.
        loaded = hardware.yaml.safe_load(text)
    assert isinstance(loaded, dict)
    assert loaded.get("platform") == info.get("platform")
