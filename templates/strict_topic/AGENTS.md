# AGENTS.md (Strict Research Mode)

This project runs in strict, policy-first mode.

## Project Goal

Build an auditable research extraction workbook with zero unapproved structural drift.

## Non-Negotiable Rules

1. Default mode is `CONTENT-ONLY`.
2. Do not add, remove, reorder, or rename columns unless user writes exact phrase: `STRUCTURE CHANGE APPROVED`.
3. Do not rename sheets unless user writes exact phrase: `STRUCTURE CHANGE APPROVED`.
4. Do not move or copy rows across sheets unless user explicitly asks for that action in the current turn.
5. Protected sheets are isolated. Rows from protected sheets cannot be copied into other sheets unless explicitly approved.
6. Run this project inside the disposable Docker VM launcher by default.
7. Do not require nested Docker inside the already-containerized session.
8. If the disposable Docker VM is unavailable, stop and report that blocker. Do not run alternative local fallback commands.
9. Mandatory multi-agent workflow for complex tasks:
- `Extractor`
- `Verifier`
- `Adjudicator`
10. Mandatory QA rounds before completion: `3`.
11. Mandatory saved-file verification before completion: run `python3 scripts/verify_saved_workbook_state.py` against the saved workbook after writing and report the actual non-empty row count and identifiers from the saved file.
12. If any QA round fails, or if saved-file verification fails, run status is `FAILED` and no completion message is allowed.

## Output Contract

Before writing files, provide:

1. Exact sheets to change.
2. Exact columns to change.
3. Expected row delta per sheet.
4. Whether change is content-only or structural.

After writing files, provide:

1. Actual row delta per sheet.
2. Added/removed identifiers.
3. QA round 1/2/3 results.
4. Saved-file verification result from the workbook on disk.
5. Policy compliance result.

## Stop Conditions

Stop and ask user before proceeding if any of these occur:

1. Missing required headers.
2. Protected-sheet isolation conflict.
3. Ambiguous user instruction that could imply structural change.
4. Disposable Docker VM unavailable.
