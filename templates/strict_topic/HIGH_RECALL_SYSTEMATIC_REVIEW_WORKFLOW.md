# High-Recall Systematic Review Workflow

Use this workflow when the goal is not just to extract papers, but to be highly confident that important papers were not missed.

This workflow is designed for the strict-topic template and assumes:

1. Codex runs in dangerous mode inside the disposable Docker VM.
2. The real project folder is only updated after sync-back.
3. Structural changes are still blocked by default unless explicitly approved.

## Confidence Goal

We cannot prove with certainty that nothing was missed. We can, however, make omission unlikely by requiring:

1. multiple search routes
2. a sentinel-paper recovery test
3. domain-level coverage checks
4. review recency and supersession checks
5. citation chasing
6. explicit expert-list reconciliation
7. adversarial missed-paper search
8. saved-file verification before completion

Treat the review as incomplete until those steps are documented.

## Dangerous-Mode Docker Rules

Because the run occurs in dangerous mode inside the disposable Docker VM, the workflow must be fail-closed inside the run itself.

1. Do not require nested Docker inside the session.
2. Do not start retrieval before preflight is shown and confirmed.
3. Do not write workbook changes before planned deltas are shown.
4. Do not trust self-reported completion.
5. Reopen the saved workbook from disk inside the VM after writing.
6. Sync back to the host project folder.
7. Re-run host-side saved-file verification after sync.
8. Do not allow a run to complete without the required coverage and supersession artifacts.

## Required Roles

Use at least these agents for execution:

1. `Search Architect`
   - defines query families, sources, synonyms, disease-domain map, and sentinel set
2. `Retriever`
   - runs broad and narrow retrieval passes and builds the master candidate pool
3. `Coverage Challenger`
   - tries to find missed papers by citation chaining, author checks, expert-list comparison, review mining, and newer-review checks
4. `Verifier`
   - checks PMID/title/URL/excerpt correctness, dedupe integrity, and recency/supersession claims
5. `Adjudicator`
   - resolves disagreements and records explicit inclusion, exclusion, or supersession reasons

If the run uses fewer roles, it should explicitly say why.

## Core Principle

Recall comes first, then filtering, then verification.

Do not make the main search too narrow too early. It is safer to over-retrieve and filter than to under-retrieve and silently miss key papers.

## Stage 1: Lock the Question

Before retrieval, define:

1. review question
2. population/problem
3. exposure/intervention/biomarker concept
4. outcome concept
5. study types eligible
6. date limits, if any
7. language rules, if any
8. explicit inclusion rules
9. explicit exclusion rules

This should be written into the task request before execution.

## Stage 2: Build the Sentinel Set

Create a small set of papers that must be recoverable.

Sentinel sources:

1. landmark papers already known to the expert
2. papers from existing systematic reviews
3. papers from submitted reference lists
4. papers representing each major synonym, subtype, assay, phenotype, or time period
5. papers from major authors in the area

Target:

1. minimum 10 sentinel papers if available
2. cover all major concept variants, not just the most famous papers
3. include at least one sentinel paper for every major domain in scope
4. include the latest major systematic review or meta-analysis for each major domain if such a review exists

The search is not good enough until the sentinel set is recovered.

## Stage 2A: Build the Domain Coverage Matrix

Before full retrieval, define the major domains or condition families in scope.

For each domain, record:

1. `Domain`
2. `Key synonyms`
3. `Canonical older review`
4. `Canonical latest review/meta-analysis`
5. `Landmark primary paper`
6. `Major authors`
7. `Coverage status`

Write this to `reports/domain_coverage_matrix.csv`.

This step is mandatory for broad evidence-mapping tasks. A run must not proceed to completion if obvious major domains are unrepresented.

## Stage 3: Design Multiple Query Families

Do not rely on one query.

Use at least:

1. broad sensitivity query
2. narrower precision query
3. synonym and spelling variant query
4. author-based query for major authors
5. review-based query to locate prior reviews and mine their references
6. latest-review query to identify the most recent systematic review or meta-analysis for each domain
7. citation-based expansion from sentinel papers

Document every query string in `reports/search_log.md` or `reports/search_log.csv`.

The search strategy is not complete unless each domain in the domain coverage matrix has at least one domain-specific review query or explicit reason why that is not applicable.

## Stage 4: Retrieve From Multiple Sources

Minimum recommended sources for serious review work:

1. PubMed
2. Embase if available
3. PsycINFO if relevant
4. Scopus or Web of Science if available
5. Google Scholar or PMC for citation chasing and edge-case recovery

If some sources are unavailable, document the gap explicitly.

## Stage 5: Build the Master Candidate Pool

Create a deduped candidate set with source provenance.

For every candidate, keep:

1. title
2. authors
3. year
4. PMID if present
5. DOI if present
6. source database(s)
7. query family that found it
8. URL used
9. dedupe key

Write this to `reports/deduped_candidates.csv`.

## Stage 5A: Latest-Review Gate

Before relying on any review article, check whether a newer systematic review or meta-analysis exists for that same domain.

For each major domain:

1. identify the newest eligible review/meta-analysis
2. compare it to older commonly cited reviews
3. record whether the older review is superseded
4. record which review should be treated as the canonical top-level evidence source

Write this to `reports/review_supersession_audit.csv`.

If an older review is retained despite a newer review existing, the reason must be explicit.

## Stage 6: Reconcile Against Known Important Sources

Before screening is finalized, compare the candidate pool against:

1. sentinel set
2. expert-submitted references
3. papers cited by highly relevant reviews
4. papers from key authors
5. the latest-review target for each domain from the supersession audit

For each missing paper, record:

1. whether it was never retrieved
2. retrieved but excluded
3. retrieved but deduped incorrectly
4. retrieved but metadata mismatch blocked it
5. retrieved but superseded incorrectly or recency check failed

Write this to `reports/coverage_audit.csv`.

## Stage 7: Citation Chasing

Run both:

1. backward citation chasing from included and sentinel papers
2. forward citation chasing from included and sentinel papers

Also use:

1. related-article expansion where available
2. author bibliography checks for the top authors

Each citation-chasing addition should be recorded with its route of discovery in `reports/citation_chasing_log.csv`.

## Stage 7A: Benchmark Recall Eval

For high-stakes reviews, create a benchmark set of must-find papers.

This should include:

1. latest major review/meta-analysis per domain
2. landmark primary studies
3. expert-nominated must-find papers

Write this to `reports/benchmark_recall_set.csv`.

Then record whether each benchmark paper was:

1. retrieved
2. included
3. missed, with failure mode

Write results to `reports/benchmark_recall_results.csv`.

If benchmark recall is inadequate, the run fails.

## Stage 8: Screening and Adjudication

During title/abstract or full-text screening:

1. do not exclude on weak inference if relevance is ambiguous
2. prefer `uncertain` over confident exclusion when evidence is incomplete
3. require explicit exclusion reasons
4. require adjudication on disagreements

Recommended exclusion reason categories:

1. wrong population
2. wrong phenotype/outcome
3. wrong exposure/biomarker/topic
4. wrong study type
5. non-human
6. review/editorial/news
7. duplicate
8. insufficient evidence to classify

Write screening decisions to `reports/inclusion_decisions.csv`.

## Stage 9: Extraction

Only after coverage work is stable should extraction begin.

Each extracted row should preserve:

1. core identifier
2. direct working link
3. study type
4. population/sample
5. key variables
6. main findings
7. exact evidence quote when important interpretation depends on wording
8. confidence or uncertainty note if needed

If the workbook schema is intentionally minimal, put overflow evidence into `reports/extraction_notes.csv` rather than adding columns without approval.

## Stage 10: QA

Run all three QA rounds plus saved-file verification.

Round 1:

1. schema presence
2. row integrity
3. hyperlink format
4. dedupe integrity

Round 2:

1. identifier match
2. title-identifier consistency
3. link-identifier consistency
4. excerpt-verbatim check where excerpts are used

Round 3:

1. inclusion consistency
2. protected-sheet isolation
3. final cleanliness
4. coverage audit completeness
5. domain coverage completeness
6. review supersession audit completeness
7. benchmark recall completeness

High-recall report validation:

```bash
python3 scripts/validate_high_recall_reports.py --project .
```

Saved-file verification:

1. reopen saved workbook from disk inside the VM
2. report actual row count and identifiers from the saved file
3. after sync-back, rerun host-side verification on the real project copy

## Sidecar Files vs Workbook Sheets

Because strict mode defaults to content-only, the safest default is:

1. workbook = extraction output only
2. `reports/` = coverage audits, search logs, candidate pools, citation chasing logs, exclusion ledgers

Do not add extra workbook sheets for:

1. `Coverage Audit`
2. `Search Log`
3. `Sentinel Set`
4. `Citation Chasing`

unless the user explicitly approves structural change.

If structural change is approved, those can be mirrored as sheets. Otherwise keep them as sidecar files under `reports/`.

## Recommended High-Recall Artifacts

Write these files unless the user asks for a different format:

1. `reports/search_log.md`
2. `reports/domain_coverage_matrix.csv`
3. `reports/sentinel_set.csv`
4. `reports/deduped_candidates.csv`
5. `reports/review_supersession_audit.csv`
6. `reports/coverage_audit.csv`
7. `reports/citation_chasing_log.csv`
8. `reports/benchmark_recall_set.csv`
9. `reports/benchmark_recall_results.csv`
10. `reports/exclusion_decisions.csv`
11. `reports/final_gap_analysis.md`
12. `reports/qa_round_1.json`
13. `reports/qa_round_2.json`
14. `reports/qa_round_3.json`
15. `reports/saved_file_verification.json`

## Coverage Audit Schema

If using CSV or a dedicated sheet, use these columns:

1. `Known Important Paper`
2. `Source of Importance`
3. `Identifier`
4. `Retrieved (Y/N)`
5. `Included (Y/N/Uncertain)`
6. `If Not Included, Why Not`
7. `Search Route That Found It`
8. `Missed-Paper Failure Mode`
9. `Action Needed`

## Review Supersession Audit Schema

Use these columns:

1. `Domain`
2. `Older Review`
3. `Older Review Identifier`
4. `Latest Review`
5. `Latest Review Identifier`
6. `Latest Review Year`
7. `Newer Review Found (Y/N)`
8. `Canonical Review Selected`
9. `Older Review Retained (Y/N)`
10. `Retention Reason`

## Benchmark Recall Result Schema

Use these columns:

1. `Domain`
2. `Benchmark Paper`
3. `Identifier`
4. `Reason It Is Mandatory`
5. `Retrieved (Y/N)`
6. `Included (Y/N/Uncertain)`
7. `If Missed, Failure Mode`
8. `Action Needed`

## High-Confidence Stopping Rule

Do not say the evidence search is complete until all are true:

1. every major domain in scope is represented in the domain coverage matrix
2. the latest major review/meta-analysis has been checked for each major domain
3. sentinel set recovery is acceptable
4. benchmark recall is acceptable
5. expert reference list is reconciled
6. citation chasing yields no clearly eligible new papers
7. major-author check yields no unresolved gaps
8. coverage audit has no unexplained misses
9. review supersession audit has no unresolved recency gaps
10. QA rounds 1, 2, and 3 all pass
11. saved-file verification passes inside the VM
12. saved-file verification passes again on the host copy after sync-back

## Common Failure Modes This Workflow Is Designed To Catch

1. important paper never retrieved because the main query was too narrow
2. important paper retrieved but deduped away incorrectly
3. important paper present in a review but absent from the main candidate pool
4. older review retained even though a newer review exists
5. an entire disease domain silently underrepresented
6. PMID/title/URL mismatch
7. hallucinated completion despite no disk write
8. coverage artifacts silently omitted because the workbook schema was kept minimal
9. wrong sandbox synced back to the host project

## Short Practical Rule

If recall matters, do not trust a single search, a single agent, or a single completion message.

Require:

1. multi-route retrieval
2. adversarial missed-paper search
3. explicit reconciliation of known important papers
4. latest-review and supersession checks
5. saved-file verification on disk
