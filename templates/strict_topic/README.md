# Strict Topic Workspace Template

Use this template to start any new evidence-extraction project with hard guardrails.

## Quick Start

1. Run:
```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/init_strict_topic_workspace.sh "/absolute/path/to/new-topic-project"
```
2. Open and edit:
- `policy/pipeline_policy.yaml`
- `prompts/task_request_template.md`
3. Validate the setup:
```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/validate_strict_project_setup.py --project "/absolute/path/to/new-topic-project"
```
4. Create the workbook from those settings:
```bash
"/absolute/path/to/new-topic-project/scripts/create_workbook_template.sh" "/absolute/path/to/new-topic-project"
```
5. Launch the dangerous-mode disposable session:
```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/launch_strict_project_vm.sh "/absolute/path/to/new-topic-project"
```
6. Paste the clipboard contents into the new session.

If the project is a systematic review or any high-recall evidence search, also use:

- `HIGH_RECALL_SYSTEMATIC_REVIEW_WORKFLOW.md`
- `prompts/high_recall_addendum.md`
- `checklists/high_recall_coverage_checklist.md`

## What This Template Enforces

1. No schema edits without explicit approval.
2. Disposable Docker VM execution by default.
3. No fallback paths when Docker permission is rejected.
4. Mandatory multi-agent workflow.
5. Mandatory QA x3 before completion.
6. Mandatory saved-file verification before completion.
7. Preflight and postflight delta reporting.

## You Must Customize These Fields

1. `project.topic_name` in `policy/pipeline_policy.yaml`
2. `project.workbook_path` in `policy/pipeline_policy.yaml`
3. `Sheets allowed to edit` in `prompts/task_request_template.md`
4. `Columns allowed to edit` in `prompts/task_request_template.md`
5. `Protected sheets` in `prompts/task_request_template.md`

## Recommended launch

For this template, use the disposable dangerous-mode launcher rather than the normal app chat:

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/launch_strict_project_vm.sh "/absolute/path/to/new-topic-project"
```

This launcher:

1. copies the startup prompt to your clipboard
2. writes the same startup prompt to `.codex-startup-prompt.md` in the project root
3. copies your existing Codex auth into the disposable home automatically
4. refuses to launch until the workbook file in `policy/pipeline_policy.yaml` actually exists

## Sync results back

After the run finishes, sync the disposable sandbox back into the real project with:

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/sync_project_from_latest_sandbox.sh "/absolute/path/to/new-topic-project"
```

The launcher records the most recent sandbox path in `.codex-last-sandbox-path` inside the real project folder, and the sync helper uses that automatically.

Then verify the saved workbook on disk with:

```bash
python3 "./scripts/verify_saved_workbook_state.py" --workbook "/absolute/path/to/workbook.xlsx" --sheet "Main extraction spreadsheet" --id-column "PMID"
```

For older workbooks that still use headers on row `3`, add:

```bash
--header-row 3
```

## Workbook helper

The template includes a workbook generator:

```bash
"/absolute/path/to/new-topic-project/scripts/create_workbook_template.sh" "/absolute/path/to/new-topic-project"
```

It reads:

1. `policy/pipeline_policy.yaml` for `workbook_path`
2. `prompts/task_request_template.md` for the first allowed sheet name and the allowed column headers

It writes those headers to row 1 of a new `.xlsx` file so the sheet opens in a normal spreadsheet layout.

## Validation helper

Before launch, you can validate the setup explicitly:

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/validate_strict_project_setup.py --project "/absolute/path/to/new-topic-project"
```

After the run, you can sync and verify in one step:

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/finalize_strict_project_run.sh "/absolute/path/to/new-topic-project"
```

For high-recall projects, use:

```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/finalize_strict_project_run.sh "/absolute/path/to/new-topic-project" --high-recall
```

## High-Recall Review Mode

For systematic reviews or any task where missing important papers would be costly:

1. read `HIGH_RECALL_SYSTEMATIC_REVIEW_WORKFLOW.md`
2. launch with:
```bash
/Users/zeryabmeyer/Documents/Autoimmune\ Encephalitis/scripts/launch_strict_project_vm.sh "/absolute/path/to/new-topic-project" --high-recall
```
3. use `checklists/high_recall_coverage_checklist.md` before accepting the run

Coverage artifacts should go to `reports/` by default. Do not add extra workbook sheets unless structural change is explicitly approved.

High-recall mode now expects, at minimum:

1. `reports/domain_coverage_matrix.csv`
2. `reports/review_supersession_audit.csv`
3. `reports/benchmark_recall_set.csv`
4. `reports/benchmark_recall_results.csv`
5. `reports/coverage_audit.csv`
6. `reports/final_gap_analysis.md`

These artifacts are checked by:

```bash
python3 "/absolute/path/to/new-topic-project/scripts/validate_high_recall_reports.py" --project "/absolute/path/to/new-topic-project"
```
