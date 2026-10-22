# Project and global capture review — 0.8.3

## Findings and changes

- High: setup explicitly initialized developer-first, so ordinary project ADD operations were skipped despite usable stores. New setups now use full-project, consistent with low-level init; upgrades preserve deliberate existing modes and privacy controls.
- High: project policy described only rules/technical decisions and host guidance called them facts. Expanded criteria cover conventions, contracts, business invariants, architecture, documentation, operations, verified lessons and stable navigation. Capture requires future usefulness and authoritative evidence, not keyword matching or the user saying remember.
- Medium: readable/available status hid the write-mode restriction. Normal context now returns capture_mode and capture_enabled on successful, empty, cached and disabled results, with no extra startup command. Doctor exposes the mode too.
- Medium: temporary/business-specific/unclear wording could justify saving one-time content in an authorized project. Temporary and unclear directions now stay in conversation; durable business content stays project-local.
- Medium: generic reusable-choice guidance could globalize repository conventions. Project applicability is checked first; an independently reusable method is separated and de-identified. First eligible global feedback remains a candidate; explicit cross-project rules retain strength. No project write fallback to global.

- High: a real read-only inspection exposed a legacy hypothesis marked active. New active hypotheses are rejected; ordinary retrieval excludes legacy hypotheses on indexed and fallback paths without deleting history. Retrieval format 4 invalidates prior context caches. A newer hypothetical legacy checkpoint cannot suppress a valid earlier checkpoint.

## Eligibility contract

Capture one supported atomic rule when it changes later work in its owning project. Include its module/situation, positive and negative conditions, exceptions and source. User-confirmed desired rules can be active on first occurrence; code observations describe existing behavior only. Do not infer a normative convention from one legacy implementation. Verified lessons retain cause and prevention evidence. Prefer canonical references to copying whole specifications. Ordinary task progress, transient instructions, secrets, speculative diagnoses and generic advice are excluded.

Controls win over capture: existing developer-first, pause/disable, read-only, excluded stores and turn opt-outs are never automatically overridden by an upgrade. Surface relevant unsaved increments rather than claiming success. No task checkpoint workflow was added.

## Independent policy exercise

A separate reviewer applied the Skill to five synthetic inputs without writing real stores: repository DTO readability => scoped project convention; one-time export exception => no memory; legacy permissive authorization => observed fact only if durable/useful; explicit all-project reuse directive => confirmed global rule; evidenced duplicate-write cause plus chosen idempotency => separate observed lesson and desired decision. The reviewer found a temporary-scope wording ambiguity, corrected before release.

This is an instruction-level exercise, not a fresh real Codex-host end-to-end certification. Program tests prove persistence/recall and controls after the assistant selects a record; they cannot prove arbitrary natural-language judgments.

## Verification

The complete suite passed 248 tests (one platform-specific skip) under PYTHONUTF8=1 before the final hypothesis guard. After that guard, 151 affected tests passed (47 store/integration, 35 adversarial, 16 lifecycle, 40 maintenance, 13 first-signal capture); the expanded legacy-checkpoint regression also passed independently. Setup tests passed 22 cases. The Windows ACL test passed separately after avoiding text decoding of unused native icacls output. The Skill validator and release builder passed. New setup regressions write and recall engineering/documentation conventions, business rules, decisions, procedures, facts and lessons without a mode switch; an existing developer-first project remains blocked and reports its mode. Existing global candidate/promotion, isolation, privacy and revision tests remain required. Initial Windows default-locale testing produced GBK decoding errors; final validation uses PYTHONUTF8=1.
