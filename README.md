# Curious Materials

DeepMind's GNoME neural net predicted 520k new materials. We let Claude Opus 4.6 go over 3k of them and ask the questions that 3k decent grad students would have asked!

**The goal:** amplify researchers' judgment by surfacing the signals that matter — validation red flags, chemical family context, and targeted research questions — so they can focus on what to synthesize next, not on sifting through data. We use Claude's reasoning to spot patterns across related compounds and 68 parallel Claude Code subagents to generate 1,700 research questions at scale.

## Quick Start

```bash
python3 -m http.server 8080 --directory interface
```

Open `http://localhost:8080` in your browser and go to Materials tab

## What Claude Opus 4.6 Asks

For each material we first generate these 5 validations traditionally:

| Validator | What it checks | Tier |
|-----------|---------------|------|
| Charge Neutrality | Oxidation states sum to zero | 1 (DFT-independent) |
| Shannon Radii | Bond lengths match expected ionic radii | 1 |
| Pauling Rule 2 | Electrostatic valence around O sites | 1 |
| Bond Valence Sum (GII) | Global bond strain | 2 (uses DFT geometry) |
| Space Group | Matches experimental databases | 2 |

Then Claude Opus 4.6 goes over each material, looks at these validations and the **related materials**, and ask one really great question.

## Project Structure

```
interface/
  index.html              # Curious Materials frontend
  data.js                 # All 3,262 materials + validation results (13 MB)
gnome_auditor/
  cli.py                  # CLI: python -m gnome_auditor.cli {stats,validate,...}
  pipeline.py             # Validation pipeline orchestration
  export_data.py          # SQLite -> data.js
  opus_questions.py       # Question generation docs + prompt
  analysis.py             # Calibration plots
  validators/             # 6 validators + oxi state assignment
  db/                     # SQLite schema + queries
  data/                   # Ingestion + MP cross-referencing
  gold_data/              # Synth/not-synth reference CSVs (ICSD)
data/
  opus_questions.json     # 1,700 Claude Opus 4.6 research questions
```

## Regenerating Data

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m gnome_auditor.export_data      # Regenerate data.js
python -m gnome_auditor.cli stats        # View pipeline results
python -m gnome_auditor.analysis         # Generate calibration plots
```

## MLIP Audit Pilot

The `mlip-audit` command records lightweight relaxation provenance for CIF
inputs. It treats learned-potential output as a screening signal, not ground
truth.

```bash
source .venv/bin/activate
pip install chgnet                       # optional CHGNet backend
python -m gnome_auditor.cli mlip-audit --demo --backend dry-run
python -m gnome_auditor.cli mlip-audit --demo --backend chgnet --max-steps 10
```

Results are written as JSONL under `data/mlip_audit/`.

## Dataset Hygiene Audit

The `dataset-audit` command is the start of a more deterministic direction:
boring dataset and benchmark hygiene checks for materials tables. It flags
missing IDs, duplicate IDs, unparsable formulas, and invalid numeric fields in a
stable JSONL issue format.

```bash
source .venv/bin/activate
python -m gnome_auditor.cli dataset-audit --csv path/to/materials.csv \
  --output data/dataset_hygiene_issues.jsonl
```

See `docs/dataset-hygiene-plan.md` for the plan and decision rules.

## License

Apache 2.0 (code). GNoME data under CC BY-NC 4.0 per [Google's terms](https://creativecommons.org/licenses/by-nc/4.0/).

Built for the Anthropic Claude Code Hackathon, Feb 2025.
