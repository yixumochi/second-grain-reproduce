"""Controlled length-change experiment. No scan registration or solver is run.

An observation describes a stock's original coordinate interval [0, length].
Shortening removes the far end; arbitrary defects, end-origin changes, installed
member movement and already fabricated secondary members are outside this model.
"""
from copy import deepcopy
import argparse
import json
import math
from pathlib import Path

from .replay import load_case, build_stage, assemble_stage, write
from .secondary_backing_agent import _recorded_supply, allocate_from_pool
from .verification import digest, validate, TOL, inside, require


def subtract(bounds, occupied):
    """Return free segments, rejecting overlapping reservations."""
    lo, hi = bounds
    cursor, free = lo, []
    for start, end in sorted(occupied):
        require(inside([start, end], bounds), 'RESERVATION_OUTSIDE_AVAILABLE_INTERVAL')
        require(start >= cursor - TOL, 'OVERLAPPING_RESERVATIONS')
        if start > cursor + TOL:
            free.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < hi - TOL:
        free.append([cursor, hi])
    return free


def available_pool(inputs):
    """Consolidated roots are authoritative over older duplicate residual records."""
    allocation = deepcopy(inputs['allocation_before'])
    root_ids = {r['root_source_id'] for r in allocation['remaining_root_stock']}
    allocation['allocations'] = [r for r in allocation['allocations'] if r['supply_id'] not in root_ids]
    used_ids = root_ids | {r['supply_id'] for r in allocation['allocations']}
    allocation['remaining_supply_ids'] = [sid for sid in allocation['remaining_supply_ids'] if sid not in used_ids]
    residual, unused = _recorded_supply(None, allocation, inventory=inputs['inventory'], design=inputs['design_supply'])
    pool = residual + unused
    by_stock = {}
    for row in pool:
        by_stock.setdefault(row['stock_instance_id'], []).append(row['available_interval_mm'])
    for bounds in by_stock.values():
        ordered = sorted(bounds)
        require(all(a[1] <= b[0] + TOL for a,b in zip(ordered, ordered[1:])), 'OVERLAPPING_AVAILABLE_STOCK')
    return pool


def reserve(pool, locked):
    result, accounted = [], set()
    for source in pool:
        occupied = []
        for row in locked:
            if row['source_stock_instance_id'] != source['stock_instance_id']:
                continue
            if inside(row['source_interval_mm'], source['available_interval_mm']):
                require(row['element_id'] not in accounted, 'AMBIGUOUS_LOCKED_INTERVAL')
                accounted.add(row['element_id'])
                occupied.append(row['source_interval_mm'])
                if row['kerf_interval_mm']:
                    occupied.append(row['kerf_interval_mm'])
        for bounds in subtract(source['available_interval_mm'], occupied):
            result.append({**deepcopy(source), 'available_interval_mm': bounds,
                           'available_length_mm': bounds[1]-bounds[0]})
    require(accounted == {r['element_id'] for r in locked}, 'LOCKED_MEMBER_NOT_IN_AVAILABLE_STOCK')
    return result


def make_ledger(pool, assignments):
    entries, accounted = [], set()
    for source in pool:
        rows = [r for r in assignments if r['source_stock_instance_id'] == source['stock_instance_id']
                and inside(r['source_interval_mm'], source['available_interval_mm'])]
        if not rows:
            continue
        rows.sort(key=lambda r: r['source_interval_mm'][0])
        require(not (accounted & {r['element_id'] for r in rows}), 'AMBIGUOUS_ASSIGNMENT_INTERVAL')
        accounted.update(r['element_id'] for r in rows)
        cuts = [r['source_interval_mm'] for r in rows]
        kerfs = [r['kerf_interval_mm'] for r in rows if r['kerf_interval_mm']]
        free = subtract(source['available_interval_mm'], cuts + kerfs)
        entries.append({'stock_instance_id': source['stock_instance_id'],
            'listing_id': source['listing_id'], 'material_section_family_id': source['material_section_family_id'],
            'source_kind': source['source_kind'], 'available_interval_before_mm': source['available_interval_mm'],
            'cut_intervals_mm': cuts, 'kerf_intervals_mm': kerfs,
            'residual_intervals_after_mm': free,
            'residual_length_after_mm': sum(b-a for a,b in free),
            'member_ids': [r['element_id'] for r in rows]})
    require(accounted == {r['element_id'] for r in assignments}, 'UNACCOUNTED_ASSIGNMENT')
    return entries


def classify(inputs, event):
    require(event.get('evidence_kind') == 'CONTROLLED_SYNTHETIC_OBSERVATION', 'ONLY_CONTROLLED_OBSERVATIONS_SUPPORTED')
    require(event.get('units') == 'mm', 'UNSUPPORTED_UNITS')
    require(event.get('change_scope') == 'STOCK_LENGTH_FROM_FIXED_ORIGIN', 'UNSUPPORTED_CHANGE_SCOPE')
    stock = next((r for r in inputs['inventory']['stock_instances'] if r['stock_instance_id'] == event['stock_id']), None)
    require(stock is not None, 'UNKNOWN_STOCK_ID')
    require(event.get('prior_inventory_digest') == digest(inputs['inventory']), 'STALE_OBSERVATION_BASE')
    if event.get('both_endpoints_observed') is not True:
        return 'INSUFFICIENT_EVIDENCE', stock, None
    length = event.get('length_mm')
    uncertainty = event.get('uncertainty_mm')
    require(isinstance(length, (int, float)) and not isinstance(length, bool)
            and math.isfinite(length) and length > 0, 'INVALID_OBSERVED_LENGTH')
    require(isinstance(uncertainty, (int, float)) and not isinstance(uncertainty, bool)
            and math.isfinite(uncertainty) and uncertainty >= 0, 'INVALID_UNCERTAINTY')
    # The first experiment accepts exact synthetic dimensions only. Real noisy
    # measurements need a separately calibrated interval/decision policy.
    if uncertainty > 0:
        return 'INSUFFICIENT_EVIDENCE', stock, None
    if 'observed_endpoints_mm' in event:
        points = event['observed_endpoints_mm']
        require(len(points) == 2 and all(len(p) == 3 for p in points), 'INVALID_ENDPOINTS')
        require(all(math.isfinite(v) for p in points for v in p), 'INVALID_ENDPOINTS')
        require(abs(math.dist(*points) - length) <= TOL, 'ENDPOINT_LENGTH_MISMATCH')
    if abs(length - stock['length_mm']) <= TOL:
        return 'NO_DIMENSION_CHANGE', stock, length
    return 'LENGTH_CHANGED', stock, length


def revised_inputs(inputs, stock_id, new_length, event):
    out = deepcopy(inputs)
    revision = str(inputs['inventory']['snapshot_revision']) + '::EXPERIMENT::' + digest(event)[:12]
    for row in out['inventory']['stock_instances']:
        row['snapshot_revision'] = revision
        if row['stock_instance_id'] == stock_id:
            row['length_mm'] = new_length
    for name in ['inventory', 'design_supply', 'allocation_before']:
        out[name]['snapshot_revision'] = revision
    # This is a derived availability view, not an overwrite of the frozen ledger.
    for row in out['allocation_before']['remaining_root_stock']:
        if row['root_source_id'] != stock_id:
            continue
        row['source_length_mm'] = new_length
        clipped = []
        for seg in row['residual_segments']:
            end = min(seg['end_mm'], new_length)
            if end > seg['start_mm'] + TOL:
                clipped.append({**seg, 'end_mm': end, 'length_mm': end-seg['start_mm']})
        row['residual_segments'] = clipped
        row['remaining_length_mm'] = sum(s['length_mm'] for s in clipped)
    for row in out['allocation_before']['allocations']:
        if row['supply_id'] != stock_id:
            continue
        row['source_length_mm'] = new_length
        if row.get('residual_interval_mm'):
            lo, hi = row['residual_interval_mm']
            end = min(hi, new_length)
            row['residual_interval_mm'] = [min(lo, end), end]
            row['offcut_mm'] = max(0, end-lo)
    out['allocation_before']['availability_revision'] = {
        'parent_allocation_digest': digest(inputs['allocation_before']),
        'event_digest': digest(event), 'scope': 'DERIVED_LENGTH_AND_RESIDUAL_METADATA_ONLY',
        'original_nested_cutting_records': 'HISTORICAL_UNCHANGED'}
    return out


def experiment(inputs, base, historical, manifest, event):
    require(base['input_digests'] == {k:digest(v) for k,v in inputs.items()}, 'BASE_STAGE_INPUT_MISMATCH')
    kind, stock, length = classify(inputs, event)
    old_assignments = base['selected_option']['supply']['assignments']
    report = {'schema': 'TIMBER_LENGTH_CHANGE_V1', 'event': deepcopy(event),
        'classification': kind, 'status': None,
        'prior_input_digest': digest(base['input_digests']),
        'prior_stage_digest': digest(base), 'baseline_fixture_modified': False,
        'solver_executed': False, 'diffcheck_executed': False,
        'engineering_approval': 'UNKNOWN', 'approved_for_construction': False,
        'historical_solver_values_reused': False,
        'affected_member_ids': [], 'changed_member_ids': [],
        'analysis_status': 'NO_NEW_SOLVER_EVIDENCE',
        'scope': 'Unfabricated secondary allocation A; exact controlled stock-length evidence only.'}
    if kind == 'INSUFFICIENT_EVIDENCE':
        report.update(status='NEEDS_EVIDENCE', proposed_inventory_revision=None,
                      reason='Endpoint coverage or exact dimensional evidence is insufficient; no inventory update.',
                      allocation_retained_digest=digest(old_assignments))
        return report, None, None
    if kind == 'NO_DIMENSION_CHANGE':
        report.update(status='UNCHANGED', proposed_inventory_revision=None,
                      allocation_retained_digest=digest(old_assignments),
                      unchanged_member_count=len(old_assignments),
                      reason='Length invariant under the supplied synthetic coordinate transform; no registration algorithm executed.')
        return report, None, None

    sid, old_length = stock['stock_instance_id'], stock['length_mm']
    report['length_change_mm'] = {'before': old_length, 'after': length, 'delta': length-old_length}
    pool_before = available_pool(inputs)
    # Only permit loss entirely inside recorded free material. Existing members,
    # unrecorded intervals and legacy consumed material are outside this repair.
    if length < old_length:
        free_tail = sum(max(0, min(old_length, r['available_interval_mm'][1]) - max(length, r['available_interval_mm'][0]))
                        for r in pool_before if r['stock_instance_id'] == sid)
        if abs(free_tail - (old_length-length)) > TOL:
            report.update(status='UNSUPPORTED_SCOPE', reason='SHORTENING_TOUCHES_EXISTING_OR_UNACCOUNTED_MATERIAL')
            return report, None, None
    changed_inputs = revised_inputs(inputs, sid, length, event)
    pool = available_pool(changed_inputs)
    affected = [r for r in old_assignments if r['source_stock_instance_id'] == sid
                and max(r['source_interval_mm'][1], (r['kerf_interval_mm'] or [0,0])[1]) > length + TOL]
    affected_ids = {r['element_id'] for r in affected}
    locked = [r for r in old_assignments if r['element_id'] not in affected_ids]
    report['affected_member_ids'] = sorted(affected_ids)
    report['stock_dependent_member_ids'] = [r['element_id'] for r in old_assignments if r['source_stock_instance_id'] == sid]
    selected = deepcopy(base['selected_option'])
    if affected:
        free_pool = reserve(pool, locked)
        partial_option = deepcopy(selected)
        partial_option['new_member_geometry'] = [r for r in selected['new_member_geometry']
            if r['member_token'] in {a['member_token'] for a in affected}]
        repair = allocate_from_pool(partial_option,
            [r for r in free_pool if r['source_kind'] == 'RESIDUAL_OFFCUT'],
            [r for r in free_pool if r['source_kind'] == 'UNUSED_REAL_STOCK'])
        if not repair['stock_feasible']:
            report.update(status='NO_FEASIBLE_REPAIR_FOUND', reason='RESIDUAL_FIRST_GREEDY_SEARCH_EXHAUSTED',
                          failed_member_token=repair['failed_member_token'], partial_repair_committed=False,
                          global_infeasibility_proven=False)
            return report, changed_inputs, None
        replacements = {r['element_id']: r for r in repair['assignments']}
        assignments = [deepcopy(replacements.get(r['element_id'], r)) for r in old_assignments]
    else:
        assignments = deepcopy(old_assignments)
    supply = selected['supply']
    supply.update(assignments=assignments, ledger=make_ledger(pool, assignments),
        status='STOCK_FEASIBLE', stock_feasible=True,
        residual_reuse_length_mm=sum(r['required_length_mm'] for r in assignments if r['source_kind']=='RESIDUAL_OFFCUT'),
        new_stock_consumed_length_mm=sum(r['required_length_mm'] for r in assignments if r['source_kind']=='UNUSED_REAL_STOCK'),
        cut_count=sum(r['kerf_interval_mm'] is not None for r in assignments))
    supply['source_count'] = len(supply['ledger'])
    decision = {'issue_id':base['decision']['issue_id'], 'selected_action':'REVISE_SECONDARY_BACKING_ALLOCATION',
                'selected_option_id':selected['option_id'],
                'reason':['Keep topology A and reserve every unaffected cut before residual-first greedy repair.'],
                'revision_policy':'KEEP_OPTION_A_AND_LOCK_UNAFFECTED_ASSIGNMENTS',
                'alternative_topologies_reconsidered':False, 'global_optimality_proven':False}
    transaction = 'CONTROLLED_CHANGE_' + digest(event)[:12]
    stage = assemble_stage(changed_inputs, transaction, base['requirement'], selected,
                           [selected], [], decision)
    verification = validate(changed_inputs, stage, historical, manifest, evidence_mode='revision')
    preserved = all(next(r for r in assignments if r['element_id']==old['element_id']) == old for old in locked)
    # Existing physical cutting records must not be rewritten by availability updates.
    cuts_preserved = all(a.get('pieces') == b.get('pieces') and a.get('pattern') == b.get('pattern')
                        for a,b in zip(inputs['allocation_before']['allocations'], changed_inputs['allocation_before']['allocations']))
    require(preserved and cuts_preserved, 'UNRELATED_ALLOCATIONS_CHANGED')
    before_by_id = {r['element_id']: r for r in old_assignments}
    changes = [{'member_id': r['element_id'], 'before': before_by_id[r['element_id']], 'after': r}
               for r in assignments if r != before_by_id[r['element_id']]]
    plan_changed = stage['framework_after']['plan'] != base['framework_after']['plan']
    numerical_fields_changed = any(c['before']['section'] != c['after']['section']
                                  or c['before']['material_section_family_id'] != c['after']['material_section_family_id']
                                  for c in changes)
    new_binding = {'input_digests': stage['input_digests'],
                   'framework_digest': digest(stage['framework_after']),
                   'loads_digest': digest(stage['loads_after']), 'transaction_id': transaction}
    report.update(status=('REALLOCATED' if affected else 'REVALIDATED') if verification['accepted_for_offline_replay'] else 'VALIDATION_FAILED',
        proposed_inventory_revision=changed_inputs['inventory']['snapshot_revision'],
        changed_member_ids=[c['member_id'] for c in changes], member_changes=changes,
        unchanged_member_count=len(assignments)-len(changes), locked_assignments_preserved=preserved,
        existing_physical_cuts_preserved=cuts_preserved,
        analysis_status='REQUIRES_NEW_SOLVE' if changes else 'NO_NEW_SOLVER_EVIDENCE',
        analysis_input_changed=plan_changed, section_or_material_family_changed=numerical_fields_changed,
        panel_load_values_changed=stage['loads_after']['load_objects'] != base['loads_after']['load_objects'],
        recomputation_scope={'allocation': 'AFFECTED_MEMBERS_ONLY', 'validation': 'FULL_NEW_STAGE',
                             'analysis_export': 'FULL_MODEL_REBUILT', 'solver': 'NOT_EXECUTED'},
        new_solver_request_binding=new_binding, new_solver_request_digest=digest(new_binding),
        verification=verification,
        metrics={'member_count':len(assignments), 'required_length_before_mm':sum(r['required_length_mm'] for r in old_assignments),
                 'required_length_after_mm':sum(r['required_length_mm'] for r in assignments),
                 'kerf_before_mm':sum(3 for r in old_assignments if r['kerf_interval_mm']),
                 'kerf_after_mm':sum(3 for r in assignments if r['kerf_interval_mm']),
                 'residual_reuse_after_mm':supply['residual_reuse_length_mm'],
                 'unused_stock_use_after_mm':supply['new_stock_consumed_length_mm'],
                 'discarded_tail_mm':max(0,old_length-length)})
    return report, changed_inputs, stage


def scenarios(inputs, base):
    assignment = base['selected_option']['supply']['assignments'][0]
    sid = assignment['source_stock_instance_id']
    stock = next(r for r in inputs['inventory']['stock_instances'] if r['stock_instance_id']==sid)
    length = stock['length_mm']
    common = {'stock_id':sid, 'prior_inventory_digest':digest(inputs['inventory']), 'units':'mm',
        'change_scope':'STOCK_LENGTH_FROM_FIXED_ORIGIN', 'evidence_kind':'CONTROLLED_SYNTHETIC_OBSERVATION',
        'both_endpoints_observed':True, 'uncertainty_mm':0.0}
    return {
        'coordinate_only':{**common, 'length_mm':length,
            'observed_endpoints_mm':[[100,200,300], [100,200+length,300]],
            'construction':'Known 90-degree rotation and translation of two synthetic endpoints; not estimated.'},
        'shortened':{**common, 'length_mm':assignment['source_interval_mm'][1]-10},
        'missing_endpoint':{**common, 'both_endpoints_observed':False, 'length_mm':None}}


def run(case, output):
    inputs, historical, manifest = load_case(case)
    before_digest = digest(inputs)
    base = build_stage(inputs, manifest['transaction_id'])
    require(validate(inputs,base,historical,manifest)['accepted_for_offline_replay'], 'INVALID_BASELINE')
    results = []
    for name, event in scenarios(inputs,base).items():
        report, revised, stage = experiment(inputs,base,historical,manifest,event)
        report['scenario'] = name
        folder = output / name
        write(folder / 'observation.json', event)
        write(folder / 'report.json', report)
        if revised:
            write(folder / 'revised-inputs.json', revised)
        if stage:
            for key in ['selected_option','decision','allocation_after','framework_after','loads_after','graph_after']:
                write(folder / (key+'.json'), stage[key])
            write(folder / 'solver-request.json', report['new_solver_request_binding'])
        write(folder / 'run-status.json', {'status':report['status'], 'event_digest':digest(event),
              'report_digest':digest(report), 'stage_available':stage is not None, 'solver_executed':False})
        results.append(report)
    require(before_digest == digest(inputs), 'BASELINE_MUTATED')
    load_case(case)  # Recheck source bytes, including all frozen historical fixtures.
    summary = {'schema':'TIMBER_CHANGE_EXPERIMENT_V1','controlled_not_measured':True,
               'frozen_fixture_hashes_verified':True, 'scenarios':results}
    write(output / 'summary.json', summary)
    from .change_report import render
    render(output, summary)
    print(json.dumps([{'scenario':r['scenario'],'status':r['status'],
                      'changed_members':len(r['changed_member_ids'])} for r in results],indent=2))
    return 0 if [r['status'] for r in results] == ['UNCHANGED','REALLOCATED','NEEDS_EVIDENCE'] else 1


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, default=root/'case')
    parser.add_argument('--output', type=Path, default=root/'results'/'change-experiment')
    args = parser.parse_args()
    return run(args.case,args.output)
