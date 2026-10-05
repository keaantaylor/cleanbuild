# Competitive-advantage rebuild: Phase 4 (memory + e-mail loop), branch `rebuild`

| Area | Change |
|---|---|
| Counterparty profile | Per sender: submissions with hashes, sheet layouts seen, reporting periods, recurring errors by rule and how they were resolved, known exceptions with reasons, approved corrections, approved rules, contacts, open requests. `GET /counterparties`, `GET /counterparties/profile?sender=` |
| Mapping memory | Same sender and identical headers: the mapping a person confirmed last time is proposed (state MAPPED_BY_MEMORY, evidence names the file and who confirmed it). A clean repeat file needs 0 mapping decisions; a person still confirms the sheet |
| Known exceptions, recurrence | A finding a person accepted as reported before (same rule, claim, column, value) is marked with who accepted it and why; it is not closed automatically. Root-cause cards say in how many of the sender's last 6 files the cause appeared |
| Approved rules | A correction a person approved 3+ times becomes a prompt: "TrueBind has observed this correction 3 times. Create an approved reusable rule?" Only a person creates the rule (re-validated server-side); then it applies on later files under policy, each change recorded with the rule id. Nothing is learned silently |
| E-mail loop | "Send to sender" writes an information request with a [TB-n] reference (text built by code from cells, expected, reported). A reply is matched by [TB-n] or Message-ID, only within the organisation and only from the address it was sent to; its text is stored for a person and never interpreted (a prompt-injection reply changes nothing). Linked issues move to review. An attached workbook becomes a linked resubmission; when processed, each linked issue is closed only if its rule no longer fires for that claim, otherwise kept open. Request, reply and verification appear in the trail |

Checks: backend 406 passed (1 Windows-only memory-limit test); new tests for mapping memory, rule suggestion and approval, the full reply and resubmission loop, spoofed sender, injection text, and retried webhooks. Frontend lint, typecheck, 24 unit, build OK. Migration 0023, additive, with RLS.
Left: no screens yet for counterparty profiles, rule suggestions or requests. Outbound requests send only when SMTP is configured.
