# AE Psychosis Review Pipeline

## What this does
- Runs staged workflow: retrieval -> metadata QA -> abstract/verbatim QA.
- Preserves source workbook by default (writes `*_output.xlsx`).
- Produces machine-readable reports under `reports/`.
- Automatically separates low-confidence inclusions into `Low Confidence Items`.
- Keeps `Low Confidence Items` formatting synced to the main sheet (column widths, wrapped text, hyperlink styling).
- Adds `Submitted Reference Inventory` when `--submitted-list` is provided.
  - Includes every submitted item (URLs/PMIDs/PMCID lines).
  - Uses a compact 20-column schema (no redundant internal QA columns).
  - Labels `Research Item (Y/N)` with a reason when not research.
  - Adds `Included in Database (Y/N)` and `If Not Included, Why Not`.
  - Fills non-matched fields with explicit text (no blank/`NR` placeholders).
  - Runs 3 internal QA checks on the inventory tab:
    - completeness (`items == written rows`)
    - inclusion consistency (`Y/N` decision vs rationale text)
    - cleanliness/link checks (no blank/`NR`, URL formatting + hyperlink)

## Master prompt
- `prompts/ae_systematic_review_master_prompt.md`

## Run in Docker
```bash
./scripts/run_pipeline_in_container.sh "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis" \
  --input "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary.xlsx" \
  --output "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary_output.xlsx" \
  --reports-dir "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/reports" \
  --email "your-email@example.com"
```

## Additional submitted-list QA (your new requested step)
Create a text file with your submitted list (URLs and/or PMIDs), then run:
```bash
./scripts/run_pipeline_in_container.sh "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis" \
  --input "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary.xlsx" \
  --output "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary_output.xlsx" \
  --reports-dir "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/reports" \
  --submitted-list "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/submitted_reference_list.txt" \
  --skip-retrieval
```

This adds:
- Primary-sheet column: `In Submitted List (Y/N)`
- Primary-sheet column: `Additional Papers Beyond Submitted List`
- New QA sheet: `Submitted_List_QA`
- Report: `reports/submitted_list_qa.csv`

## Simple mode (main sheet only)
If you want only the original/main sheet updated (no extra QA sheets/reports):
```bash
./scripts/run_pipeline_in_container.sh "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis" \
  --input "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary.xlsx" \
  --output "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary_output.xlsx" \
  --submitted-list "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/submitted_reference_list.txt" \
  --simple-output
```

Simple mode still:
- runs retrieval
- adds working links to `PubMed URL`
- adds `Direct Paper URL` (PMC/DOI/PubMed fallback)
- fills `Findings` and missing `Description` with explicit `NR` text

## Run Codex in disposable sandbox (recommended for dangerous mode)
This creates a throwaway workspace copy in `/tmp` and runs Codex there:
```bash
./scripts/run_codex_vm_disposable.sh "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis"
```

Pass extra Codex args after the source path:
```bash
./scripts/run_codex_vm_disposable.sh "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis" --version
```

Notes:
- Dangerous mode is still enabled, but only inside Docker against the disposable copy.
- The script prints the sandbox path so you can inspect or delete it after the session.

## QA-only mode
```bash
./scripts/run_pipeline_in_container.sh "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis" \
  --input "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary.xlsx" \
  --output "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary_output.xlsx" \
  --reports-dir "/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/reports" \
  --skip-retrieval
```

## Notes
- PMID extraction explicitly avoids DOI-to-PMID misparsing.
- Off-by-one PMID sentinel is included in metadata QA.
- PubMed URL normalization is enforced as `https://pubmed.ncbi.nlm.nih.gov/{PMID}/`.
- Submitted-list parser accepts mixed text containing URLs and PMIDs.
- Header order can be rearranged; required columns are `Title`, `ID`, and `PubMed URL`.

## Strict template for new topics
To bootstrap a new topic workspace with strict guardrails (no unapproved structural edits, Docker-only, mandatory multi-agent + QA x3):

```bash
./scripts/init_strict_topic_workspace.sh "/absolute/path/to/new-topic-project"
```

Then use:

1. `AGENTS.md` in the new project root.
2. `policy/pipeline_policy.yaml` for hard constraints.
3. `python3 ./scripts/validate_strict_project_setup.py --project "/absolute/path/to/new-topic-project"` to catch placeholders or missing setup before launch.
4. `"/absolute/path/to/new-topic-project/scripts/create_workbook_template.sh" "/absolute/path/to/new-topic-project"` to create the starter workbook from the policy path + task-template headers.
5. `./scripts/launch_strict_project_vm.sh "/absolute/path/to/new-topic-project"` to:
   - copy the startup prompt to your clipboard
   - also write the startup prompt to `.codex-startup-prompt.md` in the project root
   - open Codex in dangerous mode inside the disposable Docker VM
   - refuse to start if the workbook file does not exist yet
6. Paste the clipboard contents into that new session, or paste from `.codex-startup-prompt.md` if needed.
7. After the run, either:
   - sync manually: `./scripts/sync_project_from_latest_sandbox.sh "/absolute/path/to/new-topic-project"`
   - or sync + verify in one step: `./scripts/finalize_strict_project_run.sh "/absolute/path/to/new-topic-project"`
   - for high-recall runs, sync + verify + validate reports: `./scripts/finalize_strict_project_run.sh "/absolute/path/to/new-topic-project" --high-recall`
8. Verify the saved workbook on disk before trusting the completion message if you did not use the combined finalize step:
   `python3 ./scripts/verify_saved_workbook_state.py --workbook "/absolute/path/to/workbook.xlsx" --sheet "Main extraction spreadsheet" --id-column "PMID"`

New strict-topic workspaces now use headers on row `1`. For older workbooks built with the previous template, pass `--header-row 3`.

The launcher writes `.codex-last-sandbox-path` into the real project folder so the sync helper can pull from the correct sandbox automatically.

For systematic reviews or any run where recall/comprehensiveness is critical, the strict template now also includes:

1. `HIGH_RECALL_SYSTEMATIC_REVIEW_WORKFLOW.md`
2. `prompts/high_recall_addendum.md`
3. `checklists/high_recall_coverage_checklist.md`

Use those to force:

1. sentinel-paper recovery
2. multiple query families
3. expert-list and prior-review reconciliation
4. citation chasing
5. coverage audit artifacts in `reports/`
6. final gap analysis before claiming the search is comprehensive

If the project is high-recall, launch with:

```bash
./scripts/launch_strict_project_vm.sh "/absolute/path/to/new-topic-project" --high-recall
```

That flag adds `prompts/high_recall_addendum.md` to the copied startup prompt automatically.
