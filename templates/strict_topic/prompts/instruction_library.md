# Instruction Library (Copy/Paste)

Use exact statements to control run behavior.

## Allow a structural change

`STRUCTURE CHANGE APPROVED: You may add/remove/reorder columns for this run only.`

## Forbid all structural changes

`No structural changes. Content-only updates only.`

## Enforce Docker-only

`Docker-only execution. If approval is rejected, stop and re-send the same command only.`

## Enforce QA rounds

`Run QA for 3 rounds. If any round fails, stop and report failures only.`

## Enforce multi-agent flow

`Use Extractor, Verifier, and Adjudicator agents. Report each agent output summary.`

## Enforce protected-sheet isolation

`Do not copy or move rows from protected sheets into other sheets.`

## Require delta contract

`Before write: planned deltas. After write: actual deltas and ID-level changes.`

## Enforce high-recall review mode

`Use the high-recall workflow: sentinel set, multiple query families, expert-list reconciliation, citation chasing, coverage audit in reports/, and final gap analysis before claiming comprehensiveness.`
