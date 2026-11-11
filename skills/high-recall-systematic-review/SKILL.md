---
name: high-recall-systematic-review
description: Use this when starting or running a rigorous systematic review, evidence map, or academic extraction where missing important papers would be costly; enforces disposable Docker VM execution, high-recall search design, domain coverage, latest-review/supersession checks, benchmark recall, multi-agent retrieval, and saved-file verification.
---

# High-Recall Systematic Review

Use this skill for systematic reviews, evidence maps, or broad literature searches where recall matters more than speed.

## Core Rule

Do not treat a useful-looking list of papers as success. Success requires domain coverage, latest-review checks, benchmark recall, audit artifacts, and saved-file verification.

## Default Workflow

Use the strict project template stored at:

`/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/templates/strict_topic`

Use the helper scripts stored at:

`/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/scripts`

For a new project:

1. Initialize the strict workspace with `init_strict_topic_workspace.sh`.
2. Fill `policy/pipeline_policy.yaml` and `prompts/task_request_template.md`.
3. Validate setup with `validate_strict_project_setup.py`.
4. Create the workbook with the project-local `scripts/create_workbook_template.sh`.
5. Launch in disposable Docker dangerous mode with `launch_strict_project_vm.sh --high-recall`.
6. After completion, run `finalize_strict_project_run.sh --high-recall`.

## Required High-Recall Artifacts

The run must create and pass validation for:

1. `reports/domain_coverage_matrix.csv`
2. `reports/review_supersession_audit.csv`
3. `reports/benchmark_recall_set.csv`
4. `reports/benchmark_recall_results.csv`
5. `reports/coverage_audit.csv`
6. `reports/final_gap_analysis.md`

Run validation with:

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/validate_high_recall_reports.py --project "/absolute/path/to/project"
```

## Agent Roles

Use agents only where they add recall or verification value:

1. `Search Architect`: domain map, synonyms, query families, sentinel set.
2. `Retriever`: broad and narrow retrieval passes.
3. `Coverage Challenger`: missed-paper search, expert-list reconciliation, major-author checks, newer-review checks.
4. `Verifier`: PMID/title/link/excerpt correctness, dedupe integrity, latest-review/supersession claims.
5. `Adjudicator`: resolves uncertain inclusion/exclusion/supersession decisions.

Keep workbook writing, sync-back, and saved-file checks deterministic through scripts.

## Fail-Closed Conditions

Stop and report failure if:

1. a major domain is absent from `domain_coverage_matrix.csv`
2. a latest-review/supersession check is incomplete
3. a benchmark paper is not retrieved
4. a known important paper is missing without failure mode and action
5. `final_gap_analysis.md` contains unresolved/TBD/pending language
6. saved-file verification fails inside the VM or after sync-back

## Preferred Launch Command

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/launch_strict_project_vm.sh "/absolute/path/to/project" --high-recall
```

## Preferred Finish Command

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/finalize_strict_project_run.sh "/absolute/path/to/project" --high-recall
```
