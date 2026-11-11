# Project Handoff: Autoimmune Encephalitis + Psychosis Review

## Objective
Build a high-rigor, evidence-traceable systematic review workflow for autoimmune encephalitis and psychosis (including schizophrenia-spectrum presentations), with reproducible extraction into spreadsheet format.

## Non-Negotiables
1. Never overwrite the source workbook by default.
2. Never use raw XLSX XML patching for edits.
3. Use `openpyxl` for workbook writes.
4. Keep retrieval and QA as separate stages:
   - Stage 1: Retrieval/Search (add candidate records)
   - Stage 2: Metadata QA (PMID/URL/title checks)
   - Stage 3: Abstract/verbatim QA
5. If a required dependency/tool is missing, ask for permission before any fallback.
6. If a command is denied, request explicit escalation rather than using lower-quality alternatives.

## Known Failure Modes (Already Observed)
1. QA-only execution did not retrieve new papers.
2. PMID parsing bug: DOI fragments were incorrectly interpreted as PMIDs.
3. Direct XML workbook edits produced files that were unusable in Excel.
4. Overly broad “seeding” behavior created low-quality rows (placeholder topic repetition and weak metadata).

## Permission Policy
1. Ask for escalation for:
   - Package install (`pip install`)
   - Live network metadata retrieval (PubMed/Crossref/HTML metadata)
   - Any access outside writable workspace
2. Do not improvise tool substitutions after denial.
3. Re-run blocked commands with explicit escalation request and clear justification.

## Output Contract
1. Source workbook remains unchanged unless user explicitly requests in-place mode.
2. All writes go to a separate output workbook, e.g. `*_output.xlsx`.
3. Machine-readable reports are written to `/reports`:
   - summary
   - metadata QA
   - abstract QA
   - required-list coverage

## Data Quality and QA Rules
1. No quote, no claim.
2. No location/page/field, no pass.
3. Off-by-one PMID sentinel:
   - Compare candidate PMID with PMID-1 and PMID+1 title similarity.
4. Do not infer PMIDs from DOI substrings.
5. Normalize PubMed URLs to `https://pubmed.ncbi.nlm.nih.gov/{PMID}/`.
6. Distinguish:
   - `NO_VALID_PMID` (expected for non-PubMed sources)
   - true metadata mismatch
   - network retrieval failures

## Acceptance Checks (Must Pass)
1. Output workbook opens in Excel.
2. Output workbook opens via `openpyxl` without error.
3. Required-list coverage count is correct.
4. PMID mismatch and off-by-one checks are explicit in reports.
5. Abstract verbatim checks are explicit and flaggable.
6. No in-place writes unless explicitly requested.

## Recommended Clean Workflow (v2)
1. Start in a new isolated folder/workspace.
2. Install dependencies with approval (`openpyxl`, plus optional retrieval libs if needed).
3. Run retrieval first to collect candidates.
4. Run metadata QA second.
5. Run abstract/verbatim QA third.
6. Export to a separate reviewed workbook.
7. Human adjudication on all `REVIEW` flags.

