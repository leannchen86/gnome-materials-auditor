"""Small MLIP audit pilot for structure relaxation provenance.

The goal is not to turn MLIP output into ground truth. This module creates a
compact, reproducible record of what a learned interatomic potential did to an
input structure, so the result can later be compared against classical checks,
DFT, experiments, or other MLIPs.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.core import Lattice, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from gnome_auditor.config import DATA_DIR, EXTRACTED_CIFS_DIR


DEFAULT_OUTPUT = DATA_DIR / "mlip_audit" / "results.jsonl"
_CHGNET_MODEL = None
_CHGNET_RELAXER = None


@dataclass(frozen=True)
class AuditInput:
    """A structure plus enough source metadata to make the run traceable."""

    material_id: str
    structure: Structure
    source_kind: str
    source_path: str | None = None


def _package_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _space_group(structure: Structure) -> dict[str, Any]:
    try:
        sga = SpacegroupAnalyzer(structure, symprec=0.1)
        return {
            "number": sga.get_space_group_number(),
            "symbol": sga.get_space_group_symbol(),
            "crystal_system": sga.get_crystal_system(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _structure_facts(structure: Structure) -> dict[str, Any]:
    return {
        "formula": structure.composition.reduced_formula,
        "composition": structure.composition.formula,
        "n_sites": len(structure),
        "volume_ang3": structure.volume,
        "density_g_cm3": structure.density,
        "space_group": _space_group(structure),
    }


def _max_force(forces: Any) -> float | None:
    if forces is None:
        return None
    arr = np.asarray(forces, dtype=float)
    if arr.size == 0:
        return None
    if arr.ndim == 1:
        return float(np.max(np.abs(arr)))
    return float(np.max(np.linalg.norm(arr, axis=1)))


def _rms_displacement(initial: Structure, final: Structure) -> float | None:
    try:
        matcher = StructureMatcher(primitive_cell=False, scale=True, attempt_supercell=False)
        rms = matcher.get_rms_dist(initial, final)
        if rms is None:
            return None
        if isinstance(rms, tuple):
            return float(rms[0])
        return float(rms)
    except Exception:
        return None


def _demo_inputs() -> list[AuditInput]:
    """Small oxide examples that run quickly on CPU."""
    srtio3 = Structure(
        Lattice.cubic(3.905),
        ["Sr", "Ti", "O", "O", "O"],
        [
            [0.0, 0.0, 0.0],
            [0.5, 0.5, 0.5],
            [0.5, 0.5, 0.0],
            [0.5, 0.0, 0.5],
            [0.0, 0.5, 0.5],
        ],
    )
    mgo = Structure(
        Lattice.cubic(4.212),
        ["Mg", "Mg", "Mg", "Mg", "O", "O", "O", "O"],
        [
            [0.0, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.5, 0.0, 0.5],
            [0.0, 0.5, 0.5],
            [0.5, 0.5, 0.5],
            [0.5, 0.0, 0.0],
            [0.0, 0.5, 0.0],
            [0.0, 0.0, 0.5],
        ],
    )
    return [
        AuditInput("demo-SrTiO3-cubic", srtio3, "demo"),
        AuditInput("demo-MgO-rocksalt", mgo, "demo"),
    ]


def _load_cif(path: Path) -> AuditInput:
    structure = Structure.from_file(str(path))
    return AuditInput(path.stem, structure, "cif", str(path))


def collect_inputs(args: argparse.Namespace) -> list[AuditInput]:
    inputs: list[AuditInput] = []
    if args.demo:
        inputs.extend(_demo_inputs())

    for path_str in args.cif or []:
        inputs.append(_load_cif(Path(path_str)))

    if args.cif_dir:
        cif_dir = Path(args.cif_dir)
        for path in sorted(cif_dir.glob("*.cif")):
            inputs.append(_load_cif(path))

    if args.material_id:
        for material_id in args.material_id:
            path = EXTRACTED_CIFS_DIR / f"{material_id}.cif"
            inputs.append(_load_cif(path))

    if args.limit is not None:
        inputs = inputs[: args.limit]
    return inputs


def _base_record(audit_input: AuditInput, backend: str, max_steps: int, fmax: float) -> dict[str, Any]:
    return {
        "schema_version": "mlip-audit.v0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "material_id": audit_input.material_id,
        "source": {
            "kind": audit_input.source_kind,
            "path": audit_input.source_path,
        },
        "input": _structure_facts(audit_input.structure),
        "backend": {
            "name": backend,
            "max_steps": max_steps,
            "fmax_ev_ang": fmax,
            "packages": {
                "pymatgen": _package_version("pymatgen"),
                "chgnet": _package_version("chgnet"),
                "torch": _package_version("torch"),
            },
        },
    }


def dry_run(audit_input: AuditInput, *, backend: str, max_steps: int, fmax: float) -> dict[str, Any]:
    record = _base_record(audit_input, backend, max_steps, fmax)
    record["relaxation"] = {
        "status": "dry_run",
        "note": "No MLIP was executed; this record validates input parsing and output schema.",
    }
    return record


def chgnet_relax(audit_input: AuditInput, *, max_steps: int, fmax: float) -> dict[str, Any]:
    record = _base_record(audit_input, "chgnet", max_steps, fmax)
    started = time.perf_counter()
    try:
        model, relaxer = _get_chgnet_runner()
        prediction = model.predict_structure(audit_input.structure)
        result = relaxer.relax(
            audit_input.structure,
            fmax=fmax,
            steps=max_steps,
            verbose=False,
        )
        final_structure = result["final_structure"]
        trajectory = result.get("trajectory")

        energies = getattr(trajectory, "energies", None)
        forces = getattr(trajectory, "forces", None)
        initial_energy_per_atom = _scalar_prediction(prediction, "e")
        initial_energy = _total_energy(initial_energy_per_atom, len(audit_input.structure))
        final_energy = float(energies[-1]) if energies else None
        final_energy_per_atom = _per_atom(final_energy, len(final_structure))
        final_forces = forces[-1] if forces else _prediction_value(prediction, "f")
        initial_sg = record["input"]["space_group"]
        final_sg = _space_group(final_structure)

        record["relaxation"] = {
            "status": "completed",
            "elapsed_s": time.perf_counter() - started,
            "n_steps": len(energies) if energies else None,
            "initial_energy_ev": initial_energy,
            "final_energy_ev": final_energy,
            "initial_energy_ev_atom": initial_energy_per_atom,
            "final_energy_ev_atom": final_energy_per_atom,
            "energy_delta_ev_atom": _difference(final_energy_per_atom, initial_energy_per_atom),
            "final_max_force_ev_ang": _max_force(final_forces),
            "initial_volume_ang3": audit_input.structure.volume,
            "final_volume_ang3": final_structure.volume,
            "volume_delta_pct": _percent_delta(
                audit_input.structure.volume,
                final_structure.volume,
            ),
            "initial_space_group": initial_sg,
            "final_space_group": final_sg,
            "space_group_changed": _space_group_changed(initial_sg, final_sg),
            "rms_displacement_ang": _rms_displacement(audit_input.structure, final_structure),
        }
        record["final_structure"] = {
            "formula": final_structure.composition.reduced_formula,
            "n_sites": len(final_structure),
        }
    except Exception as exc:
        record["relaxation"] = {
            "status": "error",
            "elapsed_s": time.perf_counter() - started,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    return record


def _get_chgnet_runner() -> tuple[Any, Any]:
    global _CHGNET_MODEL, _CHGNET_RELAXER
    if _CHGNET_MODEL is None or _CHGNET_RELAXER is None:
        from chgnet.model.dynamics import StructOptimizer
        from chgnet.model.model import CHGNet

        _CHGNET_MODEL = CHGNet.load()
        _CHGNET_RELAXER = StructOptimizer(model=_CHGNET_MODEL)
    return _CHGNET_MODEL, _CHGNET_RELAXER


def _prediction_value(prediction: Any, key: str) -> Any:
    if isinstance(prediction, dict):
        return prediction.get(key)
    return getattr(prediction, key, None)


def _scalar_prediction(prediction: Any, key: str) -> float | None:
    value = _prediction_value(prediction, key)
    if value is None:
        return None
    arr = np.asarray(value)
    if arr.size == 0:
        return None
    return float(arr.reshape(-1)[0])


def _per_atom(energy: float | None, n_sites: int) -> float | None:
    if energy is None or n_sites == 0:
        return None
    return energy / n_sites


def _total_energy(energy_per_atom: float | None, n_sites: int) -> float | None:
    if energy_per_atom is None:
        return None
    return energy_per_atom * n_sites


def _difference(final: float | None, initial: float | None) -> float | None:
    if final is None or initial is None:
        return None
    return final - initial


def _percent_delta(initial: float, final: float) -> float | None:
    if initial == 0:
        return None
    return (final - initial) / initial * 100.0


def _space_group_changed(initial: dict[str, Any], final: dict[str, Any]) -> bool | None:
    initial_number = initial.get("number")
    final_number = final.get("number")
    if initial_number is None or final_number is None:
        return None
    return initial_number != final_number


def run_audit(args: argparse.Namespace) -> list[dict[str, Any]]:
    inputs = collect_inputs(args)
    if not inputs:
        raise ValueError("No structures found. Use --demo, --cif, --cif-dir, or --material-id.")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    with output_path.open("w", encoding="utf-8") as handle:
        for audit_input in inputs:
            if args.backend == "chgnet":
                record = chgnet_relax(audit_input, max_steps=args.max_steps, fmax=args.fmax)
            else:
                record = dry_run(
                    audit_input,
                    backend=args.backend,
                    max_steps=args.max_steps,
                    fmax=args.fmax,
                )
            records.append(record)
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return records


def print_summary(records: list[dict[str, Any]], output: Path) -> None:
    counts: dict[str, int] = {}
    for record in records:
        status = record.get("relaxation", {}).get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    print(f"MLIP audit wrote {len(records)} records to {output}")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")

    for record in records[:5]:
        relaxation = record.get("relaxation", {})
        line = f"  {record['material_id']}: {relaxation.get('status')}"
        delta = relaxation.get("energy_delta_ev_atom")
        volume_delta = relaxation.get("volume_delta_pct")
        sg_changed = relaxation.get("space_group_changed")
        if delta is not None:
            line += f", dE/atom={delta:.5f} eV"
        if volume_delta is not None:
            line += f", dV={volume_delta:.2f}%"
        if sg_changed is not None:
            line += f", sg_changed={sg_changed}"
        print(line)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backend",
        choices=("dry-run", "chgnet"),
        default="dry-run",
        help="Potential backend to run. dry-run only validates the schema.",
    )
    parser.add_argument("--demo", action="store_true", help="Run two tiny built-in oxide examples.")
    parser.add_argument("--cif", action="append", help="Path to a CIF file. Can be passed multiple times.")
    parser.add_argument("--cif-dir", help="Directory of CIF files to audit.")
    parser.add_argument(
        "--material-id",
        action="append",
        help="Material ID whose CIF exists in data/extracted_cifs. Can be passed multiple times.",
    )
    parser.add_argument("--limit", type=int, help="Limit the number of structures processed.")
    parser.add_argument("--max-steps", type=int, default=25, help="Maximum relaxation steps.")
    parser.add_argument("--fmax", type=float, default=0.08, help="Relaxation force threshold in eV/A.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path.")


def main(args: argparse.Namespace) -> None:
    records = run_audit(args)
    print_summary(records, Path(args.output))
