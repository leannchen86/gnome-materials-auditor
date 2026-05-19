# Materials Dataset Hygiene Plan

## Thesis

Materials AI does not need another vague uncertainty signal as the first
contribution. It needs boring infrastructure that makes datasets, benchmarks,
and generated-candidate claims easier to trust.

The useful claim should be deterministic whenever possible:

- this row is duplicated
- this formula cannot be parsed
- this material ID conflicts with another row
- this structure matches an existing reference
- this benchmark split overlaps a training corpus
- this generated candidate relaxes into a known prototype
- this label disagrees with a public reference

Probabilistic model disagreement can stay as a side signal, but it should not be
the center of the project until it is calibrated against a decision that experts
actually care about.

## Product Shape

Build a small, composable audit toolkit for materials datasets:

1. **Row Hygiene**
   - missing IDs
   - duplicate IDs
   - missing or unparsable formulas
   - suspicious `n_sites`, volume, or energy fields

2. **Reference Reconciliation**
   - compare candidate rows against MP, WBM, GNoME, Alexandria, OQMD, or local
     reference tables
   - report exact composition matches, same reduced formula, and eventually
     StructureMatcher/prototype matches

3. **Benchmark Integrity**
   - detect train/test overlap by material ID, formula, prototype, and
     structure match
   - surface likely leakage cases in benchmark splits

4. **Failure-Case Catalogs**
   - collect deterministic failure modes from public references
   - group them by chemistry, prototype, symmetry change, relaxation change, and
     label conflict

## First MVP

Start with row-level checks because they are deterministic, cheap, and useful
for any CSV-like dataset.

Input:

```bash
python -m gnome_auditor.cli dataset-audit --csv path/to/materials.csv
```

Output:

- JSONL issue records
- counts by issue code and severity
- stable row indices and material IDs for reproducibility

## Decision Rules

Keep building this direction if the tool can produce outputs that are:

- deterministic
- easy to verify manually
- tied to dataset/benchmark trust
- boring enough that teams might not prioritize building it themselves

Pause or pivot if the work becomes mostly interpretive ranking without a clear
ground-truth or workflow action.

## Near-Term Backlog

- Add row hygiene checks for CSV datasets.
- Add exact formula/reference overlap audit.
- Add `pymatgen.StructureMatcher` comparison for local CIF/JSON structure sets.
- Add WBM/Matbench Discovery overlap report.
- Add benchmark split leakage report.
- Add compact HTML/CSV reports once the issue schema stabilizes.

