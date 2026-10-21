"""The registry, built from the files that define each entry (#249).

Nothing in an entry is written by hand in two places, so the registry cannot drift from what
it describes:

- **models:** the title, version, method description and class come from
  ``models/<name>/model.yml``, next to the code. The id comes from the folder, the tasks a
  model serves from the bundled recipes that run it, the input schema from those recipes,
  and its third-party dependencies from the imports in its code and its shared bases.
- **adapters:** ``adapters/<name>/adapter.yml``, next to the code.
- **datasets:** the descriptor. The tasks a dataset serves come from its mapping.
- **recipes:** the recipe file. Its name and description are worked out from what it runs.

In-repo code ships under the package's license, so its entries carry none.
"""

from __future__ import annotations

import ast
import functools
import importlib.metadata
import importlib.resources as ir
import re
import sys
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from hpc_oda_commons.benchmark.leaderboard_display import format_target_label
from hpc_oda_commons.benchmark.recipes import load_recipe
from hpc_oda_commons.datasets.descriptor import TARGET_DOMAINS, load_descriptor

REGISTRY_SCHEMA_VERSION = "oda.registry.v0.2.0"
_PACKAGE = "hpc_oda_commons"
_DISTRIBUTION = "hpc-oda-commons"
# Model packages whose imports a model inherits: the shared bases under ``models/``.
_SHARED_MODEL_MODULES = f"{_PACKAGE}.models."


def _package_root() -> Path:
    return Path(str(ir.files(_PACKAGE)))


def _relative(path: Path) -> str:
    """A packaged file's path as the registry records it (``hpc_oda_commons/...``)."""
    return path.relative_to(_package_root().parent).as_posix()


# --- dependencies, from imports -------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _module_files(module: str) -> list[Path]:
    """The source files of an in-package module or package, if it is one."""
    parts = module.split(".")[1:]
    base = _package_root().joinpath(*parts)
    if base.is_dir():
        return sorted(base.rglob("*.py"))
    file = base.with_suffix(".py")
    return [file] if file.is_file() else []


def _third_party_imports(package_dir: Path) -> set[str]:
    """Top-level third-party modules a model imports, directly or through the shared bases
    under ``models/`` it builds on."""
    seen: set[str] = set()
    found: set[str] = set()
    queue = sorted(package_dir.rglob("*.py"))
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for module in _imported_modules(path):
            top = module.split(".")[0]
            if top == _PACKAGE:
                if module.startswith(_SHARED_MODEL_MODULES):
                    queue.extend(_module_files(module))
            elif top not in sys.stdlib_module_names and top != "__future__":
                found.add(top)
    return found


@functools.cache
def _requirements() -> dict[str, str]:
    """Each declared requirement by normalized distribution name, with the extras that
    install it when it is optional. Development-only extras are left out."""
    core: dict[str, str] = {}
    optional: dict[str, tuple[str, list[str]]] = {}
    for requirement in importlib.metadata.requires(_DISTRIBUTION) or []:
        spec, _, marker = requirement.partition(";")
        spec = spec.strip()
        key = _normalize(re.split(r"[<>=!~\[ ]", spec, maxsplit=1)[0])
        extra = re.search(r'extra\s*==\s*"([^"]+)"', marker)
        if not extra:
            core[key] = spec
        elif extra.group(1) != "dev":
            optional.setdefault(key, (spec, []))[1].append(extra.group(1))
    out = {key: f"{spec} (extras: {', '.join(extras)})" for key, (spec, extras) in optional.items()}
    out.update(core)
    return out


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _dependencies(package_dir: Path) -> list[str]:
    """The requirement for each third-party module the model imports, or the module's name
    when the package does not declare it (one that comes in with another, such as numpy)."""
    installed = importlib.metadata.packages_distributions()
    requirements = _requirements()
    deps: set[str] = set()
    for module in _third_party_imports(package_dir):
        names = [_normalize(d) for d in installed.get(module) or []] or [
            key for key in requirements if key == _normalize(module) or key.startswith(f"{module}-")
        ]
        declared = [requirements[name] for name in names if name in requirements]
        deps.update(declared or [module])
    return sorted(deps)


# --- entries --------------------------------------------------------------------------------


def _metadata(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = {"name", "version", "object", "description"} - set(payload or {})
    if missing:
        raise ValueError(f"{path} lacks {', '.join(sorted(missing))}")
    return payload


def _bundled_recipes() -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in sorted((_package_root() / "recipes").rglob("*.yml")):
        if "recipe_id" in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}):
            yield path, load_recipe(path)


def _matrix_recipes() -> list[dict[str, Any]]:
    """The recipes the runtime fleet runs, which the HPC matrix generates in code."""
    from hpc_oda_commons.benchmarking.hpc.matrix import RUNTIME_MODELS, build_recipe

    return [build_recipe("dataset", model, "data.parquet", "runs") for model in RUNTIME_MODELS]


def _recipe_targets(recipe: dict[str, Any]) -> list[str]:
    return sorted({str(m["target"]) for m in recipe.get("metrics") or [] if m.get("target")})


def _ordered_domains(domains: Iterable[str]) -> list[str]:
    """Tasks in the order the targets are listed (runtime first), then any others."""
    order = list(dict.fromkeys(TARGET_DOMAINS.values()))
    unique = set(domains)
    return [d for d in order if d in unique] + sorted(unique - set(order))


def _model_entries(recipes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per ``models/<name>/model.yml``. ``recipes`` is every recipe the package
    runs: the bundled files and the ones the HPC matrix generates."""
    entries = []
    for meta_path in sorted((_package_root() / "models").glob("*/model.yml")):
        meta = _metadata(meta_path)
        name = meta_path.parent.name
        model_id = f"model.{name}"
        runs = [r for r in recipes if (r.get("model") or {}).get("id") == model_id]
        if not runs:
            raise ValueError(f"{model_id} has no bundled recipe, so its tasks are unknown")
        domains = _ordered_domains(d for r in runs for d in r.get("problem_domain") or [])
        inputs = sorted({str(r.get("schema_version")) for r in runs})
        entry: dict[str, Any] = {
            "id": model_id,
            "entry_type": "model",
            "name": meta["name"],
            "version": str(meta["version"]),
            "description": " ".join(str(meta["description"]).split()),
            "problem_domain": domains,
            "input_schema_version": inputs[-1],
            "tags": sorted({t for r in runs for t in _recipe_targets(r)}),
            "reference": {
                "kind": "python",
                "python": {
                    "module": f"{_PACKAGE}.models.{name}.model",
                    "object": meta["object"],
                },
            },
        }
        deps = _dependencies(meta_path.parent)
        if deps:
            entry["dependencies"] = deps
        entries.append(entry)
    return entries


def _adapter_entries() -> list[dict[str, Any]]:
    entries = []
    for meta_path in sorted((_package_root() / "adapters").glob("*/adapter.yml")):
        meta = _metadata(meta_path)
        name = meta_path.parent.name
        entries.append(
            {
                "id": f"adapter.{name}",
                "entry_type": "adapter",
                "name": meta["name"],
                "version": str(meta["version"]),
                "description": " ".join(str(meta["description"]).split()),
                "problem_domain": list(meta["problem_domain"]),
                "supported_sources": list(meta["supported_sources"]),
                "output_schema_version": meta["output_schema_version"],
                "reference": {
                    "kind": "python",
                    "python": {
                        "module": f"{_PACKAGE}.adapters.{name}.adapter",
                        "object": meta["object"],
                    },
                },
            }
        )
    return entries


def _dataset_entries() -> list[dict[str, Any]]:
    entries = []
    for path in sorted((_package_root() / "datasets" / "descriptors").glob("*.yml")):
        descriptor = load_descriptor(path)
        entry: dict[str, Any] = {
            "id": descriptor.dataset_id,
            "entry_type": "dataset",
            "name": descriptor.name,
            "version": descriptor.version,
            "description": " ".join(descriptor.description.split()),
            "problem_domain": list(descriptor.problem_domains),
            "output_schema_version": descriptor.targets[0].schema,
            "tags": list(descriptor.tags),
            "reference": {"kind": "path", "path": _relative(path)},
        }
        spdx = (descriptor.license or {}).get("spdx")
        if spdx:
            entry["license"] = str(spdx)
        entries.append(entry)
    return entries


def _recipe_entry(path: Path, recipe: dict[str, Any], titles: dict[str, str]) -> dict[str, Any]:
    model_id = str((recipe.get("model") or {}).get("id", ""))
    model = titles.get(model_id, model_id)
    dataset = str((recipe.get("dataset") or {}).get("id", ""))
    targets = _recipe_targets(recipe)
    target_text = " and ".join(format_target_label(t) for t in targets) or "its target"
    method = str((recipe.get("split") or {}).get("method", "fixed"))
    return {
        "id": str(recipe["recipe_id"]),
        "entry_type": "recipe",
        "name": f"{model} on {dataset}, {target_text}"[:120],
        "description": (
            f"Runs {model} ({model_id}) on {dataset}, predicting {target_text}, "
            f"with a {method} split."
        ),
        "problem_domain": list(recipe.get("problem_domain") or []),
        "input_schema_version": str(recipe.get("schema_version")),
        "tags": sorted({method, *targets}),
        "reference": {"kind": "path", "path": _relative(path)},
    }


@functools.cache
def build_registry_payload() -> dict[str, Any]:
    """The registry snapshot, as ``oda.registry.v0.2.0`` JSON, built from the sources."""
    recipes = list(_bundled_recipes())
    models = _model_entries([r for _, r in recipes] + _matrix_recipes())
    titles = {entry["id"]: entry["name"] for entry in models}
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "built from the package's model, adapter, descriptor and recipe files",
        "entries": [
            *_adapter_entries(),
            *models,
            *(_recipe_entry(path, recipe, titles) for path, recipe in recipes),
            *_dataset_entries(),
        ],
    }
