Apply the high-recall systematic review workflow from `HIGH_RECALL_SYSTEMATIC_REVIEW_WORKFLOW.md`.

Additional mandatory requirements for this run:

1. Use agent roles: `Search Architect`, `Retriever`, `Coverage Challenger`, `Verifier`, `Adjudicator`.
2. Build a domain coverage matrix before main screening.
3. Build a sentinel-paper set before main screening.
4. Include the latest major systematic review or meta-analysis for each domain in the sentinel or benchmark set when available.
5. Use multiple query families rather than one search string.
6. Run an explicit latest-review gate and review supersession audit for each major domain.
7. Reconcile the candidate pool against sentinel papers, benchmark papers, expert-submitted references, prior reviews, and major authors.
8. Run backward and forward citation chasing on included and sentinel papers.
9. Write coverage artifacts to `reports/` unless I explicitly approve new workbook sheets.
10. Do not claim the search is comprehensive until you show the domain coverage matrix, review supersession audit, benchmark recall results, coverage audit, and final gap analysis.
11. Run `python3 scripts/validate_high_recall_reports.py --project .` inside the disposable Docker VM before claiming high-recall completion.
12. After writing the workbook, run saved-file verification inside the disposable Docker VM and then require host-side saved-file verification after sync-back.

Before any write, show:

1. domain coverage plan
2. sentinel-set plan
3. search sources
4. query families
5. review supersession artifacts to be written
6. benchmark recall artifacts to be written

After completion, report:

1. domain coverage status
2. latest-review / supersession status
3. sentinel recovery status
4. benchmark recall status
5. expert-list reconciliation status
6. citation-chasing yield
7. unresolved gaps, if any
8. saved-file verification result
9. high-recall report validation result
