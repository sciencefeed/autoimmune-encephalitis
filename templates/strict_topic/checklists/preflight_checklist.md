# Preflight Checklist

1. Confirm `AGENTS.md` exists in project root.
2. Confirm `policy/pipeline_policy.yaml` is filled with real paths and sheet names.
3. Confirm protected sheet names are correct.
4. Confirm allowed-edit sheet list is correct.
5. Confirm Docker is running.
6. Confirm network access method is approved.
7. Confirm run mode is content-only unless user explicitly approved structural change.
8. Confirm planned deltas are shown to user before write.
9. Confirm multi-agent roles are declared (`Extractor`, `Verifier`, `Adjudicator`).
10. Confirm QA round count is set to 3.
