Topic: `TOPIC_NAME`

Objective:
`ONE SENTENCE ON WHAT MUST CHANGE`

Scope:

1. Sheets allowed to edit: `SHEET_A, SHEET_B`
2. Columns allowed to edit: `COLUMN_1, COLUMN_2, COLUMN_3`
3. Protected sheets: `None`
4. Explicitly disallowed changes:
- no new columns
- no column reordering
- no sheet rename
- no cross-sheet row copy/move

Execution constraints:

1. Disposable Docker VM required: `YES`
2. Multi-agent required: `YES`
3. QA rounds required: `3`
4. Nested Docker inside the session: `NO`
5. No fallback path if the disposable Docker VM is unavailable: `YES`
6. Saved-file verification required before completion: `YES`

Completion definition:

1. Policy pass: `REQUIRED`
2. QA 1/2/3 pass: `REQUIRED`
3. Saved workbook reopened from disk and verified: `REQUIRED`
4. Report files written: `REQUIRED`
