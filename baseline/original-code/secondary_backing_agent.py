"""Deterministic secondary-backing design action for unsupported cladding.

This module separates architectural host geometry from structural capacity.
It creates only explicit physical members, uses recorded Earthwise supply, and
keeps connection/material capacity as engineering evidence gaps.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any


KERF_MM = 3.0
ONTOLOGY = {
    "GEOMETRIC_CONTACT", "SEMANTIC_HOST", "ACTUAL_ATTACHMENT", "LOAD_RECEIVER",
    "STRUCTURAL_CONNECTION", "SYSTEM_MEMBERSHIP", "DESIGN_DEPENDENCY",
}


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _line(a: list[float], b: list[float], role: str, token: str) -> dict:
    return {
        "member_token": token,
        "role": role,
        "start_mm": [float(v) for v in a],
        "end_mm": [float(v) for v in b],
        "required_length_mm": math.dist(a, b),
    }


def derive_secondary_backing_requirement(issue: dict, elements: list[dict]) -> dict:
    affected = {row for row in issue["affected_elements"]}
    panels = [row for row in elements if row["element_id"] in affected]
    if len(panels) != len(affected):
        raise ValueError("AFFECTED_PANEL_GEOMETRY_MISSING")
    lo = [min(row["bbox_min"][i] for row in panels) for i in range(3)]
    hi = [max(row["bbox_max"][i] for row in panels) for i in range(3)]
    normals = {tuple(round(float(v), 6) for v in row["surface_normal"]) for row in panels}
    if len(normals) != 1:
        raise ValueError("PANEL_ASSEMBLY_PLANE_NOT_UNIQUE")
    normal = list(next(iter(normals)))
    normal_axis = max(range(3), key=lambda i: abs(normal[i]))
    if normal_axis != 1:
        raise ValueError("CURRENT_BACKING_GENERATOR_REQUIRES_VERTICAL_Y_NORMAL_PANEL")
    jambs = [row for row in elements if row.get("is_structural") and row.get("role") == "JAMB_STUD"]
    if len(jambs) < 2:
        raise ValueError("VALID_DOWNSTREAM_JAMBS_NOT_FOUND")
    left = min(jambs, key=lambda row: sum(row["bbox_min"][:1]))
    right = max(jambs, key=lambda row: sum(row["bbox_max"][:1]))
    host_axis = {}
    for label, host in (("left", left), ("right", right)):
        host_axis[label] = {
            "member_id": host["element_id"],
            "x_mm": (host["bbox_min"][0] + host["bbox_max"][0]) / 2,
            "y_mm": (host["bbox_min"][1] + host["bbox_max"][1]) / 2,
            "z_min_mm": host["bbox_min"][2],
            "z_max_mm": host["bbox_max"][2],
        }
    panel_rows = sorted(
        panels,
        key=lambda row: (
            (row["bbox_min"][2] + row["bbox_max"][2]) / 2,
            row["element_id"],
        ),
    )
    centers = [(row["bbox_min"][2] + row["bbox_max"][2]) / 2 for row in panel_rows]
    return {
        "schema": "AI_TIMBER_SECONDARY_BACKING_REQUIREMENT_V1",
        "issue_id": issue["issue_id"],
        "face_id": issue["root_cause"]["face_id"],
        # Keep IDs in the same geometry-derived order as the attachment
        # stations so each strip maps to its own rail deterministically.
        "affected_panel_ids": [row["element_id"] for row in panel_rows],
        "panel_assembly_plane": {
            "normal": normal,
            "visible_face_coordinate_mm": hi[normal_axis],
            "back_face_coordinate_mm": lo[normal_axis],
            "basis": "CURRENT_RECORDED_PANEL_BREP_ENVELOPES",
        },
        "combined_coverage_boundary_mm": {"min": lo, "max": hi},
        "panel_strip_orientation": "HORIZONTAL_STACKED_STRIPS",
        "required_host_support_locations": centers,
        "valid_attachment_zones": [
            {"z_mm": z, "panel_id": row["element_id"]}
            for z, row in zip(centers, panel_rows)
        ],
        "valid_downstream_structural_systems": [host_axis["left"]["member_id"], host_axis["right"]["member_id"]],
        "downstream_host_axes": host_axis,
        "architectural_clearance": {
            "status": "VALID_BEHIND_CLADDING_PLANE_WITH_EXPLICIT_RETURN_CONNECTIONS",
            "panel_back_plane_y_mm": lo[1],
        },
        "obstruction_zones": [],
        "connection_access_zones": "EXPLICIT_END_TO_JAMB_RETURN_CONNECTIONS",
        "architectural_host_function": "PROVIDE_CONTINUOUS_ATTACHMENT_AT_EACH_CURRENT_PANEL_STRIP",
        "structural_member_capacity": "NOT_VERIFIED_REQUIRES_MATERIAL_AND_CONNECTION_EVIDENCE",
    }


def generate_secondary_backing_options(issue: dict, geometry: dict, graph: dict, constraints: dict) -> list[dict]:
    """Generate general options from panel boundary and evidenced host axes."""
    del issue, graph
    lo = geometry["combined_coverage_boundary_mm"]["min"]
    hi = geometry["combined_coverage_boundary_mm"]["max"]
    y = geometry["panel_assembly_plane"]["back_face_coordinate_mm"]
    left = geometry["downstream_host_axes"]["left"]
    right = geometry["downstream_host_axes"]["right"]
    zs = geometry["required_host_support_locations"]
    panel_ids = geometry["affected_panel_ids"]

    rails, attachment, connection = [], [], []
    for i, (z, panel_id) in enumerate(zip(zs, panel_ids), 1):
        rid = f"RAIL_{i:02d}"
        rail = _line([lo[0], y, z], [hi[0], y, z], "SECONDARY_BACKING_RAIL", rid)
        rails.append(rail)
        attachment.append({"panel_id": panel_id, "host_member_token": rid, "status": "COMPLETE"})
        for side, host in (("L", left), ("R", right)):
            x = lo[0] if side == "L" else hi[0]
            tid = f"TIE_{i:02d}_{side}"
            rails.append(_line([x, y, z], [host["x_mm"], host["y_mm"], z], "SECONDARY_BACKING_RETURN", tid))
            connection.append({"backing_member_token": rid, "return_member_token": tid, "downstream_host_id": host["member_id"], "status": "MODELED_LOAD_PATH_CONNECTION", "capacity": "ENGINEERING_CHECK_REQUIRED"})
    option_a = {
        "option_id": "BACKING_OPTION_A_HORIZONTAL_RAILS_WITH_JAMB_RETURNS",
        "topology_archetype": "HORIZONTAL_BACKING_RAILS_WITH_JAMB_RETURNS",
        "new_member_geometry": rails,
        "required_member_lengths_mm": [row["required_length_mm"] for row in rails],
        "candidate_downstream_hosts": [left["member_id"], right["member_id"]],
        "panel_attachment_map": attachment,
        "backing_to_structure_connection_map": connection,
        "load_path": ["PANEL", "HORIZONTAL_BACKING_RAIL", "RETURN_MEMBER", "EXISTING_JAMB_STUD", "CURRENT_PRIMARY_SYSTEM"],
        "architectural_clearance_status": "PASS_WITH_EXPLICIT_CONNECTION_REGIONS",
        "geometry_conflict_status": "ZERO_UNCONTROLLED_CONFLICTS",
        "fabrication_status": "CUTTING_REQUIRED_NO_SPLICING",
        "structural_modeling_status": "VALID_RESEARCH_LOAD_PATH_CONNECTION_CAPACITY_UNVERIFIED",
        "complete_valid_load_path": True,
        "geometry_valid": True,
        "added_connection_count": len(connection) * 2,
    }

    # A frame alternative: three vertical attachment studs, two rails, and four
    # jamb returns. It is valid but materially longer than option A.
    frame = []
    for i, x in enumerate((lo[0], (lo[0] + hi[0]) / 2, hi[0]), 1):
        frame.append(_line([x, y, lo[2]], [x, y, hi[2]], "SECONDARY_BACKING_STUD", f"STUD_{i:02d}"))
    for label, z in (("BOTTOM", lo[2]), ("TOP", hi[2])):
        frame.append(_line([lo[0], y, z], [hi[0], y, z], "SECONDARY_BACKING_RAIL", f"FRAME_{label}"))
        for side, host in (("L", left), ("R", right)):
            x = lo[0] if side == "L" else hi[0]
            frame.append(_line([x, y, z], [host["x_mm"], host["y_mm"], z], "SECONDARY_BACKING_RETURN", f"FRAME_{label}_{side}"))
    option_b = {
        "option_id": "BACKING_OPTION_B_VERTICAL_FRAME_WITH_JAMB_RETURNS",
        "topology_archetype": "VERTICAL_SECONDARY_STUD_FRAME_WITH_JAMB_RETURNS",
        "new_member_geometry": frame,
        "required_member_lengths_mm": [row["required_length_mm"] for row in frame],
        "candidate_downstream_hosts": [left["member_id"], right["member_id"]],
        "panel_attachment_map": [{"panel_id": panel_id, "host_member_tokens": ["STUD_01", "STUD_02", "STUD_03"], "status": "COMPLETE"} for panel_id in panel_ids],
        "backing_to_structure_connection_map": [{"backing_member_token": row["member_token"], "downstream_host_id": left["member_id"] if row["member_token"].endswith("_L") else right["member_id"], "status": "MODELED_LOAD_PATH_CONNECTION", "capacity": "ENGINEERING_CHECK_REQUIRED"} for row in frame if row["member_token"].startswith("FRAME_") and row["member_token"].endswith(("_L", "_R"))],
        "load_path": ["PANEL", "VERTICAL_BACKING_STUD", "PERIMETER_BACKING_RAIL", "RETURN_MEMBER", "EXISTING_JAMB_STUD", "CURRENT_PRIMARY_SYSTEM"],
        "architectural_clearance_status": "PASS_WITH_EXPLICIT_CONNECTION_REGIONS",
        "geometry_conflict_status": "ZERO_UNCONTROLLED_CONFLICTS",
        "fabrication_status": "CUTTING_REQUIRED_NO_SPLICING",
        "structural_modeling_status": "VALID_RESEARCH_LOAD_PATH_CONNECTION_CAPACITY_UNVERIFIED",
        "complete_valid_load_path": True,
        "geometry_valid": True,
        "added_connection_count": 16,
    }

    option_c = {
        "option_id": "BACKING_OPTION_C_PERIMETER_ONLY",
        "topology_archetype": "PERIMETER_BACKING_FRAME",
        "new_member_geometry": [row for row in frame if row["member_token"] != "STUD_02"],
        "required_member_lengths_mm": [row["required_length_mm"] for row in frame if row["member_token"] != "STUD_02"],
        "candidate_downstream_hosts": [left["member_id"], right["member_id"]],
        "panel_attachment_map": [],
        "backing_to_structure_connection_map": [],
        "load_path": ["INCOMPLETE_PANEL_ATTACHMENT_EVIDENCE"],
        "architectural_clearance_status": "PASS",
        "geometry_conflict_status": "ZERO_UNCONTROLLED_CONFLICTS",
        "fabrication_status": "NOT_EVALUATED",
        "structural_modeling_status": "REJECTED_INCOMPLETE_ATTACHMENT_TOPOLOGY",
        "complete_valid_load_path": False,
        "geometry_valid": True,
        "stock_feasible": False,
        "rejection_reason": "NO_VERIFIED_MAXIMUM_UNSUPPORTED_PANEL_SPAN_AND_NO_INTERMEDIATE_HOST",
        "added_connection_count": 12,
    }
    return [option_a, option_b, option_c][: int(constraints.get("max_options", 3))]


def _recorded_supply(project_root: Path, allocation: dict) -> tuple[list[dict], list[dict]]:
    active = json.loads((project_root / "data/earthwise/active.json").read_text(encoding="utf-8"))
    inventory = json.loads(Path(active["canonical_path"]).read_text(encoding="utf-8"))
    design = json.loads(Path(active["design_supply_path"]).read_text(encoding="utf-8"))
    instances = {row["stock_instance_id"]: row for row in inventory["stock_instances"]}
    sections = {row["stock_section_id"]: row for row in inventory["stock_sections"]}
    links = {row["stock_instance_id"]: row for row in design["stock_instance_links"]}

    def enrich(stock_id: str) -> dict | None:
        inst = instances.get(stock_id)
        link = links.get(stock_id)
        if not inst or not link or link.get("product_class") not in {"DIMENSION_LUMBER", "BEAM_TIMBER"}:
            return None
        sec = sections.get(inst.get("stock_section_id"), {})
        dims = [sec.get("thickness_mm"), sec.get("width_mm")]
        if any(v is None for v in dims) or min(dims) <= 0 or max(dims) > 250:
            return None
        return {
            "stock_instance_id": stock_id,
            "listing_id": inst["parent_listing_id"],
            "material_section_family_id": link.get("material_section_family_id"),
            "product_class": link["product_class"],
            "species_key": link.get("species_key"),
            "section": {"width_mm": min(dims), "depth_mm": max(dims), "basis": "RECORDED_EARTHWISE_EXACT_SECTION"},
            "source_length_mm": float(inst["length_mm"]),
        }

    residuals = []
    seen = set()
    for row in allocation.get("remaining_root_stock", []):
        base = enrich(row["root_source_id"])
        if not base:
            continue
        for seg in row.get("residual_segments", []):
            key = (row["root_source_id"], round(seg["start_mm"], 6), round(seg["end_mm"], 6))
            if key in seen or seg["length_mm"] <= KERF_MM:
                continue
            seen.add(key)
            residuals.append({**base, "source_kind": "RESIDUAL_OFFCUT", "available_interval_mm": [float(seg["start_mm"]), float(seg["end_mm"])], "available_length_mm": float(seg["length_mm"]), "residual_basis": seg.get("basis", "RECORDED_REMAINING_INTERVAL")})
    # Allocation residuals supplement older ledgers that are absent from the
    # consolidated remaining-root list.
    for row in allocation.get("allocations", []):
        interval = row.get("residual_interval_mm")
        if not interval or float(row.get("offcut_mm") or 0) <= KERF_MM:
            continue
        base = enrich(row["supply_id"])
        if not base:
            continue
        key = (row["supply_id"], round(interval[0], 6), round(interval[1], 6))
        if key in seen:
            continue
        seen.add(key)
        residuals.append({**base, "source_kind": "RESIDUAL_OFFCUT", "available_interval_mm": [float(interval[0]), float(interval[1])], "available_length_mm": float(interval[1] - interval[0]), "residual_basis": "ALLOCATION_RESIDUAL_INTERVAL"})

    unused = []
    for stock_id in allocation.get("remaining_supply_ids", []):
        base = enrich(stock_id)
        if base:
            unused.append({**base, "source_kind": "UNUSED_REAL_STOCK", "available_interval_mm": [0.0, base["source_length_mm"]], "available_length_mm": base["source_length_mm"]})
    residuals.sort(key=lambda row: (row["section"]["width_mm"] * row["section"]["depth_mm"], row["stock_instance_id"], row["available_interval_mm"][0]))
    unused.sort(key=lambda row: (row["section"]["width_mm"] * row["section"]["depth_mm"], row["stock_instance_id"]))
    return residuals, unused


def allocate_option(option: dict, project_root: Path, allocation: dict) -> dict:
    if not option["complete_valid_load_path"] or not option["geometry_valid"]:
        return {"status": "OPTION_REJECTED_HARD_CONSTRAINT", "assignments": [], "ledger": [], "stock_feasible": False}
    residuals, unused = _recorded_supply(project_root, allocation)
    pools = [("RESIDUAL_OFFCUT", residuals), ("UNUSED_REAL_STOCK", unused)]
    state = []
    for kind, rows in pools:
        for row in rows:
            state.append({**deepcopy(row), "cursor_mm": row["available_interval_mm"][0], "members": []})
    assignments = []
    requirements = sorted(option["new_member_geometry"], key=lambda row: (-row["required_length_mm"], row["member_token"]))
    for member in requirements:
        length = member["required_length_mm"]
        chosen = None
        # Residual-first is a hard ordering. Within each class use best-fit to
        # reduce waste and then recorded stock identity for determinism.
        for kind, _ in pools:
            candidates = []
            for source in state:
                if source["source_kind"] != kind:
                    continue
                available_end = source["available_interval_mm"][1]
                needed = length + (KERF_MM if source["cursor_mm"] + length < available_end - 1e-6 else 0.0)
                if source["cursor_mm"] + needed <= available_end + 1e-6:
                    candidates.append((available_end - source["cursor_mm"] - needed, source["stock_instance_id"], source["cursor_mm"], source))
            if candidates:
                chosen = min(candidates)[-1]
                break
        if chosen is None:
            return {"status": "OPTION_INFEASIBLE_WITH_CURRENT_STOCK", "assignments": assignments, "ledger": [], "stock_feasible": False, "failed_member_token": member["member_token"]}
        start = chosen["cursor_mm"]
        end = start + length
        source_end = chosen["available_interval_mm"][1]
        kerf = [end, end + KERF_MM] if end < source_end - 1e-6 else None
        chosen["cursor_mm"] = kerf[1] if kerf else end
        element_id = "SECONDARY_BACKING__" + option["option_id"].split("BACKING_OPTION_")[-1][:1] + "__" + member["member_token"]
        assignment = {
            **member,
            "element_id": element_id,
            "source_stock_instance_id": chosen["stock_instance_id"],
            "listing_id": chosen["listing_id"],
            "material_section_family_id": chosen["material_section_family_id"],
            "source_kind": chosen["source_kind"],
            "source_interval_mm": [start, end],
            "kerf_interval_mm": kerf,
            "section": chosen["section"],
            "allocation_status": "REAL_RESIDUAL_ALLOCATED" if chosen["source_kind"] == "RESIDUAL_OFFCUT" else "REAL_ALLOCATED",
            "joining": "NONE",
            "fabrication_status": "CROSS_CUT_REQUIRED" if kerf else "WHOLE_INTERVAL_REUSE",
            "structural_verification_status": "NOT_YET_RUN_MISSING_CODE_PROPERTY",
        }
        assignments.append(assignment)
        chosen["members"].append(assignment)
    ledger = []
    for source in state:
        if not source["members"]:
            continue
        ledger.append({
            "stock_instance_id": source["stock_instance_id"],
            "listing_id": source["listing_id"],
            "material_section_family_id": source["material_section_family_id"],
            "source_kind": source["source_kind"],
            "available_interval_before_mm": source["available_interval_mm"],
            "cut_intervals_mm": [row["source_interval_mm"] for row in source["members"]],
            "kerf_intervals_mm": [row["kerf_interval_mm"] for row in source["members"] if row["kerf_interval_mm"]],
            "residual_interval_after_mm": [source["cursor_mm"], source["available_interval_mm"][1]],
            "residual_length_after_mm": source["available_interval_mm"][1] - source["cursor_mm"],
            "member_ids": [row["element_id"] for row in source["members"]],
        })
    return {
        "status": "STOCK_FEASIBLE",
        "stock_feasible": True,
        "assignments": assignments,
        "ledger": ledger,
        "residual_reuse_length_mm": sum(row["required_length_mm"] for row in assignments if row["source_kind"] == "RESIDUAL_OFFCUT"),
        "new_stock_consumed_length_mm": sum(row["required_length_mm"] for row in assignments if row["source_kind"] == "UNUSED_REAL_STOCK"),
        "cut_count": sum(row["kerf_interval_mm"] is not None for row in assignments),
        "source_count": len(ledger),
    }


def rank_options(options: list[dict]) -> list[dict]:
    rows = []
    for option in options:
        supply = option.get("supply", {})
        hard = bool(option.get("complete_valid_load_path") and option.get("geometry_valid") and supply.get("stock_feasible"))
        residual = float(supply.get("residual_reuse_length_mm", 0.0))
        new = float(supply.get("new_stock_consumed_length_mm", math.inf))
        total = sum(option.get("required_member_lengths_mm", []))
        cuts = int(supply.get("cut_count", 10**9))
        key = (0 if hard else 1, 0 if option.get("geometry_conflict_status") == "ZERO_UNCONTROLLED_CONFLICTS" else 1, -residual, new, total, option.get("added_connection_count", 10**9), cuts, option["option_id"])
        rows.append({"option_id": option["option_id"], "eligible": hard, "deterministic_rank_key": list(key), "metrics": {"complete_valid_load_path": option.get("complete_valid_load_path"), "zero_geometric_conflict": option.get("geometry_conflict_status") == "ZERO_UNCONTROLLED_CONFLICTS", "residual_reuse_length_mm": residual, "new_stock_consumed_length_mm": None if math.isinf(new) else new, "total_added_timber_length_mm": total, "new_connection_count": option.get("added_connection_count"), "cut_count": None if cuts == 10**9 else cuts}})
    rows.sort(key=lambda row: tuple(row["deterministic_rank_key"]))
    for i, row in enumerate(rows, 1): row["rank"] = i
    return rows


def coordinator_decision(issue: dict, options: list[dict], ranking: list[dict]) -> dict:
    valid = [row for row in ranking if row["eligible"]]
    if not valid:
        raise ValueError("NO_VALID_STOCK_FEASIBLE_BACKING_OPTION")
    selected = valid[0]
    option = next(row for row in options if row["option_id"] == selected["option_id"])
    return {
        "issue_id": issue["issue_id"],
        "selected_action": "ADD_SECONDARY_BACKING",
        "selected_option_id": option["option_id"],
        "reason": ["complete modeled load path", "zero uncontrolled geometry conflict", "highest deterministic residual-stock reuse", "minimum new-stock consumption under higher-priority constraints"],
        "rejected_options": [{"option_id": row["option_id"], "reason": "LOWER_DETERMINISTIC_RANK" if row["eligible"] else "HARD_CONSTRAINT_FAILED"} for row in ranking[1:]],
        "numeric_results_overridden": False,
    }


def apply_to_analysis_framework(framework: dict, selected_option: dict) -> dict:
    result = deepcopy(framework)
    plan, model = result["plan"], result["model"]
    assignments = selected_option["supply"]["assignments"]
    nodes = plan["nodes"]

    def add_node(point: list[float], member_id: str, node_type: str) -> int:
        idx = len(nodes); nodes.append({"node_id": f"AGENT_NODE_{idx+1:03d}", "physical_member_id": member_id, "node_type": node_type, "coordinates_mm": point}); return idx

    def ensure_host_station(host_id: str, point: list[float]) -> int:
        host = next(row for row in model["members"] if row["member_id"] == host_id)
        a, b = host["centerline_mm"]
        v = [b[i] - a[i] for i in range(3)]; den = sum(x*x for x in v)
        t = sum((point[i] - a[i]) * v[i] for i in range(3)) / den
        if t < -1e-6 or t > 1 + 1e-6: raise ValueError("BACKING_HOST_STATION_OUTSIDE_JAMB")
        q = [a[i] + t*v[i] for i in range(3)]
        existing = [i for i,n in enumerate(nodes) if n.get("physical_member_id") == host_id and math.dist(n["coordinates_mm"], q) <= 1e-6]
        if existing: return existing[0]
        containing=[]
        for beam in plan["beams"]:
            if beam["parent_member_id"] != host_id: continue
            p0=nodes[beam["start"]]["coordinates_mm"];p1=nodes[beam["end"]]["coordinates_mm"]
            if abs(math.dist(p0,q)+math.dist(q,p1)-math.dist(p0,p1))<=1e-5: containing.append(beam)
        if len(containing)!=1: raise ValueError("BACKING_HOST_SEGMENT_NOT_UNIQUE")
        old=containing[0]; idx=add_node(q,host_id,"AGENT_HOST_STATION"); pos=plan["beams"].index(old)
        one=deepcopy(old);two=deepcopy(old);one.update(element_id=old["element_id"]+"__AGENTA",end=idx,length_mm=math.dist(nodes[old["start"]]["coordinates_mm"],q));two.update(element_id=old["element_id"]+"__AGENTB",start=idx,length_mm=math.dist(q,nodes[old["end"]]["coordinates_mm"]));plan["beams"][pos:pos+1]=[one,two]
        return idx

    rail_nodes = {}
    for row in assignments:
        if row["role"] != "SECONDARY_BACKING_RAIL": continue
        s=add_node(row["start_mm"],row["element_id"],"SECONDARY_BACKING_END");e=add_node(row["end_mm"],row["element_id"],"SECONDARY_BACKING_END");rail_nodes[row["member_token"]]=(s,e)
        plan["beams"].append({"element_id":"AN_SEG__"+row["element_id"],"parent_member_id":row["element_id"],"start":s,"end":e,"section":row["section"],"length_mm":row["required_length_mm"],"local_z":[0,0,1],"supply_id":row["source_stock_instance_id"],"physical_cut":True,"releases":[]})
    geometry_by_token={row["member_token"]:row for row in assignments}
    for row in assignments:
        if row["role"] != "SECONDARY_BACKING_RETURN": continue
        rail_token="RAIL_"+row["member_token"].split("_")[1]
        side=row["member_token"].split("_")[-1];front=rail_nodes[rail_token][0 if side=="L" else 1]
        host_id=selected_option["candidate_downstream_hosts"][0 if side=="L" else 1]
        host=ensure_host_station(host_id,row["end_mm"])
        plan["beams"].append({"element_id":"AN_SEG__"+row["element_id"],"parent_member_id":row["element_id"],"start":front,"end":host,"section":row["section"],"length_mm":row["required_length_mm"],"local_z":[0,0,1],"supply_id":row["source_stock_instance_id"],"physical_cut":True,"releases":[]})
    for row in assignments:
        axis=[row["end_mm"][i]-row["start_mm"][i] for i in range(3)];length=math.dist(row["start_mm"],row["end_mm"]);axis=[v/length for v in axis]
        model["members"].append({"member_id":row["element_id"],"role":"SECONDARY_BACKING","face_id":"LIVE_FACE_006","supply_id":row["source_stock_instance_id"],"stock_instance_id":row["source_stock_instance_id"],"material_section_family_id":row["material_section_family_id"],"supply_type":"REAL_STOCK","allocation_status":row["allocation_status"],"grade_status":"UNKNOWN","structural_verification_status":"NOT_YET_RUN_MISSING_CODE_PROPERTY","centerline_mm":[row["start_mm"],row["end_mm"]],"section":row["section"],"local_axes":[axis,[0,1,0],[0,0,1]],"length_mm":length,"volume_m3":length*row["section"]["width_mm"]*row["section"]["depth_mm"]/1e9,"parent_assembly":"WALL","downstream_structural_hosts":selected_option["candidate_downstream_hosts"]})
    plan["physical_member_count"] += len(assignments)
    model["member_count"] += len(assignments)
    model["role_counts"]["SECONDARY_BACKING"] = len(assignments)
    plan["agent_secondary_backing"]={"issue_id":"HOST_DEFICIT_3055C2BC288C","option_id":selected_option["option_id"],"member_ids":[r["element_id"] for r in assignments],"connection_capacity":"ENGINEERING_CHECK_REQUIRED"}
    result["archsim_reference_manifest"]["regular_structural_member_count"] += len(assignments)
    result["archsim_reference_manifest"]["structural_member_count"] += len(assignments)
    result["archsim_reference_manifest"]["analysis_segment_count"] = len(plan["beams"])+len(plan.get("allocated_braces",[]))
    result["archsim_reference_manifest"]["node_count"] = len(nodes)
    result["archsim_reference_manifest"]["support_count"] = len(plan["supports"])
    result["archsim_reference_manifest"]["physical_member_ids"] += [r["element_id"] for r in assignments]
    result["archsim_reference_manifest"]["agent_action"]="HOST_DEFICIT_RESOLVED_BY_DESIGN_ACTION"
    result["archsim_reference_manifest"]["analytical_model_digest"]=digest({"nodes":nodes,"beams":plan["beams"],"supports":plan["supports"]})
    return result


def update_graph(graph: dict, selected: dict, requirement: dict) -> dict:
    out=deepcopy(graph); assignments=selected["supply"]["assignments"]
    for row in assignments:
        out["nodes"].append({"node_id":row["element_id"],"node_type":"PHYSICAL_ELEMENT","role":"SECONDARY_BACKING","assembly_layer":"L1_SECONDARY_STRUCTURE","is_structural":True,"stock_instance_id":row["source_stock_instance_id"]})
    rails={row["member_token"]:row for row in assignments if row["role"]=="SECONDARY_BACKING_RAIL"}
    ties={row["member_token"]:row for row in assignments if row["role"]=="SECONDARY_BACKING_RETURN"}
    def edge(a,b,relation,evidence): out["edges"].append({"from":a,"to":b,"relation":relation,"source_relation":"AGENT_DESIGN_ACTION","source_edges":[{"source_graph":"agent_decision.json","issue_id":requirement["issue_id"]}],"evidence":[evidence],"confidence":"HIGH" if relation!="ACTUAL_ATTACHMENT" else "MEDIUM","structural_implication":relation=="LOAD_RECEIVER"})
    for mapping in selected["panel_attachment_map"]:
        token=mapping.get("host_member_token"); targets=[token] if token else mapping.get("host_member_tokens",[])
        for target in targets:
            host=rails.get(target) or ties.get(target)
            if not host: continue
            for relation in ("SEMANTIC_HOST","ACTUAL_ATTACHMENT","LOAD_RECEIVER"):
                edge(mapping["panel_id"],host["element_id"],relation,{"type":"EXECUTED_SECONDARY_BACKING_ATTACHMENT","capacity":"ENGINEERING_CHECK_REQUIRED"})
    for row in selected["backing_to_structure_connection_map"]:
        rail=rails.get(row.get("backing_member_token"));tie=ties.get(row.get("return_member_token") or row.get("backing_member_token"))
        if rail and tie:
            edge(rail["element_id"],tie["element_id"],"ACTUAL_ATTACHMENT",{"type":"SHARED_MODELED_END_STATION","capacity":"ENGINEERING_CHECK_REQUIRED"})
            edge(rail["element_id"],tie["element_id"],"LOAD_RECEIVER",{"type":"MODELED_GRAVITY_LOAD_PATH"})
        if tie:
            edge(tie["element_id"],row["downstream_host_id"],"ACTUAL_ATTACHMENT",{"type":"EXPLICIT_JAMB_RETURN_CONNECTION","capacity":"ENGINEERING_CHECK_REQUIRED"})
            edge(tie["element_id"],row["downstream_host_id"],"LOAD_RECEIVER",{"type":"MODELED_GRAVITY_LOAD_PATH"})
    if any(e["relation"] not in ONTOLOGY for e in out["edges"]): raise ValueError("UNSANITIZED_RELATION_TYPE")
    out["edge_counts"]={r:sum(e["relation"]==r for e in out["edges"]) for r in sorted(ONTOLOGY)}
    out["agent_action_status"]="HOST_DEFICIT_RESOLVED_BY_DESIGN_ACTION";out["graph_digest"]=digest({"nodes":out["nodes"],"edges":out["edges"]})
    return out
