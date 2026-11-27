"""Independent checks for the bounded rail/return replay; no solver is invoked."""
from collections import Counter, defaultdict, deque
from hashlib import sha256
import json
import math

TOL = 1e-5  # Numerical consistency tolerance in mm, not a fabrication tolerance.

def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def close(a, b):
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a) - float(b)) <= TOL

def interval(value):
    if len(value) != 2 or not all(math.isfinite(float(v)) for v in value) or value[1] < value[0]:
        raise ValueError('INVALID_INTERVAL')
    return float(value[0]), float(value[1])

def inside(segment, container):
    a, b = interval(segment)
    lo, hi = interval(container)
    return a >= lo - TOL and b <= hi + TOL

def require(condition, code):
    if not condition:
        raise ValueError(code)

def unique(rows, key):
    result = {r[key]: r for r in rows}
    require(len(result) == len(rows), 'DUPLICATE_' + key.upper())
    return result

def validate(inputs, stage, historical, manifest, *, evidence_mode='frozen'):
    if evidence_mode not in {'frozen', 'revision'}:
        raise ValueError('UNKNOWN_EVIDENCE_MODE')
    checks = []
    def check(name, function):
        try:
            details = function()
            checks.append({'check': name, 'status': 'PASS', 'evidence': details})
        except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError, StopIteration) as exc:
            checks.append({'check': name, 'status': 'FAIL', 'reason': str(exc) or type(exc).__name__})

    selected = stage['selected_option']
    assignments = selected['supply']['assignments']
    ledger = selected['supply']['ledger']

    def binding():
        current = {k: digest(v) for k, v in inputs.items()}
        require(stage['input_digests'] == current, 'STALE_STAGE_INPUT_BINDING')
        return {'input_count': len(current), 'input_digest': digest(current)}

    def revisions():
        expected = inputs['inventory']['snapshot_revision']
        require(inputs['design_supply']['snapshot_revision'] == expected, 'DESIGN_SUPPLY_SNAPSHOT_MISMATCH')
        require(inputs['allocation_before']['snapshot_revision'] == expected, 'ALLOCATION_SNAPSHOT_MISMATCH')
        for key in ['geometry_revision', 'demand_revision']:
            require(inputs['loads_before'][key] == inputs['allocation_before'][key], 'LOAD_' + key.upper() + '_MISMATCH')
        require(inputs['framework_before']['model']['geometry_revision'] == inputs['allocation_before']['geometry_revision'], 'MODEL_GEOMETRY_REVISION_MISMATCH')
        return {'snapshot_revision': expected}

    def geometry():
        wanted = unique(selected['new_member_geometry'], 'member_token')
        actual = unique(assignments, 'member_token')
        unique(assignments, 'element_id')
        require(set(wanted) == set(actual), 'MEMBER_ASSIGNMENT_SET_MISMATCH')
        for token, row in actual.items():
            length = math.dist(row['start_mm'], row['end_mm'])
            require(length > TOL and close(length, row['required_length_mm']), 'MEMBER_GEOMETRY_LENGTH_MISMATCH:' + token)
            for field in ['start_mm', 'end_mm', 'required_length_mm', 'role']:
                require(row[field] == wanted[token][field], 'ASSIGNED_GEOMETRY_CHANGED:' + token)
            require(close(interval(row['source_interval_mm'])[1] - interval(row['source_interval_mm'])[0], length), 'CUT_LENGTH_MISMATCH:' + token)
        return {'members': len(assignments), 'scope': 'Recorded centerlines only; no solid collision or capacity check.'}

    def stock():
        stocks = unique(inputs['inventory']['stock_instances'], 'stock_instance_id')
        sections = unique(inputs['inventory']['stock_sections'], 'stock_section_id')
        links = unique(inputs['design_supply']['stock_instance_links'], 'stock_instance_id')
        roots = {r['root_source_id']: r for r in inputs['allocation_before']['remaining_root_stock']}
        legacy = {r['supply_id']: r for r in inputs['allocation_before']['allocations']}
        for row in assignments:
            sid = row['source_stock_instance_id']
            require(sid in stocks and sid in links, 'UNKNOWN_STOCK_ID:' + sid)
            inst = stocks[sid]
            require(inst['snapshot_revision'] == inputs['inventory']['snapshot_revision'], 'STOCK_SNAPSHOT_MISMATCH:' + sid)
            require(links[sid]['product_class'] in {'DIMENSION_LUMBER', 'BEAM_TIMBER'}, 'UNSUPPORTED_STOCK_CLASS:' + sid)
            require(inside(row['source_interval_mm'], [0, inst['length_mm']]), 'CUT_OUTSIDE_CURRENT_STOCK:' + sid)
            sec = sections[inst['stock_section_id']]
            require(all(close(a,b) for a,b in zip(sorted([row['section']['width_mm'], row['section']['depth_mm']]), sorted([sec['width_mm'],sec['thickness_mm']]))), 'SECTION_MISMATCH:' + sid)
            require(row['listing_id'] == inst['parent_listing_id'], 'LISTING_ID_MISMATCH:' + sid)
            require(row['material_section_family_id'] == links[sid]['material_section_family_id'], 'FAMILY_MISMATCH:' + sid)
            require(row['joining'] == 'NONE', 'JOINING_NOT_SUPPORTED')
            for before in [roots.get(sid), legacy.get(sid)]:
                if before and before.get('source_length_mm') is not None:
                    require(close(before['source_length_mm'], inst['length_mm']), 'STOCK_LENGTH_CHANGED_REQUIRES_REALLOCATION:' + sid)
        return {'source_count': len({r['source_stock_instance_id'] for r in assignments}), 'evidence': 'Snapshot identities and seller dimensions; no physical grading inferred.'}

    def accounting():
        by_member = unique(assignments, 'element_id')
        seen = []
        global_segments = defaultdict(list)
        roots = {r['root_source_id']: r for r in inputs['allocation_before']['remaining_root_stock']}
        legacy = {r['supply_id']: r for r in inputs['allocation_before']['allocations']}
        unused = set(inputs['allocation_before']['remaining_supply_ids'])
        stocks = {r['stock_instance_id']: r for r in inputs['inventory']['stock_instances']}
        for entry in ledger:
            sid = entry['stock_instance_id']
            bounds = entry['available_interval_before_mm']
            start, end = interval(bounds)
            require(sid in stocks, 'UNKNOWN_LEDGER_STOCK:' + sid)
            require(inside(bounds, [0, stocks[sid]['length_mm']]), 'LEDGER_OUTSIDE_STOCK:' + sid)
            if entry['source_kind'] == 'RESIDUAL_OFFCUT':
                root = roots.get(sid)
                allowed = [[r['start_mm'], r['end_mm']] for r in root.get('residual_segments', [])] if root else []
                if not root and legacy.get(sid, {}).get('residual_interval_mm'):
                    allowed = [legacy[sid]['residual_interval_mm']]
                require(any(inside(bounds, permitted) for permitted in allowed), 'INTERVAL_NOT_AVAILABLE_BEFORE:' + sid)
            else:
                require(entry['source_kind'] == 'UNUSED_REAL_STOCK' and sid in unused, 'UNAVAILABLE_UNUSED_STOCK:' + sid)
            require(len(entry['member_ids']) == len(entry['cut_intervals_mm']), 'LEDGER_MEMBER_CUT_COUNT_MISMATCH')
            kerfs = []
            for mid, cut in zip(entry['member_ids'], entry['cut_intervals_mm']):
                require(mid in by_member, 'UNKNOWN_LEDGER_MEMBER:' + mid)
                row = by_member[mid]
                require(row['source_stock_instance_id'] == sid and row['source_interval_mm'] == cut, 'LEDGER_ASSIGNMENT_MISMATCH:' + mid)
                require(row['source_kind'] == entry['source_kind'], 'LEDGER_SOURCE_KIND_MISMATCH')
                if row['kerf_interval_mm'] is not None:
                    kerf = row['kerf_interval_mm']
                    require(close(kerf[0], cut[1]) and close(kerf[1]-kerf[0], 3.0), 'KERF_MISMATCH:' + mid)
                    kerfs.append(kerf)
                seen.append(mid)
            require(kerfs == entry['kerf_intervals_mm'], 'LEDGER_KERF_MISMATCH')
            residuals = (entry['residual_intervals_after_mm'] if 'residual_intervals_after_mm' in entry
                         else [entry['residual_interval_after_mm']])
            segments = entry['cut_intervals_mm'] + kerfs + residuals
            segments = sorted(interval(x) for x in segments)
            require(all(inside(x, bounds) for x in segments), 'LEDGER_SEGMENT_OUT_OF_BOUNDS:' + sid)
            require(all(a[1] <= b[0] + TOL for a,b in zip(segments,segments[1:])), 'OVERLAPPING_CUTS_OR_KERFS:' + sid)
            require(close(sum(b-a for a,b in segments), end-start), 'LENGTH_NOT_CONSERVED:' + sid)
            require(close(entry['residual_length_after_mm'], sum(b-a for a,b in residuals)), 'RESIDUAL_LENGTH_MISMATCH')
            global_segments[sid].extend(entry['cut_intervals_mm'] + kerfs)
        require(Counter(seen) == Counter(by_member.keys()), 'MEMBERS_NOT_ACCOUNTED_EXACTLY_ONCE')
        for sid, segments in global_segments.items():
            segments = sorted(segments)
            require(all(a[1] <= b[0] + TOL for a,b in zip(segments,segments[1:])), 'CROSS_LEDGER_OVERLAP:' + sid)
        return {'ledger_entries': len(ledger), 'cuts': len(seen), 'kerf_mm': 3.0}

    def graph():
        document = stage['graph_after']
        nodes = unique(document['nodes'], 'node_id')
        adjacency = defaultdict(set)
        for edge in document['edges']:
            require(edge['from'] in nodes and edge['to'] in nodes, 'DANGLING_GRAPH_REFERENCE')
            if edge['relation'] == 'LOAD_RECEIVER':
                adjacency[edge['from']].add(edge['to'])
        hosts = set(stage['requirement']['valid_downstream_structural_systems'])
        by_token = {r['member_token']: r['element_id'] for r in assignments}
        panel_ids = stage['requirement']['affected_panel_ids']
        mappings = unique(selected['panel_attachment_map'], 'panel_id')
        require(set(mappings) == set(panel_ids), 'PANEL_ATTACHMENT_SET_MISMATCH')
        for panel in panel_ids:
            expected = by_token[mappings[panel]['host_member_token']]
            require(expected in adjacency[panel], 'MISSING_PANEL_RECEIVER:' + panel)
            visited, queue = set(), deque([panel])
            while queue:
                current = queue.popleft()
                if current in visited: continue
                visited.add(current)
                queue.extend(adjacency[current] - visited)
            require(bool(visited & hosts), 'NO_DECLARED_PATH_TO_EXISTING_HOST:' + panel)
        return {'affected_panels_with_declared_paths': len(panel_ids), 'connection_capacity': 'UNKNOWN'}

    def framework():
        before, after = inputs['framework_before'], stage['framework_after']
        plan = after['plan']
        require(plan['supports'] == before['plan']['supports'], 'SUPPORTS_CHANGED')
        members = unique(after['model']['members'], 'member_id')
        original = unique(before['model']['members'], 'member_id')
        require(all(members.get(k) == v for k,v in original.items()), 'EXISTING_PHYSICAL_MEMBER_CHANGED')
        require(set(members)-set(original) == {r['element_id'] for r in assignments}, 'ANALYSIS_MEMBER_SET_MISMATCH')
        beams = defaultdict(list)
        for beam in plan['beams']:
            s,e = beam['start'], beam['end']
            require(isinstance(s,int) and isinstance(e,int) and 0 <= s < len(plan['nodes']) and 0 <= e < len(plan['nodes']), 'INVALID_ANALYSIS_NODE_INDEX')
            beams[beam['parent_member_id']].append(beam)
        for row in assignments:
            mid = row['element_id']
            require(len(beams[mid]) == 1, 'ADDED_MEMBER_NOT_ANALYTICALLY_REPRESENTED:' + mid)
            beam = beams[mid][0]
            endpoints = [plan['nodes'][beam[k]]['coordinates_mm'] for k in ['start','end']]
            require(all(math.dist(a,b) <= TOL for a,b in zip(endpoints,[row['start_mm'],row['end_mm']])), 'ANALYSIS_ENDPOINT_MISMATCH:' + mid)
            require(beam['supply_id'] == row['source_stock_instance_id'], 'ANALYSIS_STOCK_REFERENCE_MISMATCH')
            require(beam['section'] == row['section'], 'ANALYSIS_SECTION_MISMATCH')
        return {'added_members': len(assignments), 'nodes': len(plan['nodes']), 'supports': len(plan['supports']), 'solver_executed': False}

    def loads():
        panels = unique(stage['panels_after']['panels'], 'panel_id')
        before = unique(inputs['panels_before']['panels'], 'panel_id')
        require(set(panels) == set(before), 'PANEL_SET_CHANGED')
        objects = stage['loads_after']['load_objects']
        unique(objects, 'load_id')
        by_panel = defaultdict(list)
        members = {r['member_id'] for r in stage['framework_after']['model']['members']}
        for row in objects:
            require(row['panel_id'] in panels, 'UNKNOWN_PANEL_LOAD')
            require(row['physical_member_id'] in members, 'LOAD_RECEIVER_NOT_IN_ANALYSIS')
            by_panel[row['panel_id']].append(row)
        unresolved, total = 0.0, 0.0
        for pid, panel in panels.items():
            require(close(panel['self_weight_kN'], before[pid]['self_weight_kN']), 'PANEL_WEIGHT_CHANGED:' + pid)
            weight = float(panel['self_weight_kN'])
            total += weight
            actual = by_panel[pid]
            if panel['load_path_status'] == 'LOAD_PATH_RESOLVED':
                require(actual and all(r['physical_member_id'] in panel['receiving_member_ids'] for r in actual), 'PANEL_LOAD_MISSING_OR_MISDIRECTED:' + pid)
                force = [sum(r['force_kN'][i] for r in actual) for i in range(3)]
                require(close(force[0],0) and close(force[1],0) and close(force[2],-weight), 'PANEL_LOAD_NOT_CONSERVED:' + pid)
            else:
                unresolved += weight
                require(not actual, 'UNRESOLVED_PANEL_HAS_APPLIED_LOAD')
        require(close(stage['loads_after']['unresolved_weight_kN'], unresolved), 'UNRESOLVED_LOAD_TOTAL_MISMATCH')
        require(close(stage['loads_after']['resolved_weight_kN'], total-unresolved), 'RESOLVED_LOAD_TOTAL_MISMATCH')
        require(close(unresolved,0), 'UNRESOLVED_PANEL_LOAD_REMAINS')
        return {'panels': len(panels), 'applied_weight_kN': total-unresolved, 'unapplied_weight_kN': unresolved}

    def existing_allocations():
        after = dict(stage['allocation_after'])
        for key in ['agent_action','agent_action_digest','allocation_status']:
            after.pop(key, None)
        before = dict(inputs['allocation_before'])
        for key in ['agent_action','agent_action_digest','allocation_status']:
            before.pop(key, None)
        require(digest(after) == digest(before), 'EXISTING_ALLOCATION_CHANGED')
        require(stage['allocation_after']['agent_action']['assignments'] == assignments, 'ALLOCATION_ASSIGNMENT_MISMATCH')
        require(stage['allocation_after']['agent_action']['cutting_ledger'] == ledger, 'ALLOCATION_LEDGER_MISMATCH')
        require(stage['allocation_after']['agent_action_digest'] == digest(stage['allocation_after']['agent_action']), 'STALE_ALLOCATION_ACTION_DIGEST')
        return {'existing_allocation_content_preserved': True}

    def archive_binding():
        for name, value in inputs.items():
            expected = manifest['files']['inputs/' + name + '.json']['semantic_sha256']
            require(digest(value) == expected, 'HISTORICAL_RESULT_NOT_APPLICABLE_TO_CHANGED_INPUT:' + name)
        archived_result = historical['structural_result']
        require(digest(archived_result) == manifest['files']['historical/structural_result.json']['semantic_sha256'], 'HISTORICAL_RESULT_CONTENT_CHANGED')
        require(archived_result['transaction_id'] == manifest['transaction_id'], 'HISTORICAL_TRANSACTION_MISMATCH')
        require(stage['framework_after']['plan'] == historical['framework_after']['plan'], 'REPLAY_PLAN_DIFFERS_FROM_ARCHIVE')
        require(stage['loads_after'] == historical['loads_after'], 'REPLAY_LOADS_DIFFER_FROM_ARCHIVE')
        return {'association': 'RECORDED_FIXTURE_ONLY', 'solver_run_binding': 'UNKNOWN', 'solver_executed_now': False}

    for name, fn in [('input_binding',binding), ('revision_consistency',revisions),
                     ('centerline_geometry',geometry), ('stock_identity_dimensions',stock),
                     ('cutting_ledger',accounting), ('declared_load_paths',graph),
                     ('analysis_input_consistency',framework), ('panel_load_conservation',loads),
                     ('existing_allocations',existing_allocations), ('historical_association',archive_binding)]:
        if name == 'historical_association' and evidence_mode == 'revision':
            checks.append({'check': name, 'status': 'NOT_APPLICABLE',
                           'reason': 'New scenario revision; archived solver values are not carried forward.'})
        else:
            check(name, fn)
    checks.extend({'check': name, 'status': 'UNKNOWN', 'reason': reason} for name, reason in [
        ('live_structural_analysis','Historical outputs only; no Rhino/Karamba execution in this replay.'),
        ('material_capacity','Physical condition, grade and design strength not verified.'),
        ('connection_capacity','Declared graph paths do not establish connection resistance.'),
        ('foundation_design','No foundation verification performed.'),
        ('solid_geometry_clearance','Centerline consistency does not verify fabrication clearances.')])
    failures = [r for r in checks if r['status'] == 'FAIL']
    return {'schema': 'TIMBER_BASELINE_VERIFICATION_V1',
            'offline_replay_status': 'FAIL' if failures else 'PASS',
            'accepted_for_offline_replay': not failures,
            'engineering_approval': 'UNKNOWN', 'approved_for_construction': False,
            'checks': checks,
            'metrics': {'added_members': len(assignments), 'stock_sources': len(ledger),
                        'added_length_mm': sum(r['required_length_mm'] for r in assignments)}}
