#!/usr/bin/env python3
"""Repeated, isolated Codex CLI A/B benchmark for dev-memory (uses synthetic data only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import selectors
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
from check_maintenance import observed_usage, observed_maintenance
import time
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parents[1] / "skills" / "dev-memory"
sys.path.insert(0, str(PACKAGE / "scripts"))
from dev_memory import SKILL_FILES
SOURCES = tuple(SKILL_FILES)

def source_hashes():
    return {n: hashlib.sha256((PACKAGE / n).read_bytes()).hexdigest() for n in SOURCES}
STARTER = "def refund_eligible(order):\n    raise NotImplementedError(\"policy not implemented\")\n"
TASK = (
    "This project contains an optional local development-memory Skill at .agents/skills/dev-memory. "
    "If present, read SKILL.md and use its CLI to recall the prior confirmed refund policy for this project. "
    "Implement refund_eligible(order) and add tests only when an applicable stored policy is available. "
    "If no applicable policy is available, do not invent eligibility rules or change code; ask what exact policy to use."
)
AUTOMATIC_TASK = (
    "Implement refund_eligible(order) in refunds.py and add unit tests. The current user-confirmed policy is: "
    "the order must be delivered and unopened, with days_since_delivery <= 14; gift and final_sale orders are excluded. "
    "Require every positive condition and both exclusions. Do not change any unrelated business code. "
    "Run the tests and report the actual result."
)
CRITERIA = ("delivered", "unopened", "14", "gift", "final")

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenario", choices=("recovery", "automatic-maintenance"), default="recovery")
    p.add_argument("--model", required=True, help="One exact Codex model ID used for all cells.")
    p.add_argument("--reasoning", choices=("low", "medium", "high", "xhigh"), required=True)
    p.add_argument("--repetitions", type=int, default=3, help="Minimum recommended: 3 independent runs per cell.")
    p.add_argument("--seed", type=int, default=20261010, help="Shuffle seed for condition order.")
    p.add_argument("--timeout-seconds", type=int, default=180)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--codex", default="codex", help="Codex CLI executable.")
    return p

def _copy_support(project: Path) -> Path:
    target = project / ".agents" / "skills" / "dev-memory"
    target.mkdir(parents=True)
    for rel in SOURCES:
        src, dst = PACKAGE / rel, target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return target

def _starter(project: Path) -> None:
    project.mkdir(parents=True, exist_ok=True)
    (project / "refunds.py").write_text(STARTER, encoding="utf-8")
    (project / "README.md").write_text("Synthetic refund-policy benchmark fixture. No customer data.\n", encoding="utf-8")

def _seed_history(skill: Path, project: Path, global_root: Path) -> None:
    env = {**os.environ, "DEV_MEMORY_HOME": str(global_root)}
    cli = skill / "scripts" / "dev_memory.py"
    subprocess.run([sys.executable, str(cli), "init", "--global"], check=True, env=env, capture_output=True, text=True)
    subprocess.run([sys.executable, str(cli), "init", "--project-root", str(project)], check=True, env=env, capture_output=True, text=True)
    subprocess.run([sys.executable, str(cli), "mode", "full-project", "--project-root", str(project)],
                   check=True, env=env, capture_output=True, text=True)
    record = {
        "kind": "business_rule", "claim_type": "desired", "strength": "hard",
        "title": "Confirmed refund eligibility", "content": "Refund eligibility requires a delivered, unopened order within 14 days.",
        "conditions": "The order is delivered; the item is unopened; no more than 14 days have elapsed.",
        "exceptions": "Gift orders and final-sale items are excluded.",
        "do": "Require all positive conditions.", "dont": "Do not permit gifts or final-sale items.",
        "verification_steps": "Test each positive condition and both exclusions.",
        "tags": ["refund"], "source": {"type": "user_confirmation", "excerpt": "Only delivered, unopened orders within 14 days; gifts and final-sale items are excluded."},
    }
    payload = {"schema_version": 1, "scope": "project", "session_id": "synthetic-seed-session",
               "turn_id": "synthetic-seed-turn", "task_id": "refund-policy", "idempotency_key": "synthetic-seed-v1",
               "operations": [{"op": "ADD", "scope": "project", "record": record}]}
    subprocess.run([sys.executable, str(cli), "apply", "--project-root", str(project)], input=json.dumps(payload),
                   check=True, env=env, capture_output=True, text=True)

def _token_usage(event: dict[str, Any]) -> dict[str, int] | None:
    found = []
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("usage", "last_token_usage", "total_token_usage"):
                usage = value.get(key)
                if isinstance(usage, dict):
                    tokens = {k: v for k, v in usage.items() if "token" in k.casefold() and isinstance(v, (int, float))}
                    if tokens:
                        found.append(tokens)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(event)
    return found[-1] if found else None

def _memory_state(project: Path, *, history: bool, mode: str) -> dict[str, Any]:
    import dev_memory_store as store
    records = [store.show_record('project',r['id'],project_root=project)['record']
               for r in store.list_records('project',project_root=project)['records']]
    rules = [r for r in records if r['kind'] in {'business_rule','decision'} and r['claim_type']=='desired'
             and ('refund' in r['tags'] or 'refund' in r['title'].casefold())]
    return {'active_refund_rules':len(rules),
            'historical_duplicates_retired':len(rules)==1 if history and mode=='on' else None,
            'state_count_not_semantic_proof':True}

def _run_trial(codex: str, model: str, reasoning: str, timeout: int, *, mode: str, history: bool,
               repetition: int, scratch: Path, scenario: str = "recovery") -> dict[str, Any]:
    project = scratch / "project"
    global_root = scratch / "global-data"
    _starter(project)
    skill = _copy_support(project) if mode == "on" else None
    global_root.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CODEX_DISABLE_PROJECT_DOCS": "1", "DEV_MEMORY_HOME": str(global_root)}
    if mode == "on" and scenario == "recovery":
        _seed_history(skill, project, global_root) if history else _seed_empty(skill, project, global_root)
    task_text = TASK
    if scenario == "automatic-maintenance":
        auth = Path(os.environ.get("CODEX_HOME", Path.home()/".codex"))/"auth.json"
        home = scratch / "home"; home.mkdir()
        codex_home = home / ".codex"; codex_home.mkdir()
        if auth.is_file():
            shutil.copyfile(auth, codex_home / "auth.json")
            os.chmod(codex_home / "auth.json", 0o600)
        env.update(HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(codex_home), PYTHONDONTWRITEBYTECODE="1")
        env.pop("CODEX_DISABLE_PROJECT_DOCS", None)
        task_text = AUTOMATIC_TASK
        seed_skill = skill or PACKAGE
        _seed_history(seed_skill, project, global_root) if history else _seed_empty(seed_skill, project, global_root)
        if mode == "on":
            import dev_memory_setup
            dev_memory_setup.setup(project, "codex", skill, sys.executable, global_root)
        if history:
            import dev_memory_store
            original = dev_memory_store.list_records("project",project_root=project)["records"][0]
            record = dev_memory_store.show_record("project",original["id"],project_root=project)["record"]
            for n, body in enumerate(("Every stated condition must hold, including both exclusions.",
                                       "Require all stated refund conditions and both exclusions. " * 30)):
                replacement = {k:v for k,v in record.items() if k not in {"id","revision","semantic_hash","created_at","updated_at"}}
                replacement.update(content=body, source={"type":"user_confirmation","excerpt":"Synthetic repeated confirmation of the same refund rule."})
                dev_memory_store.apply_payload({"schema_version":1,"scope":"project","session_id":"benchmark-seed",
                    "turn_id":f"paraphrase-{n}","idempotency_key":f"paraphrase-{n}","operations":[{"op":"ADD","record":replacement}]},project_root=project)
    last_message = scratch / "last-message.txt"
    argv = [codex, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
            "--sandbox", "workspace-write", "--model", model, "--config", f"model_reasoning_effort={reasoning}",
            "--add-dir", str(global_root), "--output-last-message", str(last_message), task_text]
    start = time.monotonic()
    first_action = None
    first_business_edit = None
    memory_events = 0
    protocol_reads = 0
    tool_events = 0
    token_usage = None
    reported_use_ids = set()
    maintenance_observed = {'COMPACT':False,'MERGE_DUPLICATES':False,'MAINTENANCE_REVIEW':False}
    event_lines = 0
    host_errors = []
    timed_out = False
    error_file = scratch / "stderr.log"
    error_stream = error_file.open("w", encoding="utf-8")
    process = subprocess.Popen(argv, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=error_stream,
                              text=True, encoding="utf-8", errors="replace", bufsize=1, start_new_session=True)
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    while selector.get_map():
        try:
            business_changed = (project / "refunds.py").read_text() != STARTER
        except OSError:
            business_changed = False
        if first_business_edit is None and business_changed:
            first_business_edit = time.monotonic() - start
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, AttributeError):
                process.kill()
            break
        for key, _ in selector.select(min(0.25, remaining)):
            line = key.fileobj.readline()
            if not line:
                selector.unregister(key.fileobj)
                continue
            event_lines += 1
            received = time.monotonic()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get('type') in {'error', 'turn.failed'}:
                host_errors.append(event)
            token_usage = _token_usage(event) or token_usage
            reported_use_ids.update(observed_usage([event]))
            for operation, observed in observed_maintenance([event]).items():
                maintenance_observed[operation] |= observed
            item = event.get("item") if isinstance(event, dict) else None
            event_type = event.get("type") if isinstance(event, dict) else None
            item_type = item.get("type") if isinstance(item, dict) else None
            if event_type == "item.started" and item_type in {"command_execution", "mcp_tool_call", "tool_call", "file_change"}:
                tool_events += 1
                command = item.get("command", "")
                memory_events += "dev_memory.py" in command
                protocol_reads += "references/protocol.md" in command
                if first_action is None:
                    first_action = received - start
    process.wait()
    selector.close()
    process.stdout.close()
    error_stream.close()
    stderr = (scratch / "stderr.log").read_text(encoding="utf-8", errors="replace")
    duration = time.monotonic() - start
    final_text = last_message.read_text(encoding="utf-8", errors="replace") if last_message.exists() else ""
    code = (project / "refunds.py").read_text(encoding="utf-8", errors="replace")
    changed = code != STARTER
    lower_code = code.casefold()
    constraints = {"delivered": "delivered" in lower_code, "unopened": "unopened" in lower_code,
                   "14_day_limit": "14" in lower_code, "gift_exclusion": "gift" in lower_code,
                   "final_sale_exclusion": "final" in lower_code}
    lowered_message = final_text.casefold()
    asks = "?" in final_text and any(token in lowered_message for token in ("policy", "eligibility", "conditions", "rules")) and any(
        token in lowered_message for token in ("what", "which", "provide", "specify", "tell me")
    )
    expected = "implement_rule" if scenario == "automatic-maintenance" or mode == "on" and history else "ask_for_policy"
    test_result = None
    tests_path = project / "tests"
    root_tests = list(project.glob("test*.py"))
    if tests_path.is_dir() or root_tests:
        try:
            test = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                                   "tests" if tests_path.is_dir() else ".", "-v"],
                                  cwd=project, env=env, capture_output=True, text=True, timeout=15)
            output = test.stdout + test.stderr
            match = re.search(r"Ran\s+(\d+)\s+tests?", output)
            test_result = {"exit_code": test.returncode, "test_count": int(match.group(1)) if match else 0,
                           "output_tail": output[-2000:]}
        except subprocess.TimeoutExpired:
            test_result = {"exit_code": None, "timeout": True}
    test_count = test_result.get("test_count", 0) if test_result else None
    independent_behavior = None
    if scenario == "automatic-maintenance":
        probe = """import refunds
cases=[(dict(delivered=True,unopened=True,days_since_delivery=14,gift=False,final_sale=False),True),
(dict(delivered=False,unopened=True,days_since_delivery=1,gift=False,final_sale=False),False),
(dict(delivered=True,unopened=False,days_since_delivery=1,gift=False,final_sale=False),False),
(dict(delivered=True,unopened=True,days_since_delivery=15,gift=False,final_sale=False),False),
(dict(delivered=True,unopened=True,days_since_delivery=1,gift=True,final_sale=False),False),
(dict(delivered=True,unopened=True,days_since_delivery=1,gift=False,final_sale=True),False)]
assert all(refunds.refund_eligible(order)==expected for order,expected in cases)
"""
        checked = subprocess.run([sys.executable,"-c",probe],cwd=project,env=env,capture_output=True,text=True,timeout=10)
        independent_behavior = checked.returncode == 0
    policy_match = (independent_behavior if scenario == "automatic-maintenance" else all(constraints.values())) if expected == "implement_rule" else None
    tests_passed = (test_result.get("exit_code") == 0 and test_count > 0) if test_result else None
    memory_state = None
    if scenario == 'automatic-maintenance':
        memory_state = _memory_state(project,history=history,mode=mode)
    criterion = (bool(policy_match) and tests_passed) if expected == "implement_rule" and test_result else (
        None if expected == "implement_rule" else (not changed and asks)
    )
    return {
        "mode": mode, "history": history, "repetition": repetition, "exit_code": process.returncode,
        "timed_out": timed_out, "host_errors": host_errors, "duration_seconds": round(duration, 3),
        "first_effective_action_seconds": round(first_action, 3) if first_action is not None else None,
        "first_business_edit_seconds": round(first_business_edit, 3) if first_business_edit is not None else None,
        "memory_tool_events": memory_events, "protocol_read_events": protocol_reads,
        "tool_event_count": tool_events, "token_usage": token_usage, "jsonl_event_count": event_lines,
        "memory_use_reported_ids": sorted(reported_use_ids),
        "maintenance_operations_observed": maintenance_observed, "memory_state_after": memory_state,
        "expected_behavior": expected, "automated_criterion_match": criterion,
        "policy_constraint_match": policy_match,
        "constraint_presence": constraints if expected == "implement_rule" else None,
        "independent_behavior_six_cases": independent_behavior,
        "generated_test_count": test_count if expected == "implement_rule" else None,
        "generated_tests_passed": tests_passed if expected == "implement_rule" else None,
        "changed_code": changed, "asked_for_policy": asks, "test_result": test_result,
        "final_message": final_text[-3000:], "stderr_tail": stderr[-1500:],
    }

def _seed_empty(skill: Path, project: Path, global_root: Path) -> None:
    env = {**os.environ, "DEV_MEMORY_HOME": str(global_root)}
    cli = skill / "scripts" / "dev_memory.py"
    subprocess.run([sys.executable, str(cli), "init", "--global"], check=True, env=env, capture_output=True, text=True)
    subprocess.run([sys.executable, str(cli), "init", "--project-root", str(project)], check=True, env=env, capture_output=True, text=True)
    subprocess.run([sys.executable, str(cli), "mode", "full-project", "--project-root", str(project)],
                   check=True, env=env, capture_output=True, text=True)

def _completed_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def stats(field):
        values = [r[field] for r in rows if isinstance(r.get(field), (int, float))]
        return {'median': statistics.median(values), 'min': min(values), 'max': max(values)} if values else None
    tokens = [u.get('total_tokens', u.get('input_tokens', 0) + u.get('output_tokens', 0))
              for r in rows if isinstance((u := r.get('token_usage')), dict)]
    return {'n': len(rows), 'duration_seconds': stats('duration_seconds'),
            'first_tool_action_seconds': stats('first_effective_action_seconds'),
            'first_business_edit_seconds': stats('first_business_edit_seconds'),
            'tool_events': stats('tool_event_count'),
            'memory_tool_events': stats('memory_tool_events'),
            'protocol_read_events': stats('protocol_read_events'),
            'token_sum_median': statistics.median(tokens) if tokens else None,
            'tokens_available_n': len(tokens)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [r["duration_seconds"] for r in rows if isinstance(r.get("duration_seconds"), (int, float))]
    first = [r["first_effective_action_seconds"] for r in rows if r["first_effective_action_seconds"] is not None]
    tokens = [
        usage.get("total_tokens", usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
        for r in rows if (usage := r.get("token_usage")) and isinstance(usage, dict)
    ]
    tool_counts = [r["tool_event_count"] for r in rows if isinstance(r.get("tool_event_count"), (int, float))]
    return {
        "n": len(rows), "completed_metrics": _completed_metrics([r for r in rows if r.get('exit_code') == 0 and not r.get('timed_out')]),
        "host_failed_or_timed_out": sum(r.get('exit_code') != 0 or bool(r.get('timed_out')) for r in rows),
        "duration_median_seconds": statistics.median(values) if values else None,
        "duration_min_seconds": min(values) if values else None, "duration_max_seconds": max(values) if values else None,
        "first_action_median_seconds": statistics.median(first) if first else None,
        "tool_events_median": statistics.median(tool_counts) if tool_counts else None,
        "token_sum_median": statistics.median(tokens) if tokens else None,
        "correct_criteria": sum(r.get("automated_criterion_match") is True for r in rows),
        "criteria_evaluated": sum(r.get("automated_criterion_match") is not None for r in rows),
        "criteria_unknown": sum(r.get("automated_criterion_match") is None for r in rows),
        "policy_constraint_matches": sum(bool(r.get("policy_constraint_match")) for r in rows if r.get("policy_constraint_match") is not None),
        "generated_test_suites_passed": sum(bool(r.get("generated_tests_passed")) for r in rows if r.get("generated_tests_passed") is not None),
        "semantic_review_required": True,
    }

def main() -> int:
    args = parser().parse_args()
    if args.repetitions < 1:
        parser().error("--repetitions must be at least 1")
    codex = shutil.which(args.codex) or args.codex
    order = [(mode, history, rep) for rep in range(1, args.repetitions + 1)
             for history in (False, True) for mode in ("off", "on")]
    random.Random(args.seed).shuffle(order)
    rows = []
    frozen = source_hashes()
    for index, (mode, history, rep) in enumerate(order, 1):
        if source_hashes() != frozen:
            raise RuntimeError("Runtime changed during the benchmark; do not publish mixed-source metrics.")
        with tempfile.TemporaryDirectory(prefix="dev-memory-bench-") as temp:
            print(f"[{index}/{len(order)}] mode={mode} history={history} repetition={rep}", file=sys.stderr, flush=True)
            try:
                rows.append(_run_trial(codex, args.model, args.reasoning, args.timeout_seconds, mode=mode,
                                       history=history, repetition=rep, scratch=Path(temp), scenario=args.scenario))
            except Exception as exc:
                rows.append({"mode": mode, "history": history, "repetition": rep, "exit_code": None,
                             "timed_out": False, "duration_seconds": None, "first_effective_action_seconds": None,
                             "tool_event_count": None, "token_usage": None, "automated_criterion_match": None,
                             "runner_error": f"{type(exc).__name__}: {exc}"})
    if source_hashes() != frozen:
        raise RuntimeError("Runtime changed during the benchmark; do not publish mixed-source metrics.")
    groups = {}
    for mode in ("off", "on"):
        for history in (False, True):
            key = f"{mode}/{'history' if history else 'empty'}"
            groups[key] = _summary([r for r in rows if r["mode"] == mode and r["history"] == history])
    report = {
        "benchmark": "dev-memory A/B synthetic refund-rule coding task", "scenario": args.scenario,
        "runtime_source_sha256": frozen,
        "history_stores_identically_seeded_on_and_off": args.scenario == "automatic-maintenance",
        "runtime_version": "0.7.0", "current_constraints_given_equally": args.scenario == "automatic-maintenance",
        "model": args.model, "reasoning": args.reasoning, "codex_cli": _version(codex),
        "repetitions_per_cell": args.repetitions, "condition_order_seed": args.seed,
        "same_task_text": True, "same_starting_code": True,
        "metrics_note": "Tool event counts and token use are best-effort Codex CLI JSONL observations. Input+output tokens are summed once; cached input is a subset. The first observable tool-action event proxies first effective action; first_business_edit_seconds polls the starter file at approximately 250ms resolution and does not prove the edit is correct. Code-string policy checks and test execution do not replace semantic review.",
        "cells": groups, "trials": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "report": str(args.output), "cells": groups}, ensure_ascii=False, indent=2))
    return 0

def _version(codex: str) -> str | None:
    try:
        result = subprocess.run([codex, "--version"], capture_output=True, text=True, timeout=5)
        return (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return None

if __name__ == "__main__":
    raise SystemExit(main())
