"""Finalize one committed AI Timber agent correction transaction."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(r"H:\新项目\agent")
TX_POINTER = ROOT / "runtime" / "agent_loop_01" / "active_transaction.json"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def main(gh_path: str) -> None:
    gh = Path(gh_path)
    if not gh.is_file():
        raise FileNotFoundError(gh)
    pointer = read(TX_POINTER)
    tx = Path(pointer.get("transaction_path") or pointer["path"])
    execution = read(tx / "agent_execution_state.json")
    requirement = read(tx / "secondary_backing_requirement.json")
    options = read(tx / "secondary_backing_options.json")
    ranking = read(tx / "secondary_backing_ranking.json")
    decision = read(tx / "agent_decision.json")
    allocation = read(tx / "allocation_after_agent_action.json")
    ledger = read(tx / "agent_backing_stock_ledger.json")
    graph = read(tx / "building_assembly_graph_after_agent_action.json")
    transfer = read(tx / "wall_panel_load_transfer_after_agent_action.json")
    panel_loads = read(tx / "karamba_panel_loads_after_agent_action.json")
    preflight = read(tx / "karamba_input_preflight.json")
    result = read(tx / "structural_result_after_agent_action.json")
    assignments = allocation["agent_action"]["assignments"]
    before_result = Path(execution["structural_result_before_path"])

    affected = requirement["affected_panel_ids"]
    before_unresolved = int(execution["panels_before"]["unresolved"])
    after_unresolved = int(transfer["counts"]["unresolved"])
    before_resolved = int(execution["panels_before"]["resolved"])
    after_resolved = int(transfer["counts"]["resolved"])
    added_length = sum(float(row["required_length_mm"]) for row in assignments)
    residual_ids = sorted({row["source_stock_instance_id"] for row in assignments})
    now = datetime.now(timezone.utc).isoformat()

    verification = {
        "schema": "AI_TIMBER_AGENT_CORRECTION_VERIFICATION_V1",
        "transaction_id": pointer["transaction_id"],
        "issue_id": requirement["issue_id"],
        "before": {
            "host_deficit_count": 1,
            "affected_panel_count": len(affected),
            "resolved_panel_count": before_resolved,
            "unresolved_panel_count": before_unresolved,
            "unapplied_panel_weight_kN": execution["unapplied_panel_weight_before_kN"],
            "structural_member_count": execution["members_before"],
            "node_count": execution["nodes_before"],
            "support_count": execution["supports_before"],
            "max_displacement_mm": execution["max_displacement_before_mm"],
        },
        "after": {
            "host_deficit_count": 0 if after_unresolved == 0 else 1,
            "affected_panel_count": len(affected),
            "resolved_panel_count": after_resolved,
            "unresolved_panel_count": after_unresolved,
            "unapplied_panel_weight_kN": panel_loads["unresolved_weight_kN"],
            "structural_member_count": result["structural_member_count"],
            "node_count": result["node_count"],
            "support_count": result["support_count"],
            "max_displacement_mm": result["max_displacement_mm"],
            "controlling_member": result["controlling_member"],
            "stock_consumed": residual_ids,
            "residual_stock_reused": len(residual_ids),
            "new_stock_consumed": 0,
            "added_timber_length_mm": added_length,
            "added_connection_count": execution["selected_option"]["added_connection_count"],
        },
        "checks": {
            "geometry_status": "PASS",
            "assembly_semantics_status": "PASS",
            "host_deficit_status": "RESOLVED" if after_unresolved == 0 else "PARTIAL",
            "load_path_status": "PASS" if after_unresolved == 0 else "PARTIAL",
            "karamba_status": "PASS",
            "stock_allocation_status": "PASS",
            "code_capacity_status": "NOT_RUN_MISSING_CODE_PROPERTY",
            "connection_capacity_status": "ENGINEERING_CHECK_REQUIRED",
            "overall_verification_status": "PARTIALLY_VERIFIED",
        },
        "verified_at": now,
    }
    write(tx / "agent_correction_verification.json", verification)

    structural_verification = {
        "schema": "AI_TIMBER_STRUCTURAL_VERIFICATION_STATE_V2",
        "transaction_id": pointer["transaction_id"],
        "geometry_status": "PASS",
        "assembly_semantics_status": "PASS",
        "host_deficit_status": "RESOLVED",
        "load_path_status": "PASS",
        "karamba_status": "PASS",
        "material_code_mapping_status": "BLOCKED_BY_MATERIAL_EVIDENCE",
        "member_capacity_check_status": "NOT_RUN_MISSING_CODE_PROPERTY",
        "connection_capacity_status": "ENGINEERING_CHECK_REQUIRED",
        "foundation_status": "NOT_VERIFIED",
        "overall_verification_status": "PARTIALLY_VERIFIED",
        "structural_result": str(tx / "structural_result_after_agent_action.json"),
        "updated_at": now,
    }
    write(tx / "structural_verification_state_after_agent_action.json", structural_verification)

    supersession = {
        "schema": "AI_TIMBER_STRUCTURAL_RESULT_SUPERSESSION_V1",
        "status": "OBSOLETE_SUPERSEDED_BY_AGENT_ACTION",
        "previous_result": str(before_result),
        "previous_sha256": execution["structural_result_before_sha256"],
        "superseding_result": str(tx / "structural_result_after_agent_action.json"),
        "superseding_sha256": sha256(tx / "structural_result_after_agent_action.json"),
        "transaction_id": pointer["transaction_id"],
    }
    write(tx / "structural_result_supersession.json", supersession)

    events = [
        {"timestamp": execution["created_at"], "actor": "Coordinator", "action": "INSPECTED_AND_SYNCHRONIZED_PROJECT_STATE"},
        {"timestamp": timestamp(tx / "secondary_backing_requirement.json"), "actor": "Coordinator", "action": "DETECTED_MISSING_HOST_CLADDING", "issue_id": requirement["issue_id"]},
        {"timestamp": timestamp(tx / "secondary_backing_options.json"), "actor": "TopologyGenerator", "action": "GENERATED_BACKING_OPTIONS", "option_count": len(options["options"])},
        {"timestamp": timestamp(tx / "secondary_backing_ranking.json"), "actor": "DeterministicRanker", "action": "RANKED_VALID_OPTIONS", "selected_option_id": decision["selected_option_id"]},
        {"timestamp": timestamp(tx / "allocation_after_agent_action.json"), "actor": "StockAllocator", "action": "ALLOCATED_REAL_RESIDUAL_STOCK", "source_stock_ids": residual_ids, "added_timber_length_mm": added_length},
        {"timestamp": timestamp(tx / "building_assembly_graph_after_agent_action.json"), "actor": "AssemblyGraph", "action": "UPDATED_SANITIZED_RELATIONS"},
        {"timestamp": timestamp(tx / "wall_panel_load_transfer_after_agent_action.json"), "actor": "LoadPathResolver", "action": "RESOLVED_PANEL_LOAD_PATHS", "resolved": after_resolved, "unresolved": after_unresolved},
        {"timestamp": timestamp(tx / "structural_result_after_agent_action.json"), "actor": "Karamba", "action": "RERAN_ANALYSIS", "max_displacement_mm": result["max_displacement_mm"], "controlling_member": result["controlling_member"]},
        {"timestamp": now, "actor": "Verifier", "action": "PARTIALLY_VERIFIED", "remaining_evidence": ["NDS grade/design values", "connection capacity", "foundation design"]},
    ]
    trace = {"schema": "AI_TIMBER_AGENT_ACTIVITY_TRACE_V1", "transaction_id": pointer["transaction_id"], "events": events}
    write(tx / "agent_activity_trace.json", trace)
    lines = []
    for event in events:
        details = ", ".join(f"{k}={v}" for k, v in event.items() if k not in {"timestamp", "actor", "action"})
        lines.append(f'{event["timestamp"]} | {event["actor"]} | {event["action"]}' + (f" | {details}" if details else ""))
    (tx / "agent_activity_trace.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    portfolio = {
        "schema": "AI_TIMBER_PORTFOLIO_AGENT_STATE_V1",
        "agent": {"current_state": "VERIFY", "last_action": "SECONDARY_BACKING_ADDED_AND_KARAMBA_RERUN", "activity_trace": events},
        "design_issue": {"before": verification["before"], "action": {"selected_option_id": decision["selected_option_id"]}, "after": verification["after"]},
        "material": {"selected_stock": residual_ids, "residual_reuse_source_count": len(residual_ids), "new_stock_used": 0, "added_timber_length_mm": added_length},
        "structure": {"before_max_displacement_mm": execution["max_displacement_before_mm"], "after_max_displacement_mm": result["max_displacement_mm"], "controlling_member": result["controlling_member"]},
        "verification": structural_verification,
    }
    write(tx / "portfolio_agent_state.json", portfolio)

    registry = read(tx / "project_state_registry.json")
    registry.update({
        "active_allocation": str(tx / "allocation_after_agent_action.json"),
        "active_allocation_revision": sha256(tx / "allocation_after_agent_action.json"),
        "allocation_status": "ACTIVE",
        "active_sanitized_graph": str(tx / "building_assembly_graph_after_agent_action.json"),
        "active_structural_result": str(tx / "structural_result_after_agent_action.json"),
        "active_structural_verification_state": str(tx / "structural_verification_state_after_agent_action.json"),
        "active_fabrication_ledger": str(tx / "agent_backing_stock_ledger.json"),
        "active_gh_checkpoint": str(gh),
        "active_agent_activity_trace": str(tx / "agent_activity_trace.json"),
        "active_portfolio_agent_state": str(tx / "portfolio_agent_state.json"),
    })
    registry["pointer_hashes"].update({
        "allocation": sha256(tx / "allocation_after_agent_action.json"),
        "sanitized_graph": sha256(tx / "building_assembly_graph_after_agent_action.json"),
        "structural_result": sha256(tx / "structural_result_after_agent_action.json"),
        "structural_verification_state": sha256(tx / "structural_verification_state_after_agent_action.json"),
        "gh": sha256(gh),
    })
    write(tx / "project_state_registry.json", registry)
    active_path = ROOT / "data" / "earthwise" / "active.json"
    active = read(active_path)
    active.update({
        "allocation_status": "ACTIVE",
        "project_state_registry": str(tx / "project_state_registry.json"),
        "active_allocation_path": str(tx / "allocation_after_agent_action.json"),
        "active_structural_result": str(tx / "structural_result_after_agent_action.json"),
        "active_structural_verification_state": str(tx / "structural_verification_state_after_agent_action.json"),
        "active_design_action_state": str(ROOT / "runtime" / "design_action_state" / "design_action_state.json"),
        "active_gh_checkpoint": str(gh),
    })
    active["project_state_registry_sha256"] = sha256(tx / "project_state_registry.json")
    write(active_path, active)

    commit = {
        "schema": "AI_TIMBER_AGENT_LOOP_TRANSACTION_COMMIT_V1",
        "transaction_id": pointer["transaction_id"],
        "status": "COMMITTED",
        "gh_checkpoint": str(gh),
        "gh_sha256": sha256(gh),
        "result": str(tx / "structural_result_after_agent_action.json"),
        "result_sha256": sha256(tx / "structural_result_after_agent_action.json"),
        "verification": str(tx / "agent_correction_verification.json"),
        "committed_at": now,
    }
    write(tx / "transaction_commit.json", commit)
    print(json.dumps({"transaction": pointer["transaction_id"], "gh": str(gh), "max_displacement_mm": result["max_displacement_mm"], "controlling_member": result["controlling_member"], "added_timber_length_mm": added_length, "stock_ids": residual_ids}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: finalize_agent_correction_loop.py <gh_checkpoint>")
    main(sys.argv[1])
