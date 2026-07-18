# GNoME Materials Auditor

Audit and explore candidate materials from DeepMind's GNoME predictions with chemistry validators, Materials Project cross-references, and Claude-generated research questions.

The interactive frontend is called **Curious Materials**. It helps researchers triage GNoME candidates by surfacing validation red flags, chemical-family context, and targeted follow-up questions, so they can focus on what to synthesize next instead of sifting through raw prediction tables.

This repo combines traditional chemistry checks with Claude-assisted question generation. In the current run, Claude Opus 4.6 reviewed 3,262 materials and 68 parallel Claude Code subagents generated 1,700 research questions at scale.

## Quick Start

```bash
python3 -m http.server 8080 --directory interface
```

Open `http://localhost:8080` in your browser and go to the Materials tab.

## What The Auditor Checks

For each material, the pipeline first runs these validation checks:

| Validator | What it checks | Tier |
|-----------|---------------|------|
| Charge Neutrality | Oxidation states sum to zero | 1 (DFT-independent) |
| Shannon Radii | Bond lengths match expected ionic radii | 1 |
| Pauling Rule 2 | Electrostatic valence around O sites | 1 |
| Bond Valence Sum (GII) | Global bond strain | 2 (uses DFT geometry) |
| Space Group | Matches experimental databases | 2 |

Then Claude reviews each material, its validation results, and its **related materials** to generate a targeted research question.

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

## License

Apache 2.0 (code). GNoME data under CC BY-NC 4.0 per [Google's terms](https://creativecommons.org/licenses/by-nc/4.0/).

Built for the Anthropic Claude Code Hackathon, February 2025.
