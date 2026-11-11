Read `AGENTS.md` and `policy/pipeline_policy.yaml` first and obey them exactly.

Run in strict content mode with these hard constraints:

1. No column or sheet structure changes unless I type: `STRUCTURE CHANGE APPROVED`.
2. Do not move/copy rows across sheets unless I explicitly request it in this turn.
3. Treat protected sheets as isolated.
4. This run must occur inside the disposable Docker VM launched for this project. Do not require nested Docker inside the session.
5. No fallback paths. If the disposable Docker VM is unavailable, stop and report that blocker.
6. Use mandatory multi-agent workflow (`Extractor`, `Verifier`, `Adjudicator`).
7. Run QA for 3 rounds before completion.
8. After any write, run `python3 scripts/verify_saved_workbook_state.py` against the saved workbook on disk and verify the actual row count and identifiers from the file itself before claiming success.
9. If any QA fails or saved-file verification fails, stop and report failures only.

Before writing any file, provide:

1. Exact sheets to change.
2. Exact columns to change.
3. Expected row delta by sheet.
4. Content-only vs structural classification.

After writing, provide:

1. Actual row delta by sheet.
2. Added/removed IDs.
3. QA round results (1, 2, 3).
4. Saved-file verification result from the workbook on disk.
5. Policy compliance status.
