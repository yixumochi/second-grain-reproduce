"""Recompute allocation/graph/load inputs, then independently verify them offline."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

from .secondary_backing_agent import (allocate_option, apply_to_analysis_framework,
    coordinator_decision, derive_secondary_backing_requirement, generate_secondary_backing_options,
    rank_options, update_graph)
from .verification import digest, validate

INPUT_NAMES = ['inventory', 'design_supply', 'allocation_before', 'elements', 'action',
               'graph_before', 'panels_before', 'framework_before', 'loads_before']
HISTORICAL_NAMES = ['requirement', 'options', 'decision', 'ledger', 'graph_after',
                    'transfer_after', 'framework_after', 'loads_after', 'structural_result']

def reject_constant(value):
    raise ValueError('NON_STANDARD_JSON_NUMBER:' + value)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=reject_constant)

def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def load_case(case):
    case = Path(case)
    manifest = read(case / 'manifest.json')
    # Verify frozen evidence bytes before loading them. Hashes are local provenance,
    # not proof that the original structural solution used these inputs.
    for relative, info in manifest['files'].items():
        file = case / relative
        if not file.is_file():
            raise ValueError('MISSING_FIXTURE_FILE:' + relative)
        if sha256(file.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('FIXTURE_HASH_MISMATCH:' + relative)
    inputs = {name: read(case / 'inputs' / (name + '.json')) for name in INPUT_NAMES}
    historical = {name: read(case / 'historical' / (name + '.json')) for name in HISTORICAL_NAMES}
    return inputs, historical, manifest

def build_stage(inputs, transaction_id):
    issues = inputs['action']['detected_issues']
    if len(issues) != 1 or issues[0]['issue_type'] != 'MISSING_HOST_CLADDING':
        raise ValueError('BASELINE_REQUIRES_ONE_MISSING_HOST_CLADDING_ISSUE')
    issue = issues[0]
    requirement = derive_secondary_backing_requirement(issue, inputs['elements']['elements'])
    options = generate_secondary_backing_options(issue, requirement, inputs['graph_before'], {'max_options': 3})
    for option in options:
        option['supply'] = allocate_option(option, None, inputs['allocation_before'],
            inventory=inputs['inventory'], design=inputs['design_supply'])
        option['stock_feasible'] = option['supply']['stock_feasible']
    ranking = rank_options(options)
    decision = coordinator_decision(issue, options, ranking)
    selected = next(o for o in options if o['option_id'] == decision['selected_option_id'])
    return assemble_stage(inputs, transaction_id, requirement, selected, options, ranking, decision)


def assemble_stage(inputs, transaction_id, requirement, selected, options, ranking, decision):
    """Assemble an explicitly allocated option without choosing stock again."""
    issue = inputs['action']['detected_issues'][0]
    allocation = deepcopy(inputs['allocation_before'])
    allocation['agent_action'] = {
        'transaction_id': transaction_id, 'issue_id': issue['issue_id'],
        'selected_option_id': selected['option_id'], 'assignments': selected['supply']['assignments'],
        'cutting_ledger': selected['supply']['ledger'], 'joining': 'NONE',
        'existing_allocations_modified': False}
    allocation['agent_action_digest'] = digest(allocation['agent_action'])
    allocation['allocation_status'] = 'STAGED_PENDING_INDEPENDENT_CHECKS'
    graph = update_graph(inputs['graph_before'], selected, requirement)
    framework = apply_to_analysis_framework(inputs['framework_before'], selected)
    by_token = {r['member_token']: r for r in selected['supply']['assignments']}
    rail_by_panel = {r['panel_id']: by_token[r['host_member_token']] for r in selected['panel_attachment_map']}
    panels = deepcopy(inputs['panels_before'])
    loads = deepcopy(inputs['loads_before'])
    for row in panels['panels']:
        backing = rail_by_panel.get(row['panel_id'])
        if not backing: continue
        centroid = [(backing['start_mm'][i] + backing['end_mm'][i]) / 2 for i in range(3)]
        row.update(
            host_system_id='SECONDARY_BACKING_SYSTEM::' + requirement['face_id'],
            receiving_member_ids=[backing['element_id']],
            transfer_archetype='DECLARED_PANEL_TO_SECONDARY_BACKING_TO_JAMB_LOAD_PATH',
            load_distribution_method='PANEL_SELF_WEIGHT_TO_BACKING_RAIL_AT_PANEL_CENTROID',
            geometry_evidence=[{'type':'EXECUTED_BACKING_RAIL_BEHIND_PANEL','backing_member_id':backing['element_id'],'contact_coordinates_mm':centroid}],
            semantic_evidence=[{'type':'EXPLICIT_AGENT_DESIGN_ACTION','issue_id':issue['issue_id']}],
            attachment_capacity_status='ENGINEERING_CHECK_REQUIRED',
            load_path_status='LOAD_PATH_RESOLVED', evidence_gaps=['CONNECTION_CAPACITY_NOT_VERIFIED'])
        loads['load_objects'].append({
            'load_id':'PANEL_DL::' + row['panel_id'], 'panel_id':row['panel_id'],
            'physical_member_id':backing['element_id'], 'force_kN':[0.0,0.0,-float(row['self_weight_kN'])],
            'contact_coordinates_mm':centroid, 'load_case':'DL_STRUCTURAL_TIMBER',
            'distribution_method':'PANEL_SELF_WEIGHT_TO_BACKING_RAIL_AT_PANEL_CENTROID',
            'attachment_capacity_status':'ENGINEERING_CHECK_REQUIRED'})
    resolved = [r for r in panels['panels'] if r['load_path_status'] == 'LOAD_PATH_RESOLVED']
    unresolved = [r for r in panels['panels'] if r['load_path_status'] != 'LOAD_PATH_RESOLVED']
    panels['counts'] = {'total_panels_reviewed':len(panels['panels']), 'resolved':len(resolved),
                        'partially_resolved':sum('PARTIAL' in r['load_path_status'] for r in panels['panels']),
                        'unresolved':len(unresolved)}
    panels['resolved_weight_kN'] = sum(float(r['self_weight_kN']) for r in resolved)
    panels['unresolved_weight_kN'] = sum(float(r['self_weight_kN']) for r in unresolved)
    panels['status'] = 'ALL_REVIEWED_PANEL_LOAD_PATHS_RESOLVED' if not unresolved else 'INCOMPLETE_LOAD_PATH_EVIDENCE'
    loads.update(resolved_weight_kN=panels['resolved_weight_kN'], unresolved_weight_kN=panels['unresolved_weight_kN'],
                 agent_action_transaction_id=transaction_id)
    return {'transaction_id':transaction_id, 'input_digests':{k:digest(v) for k,v in inputs.items()},
            'requirement':requirement, 'options':options, 'ranking':ranking, 'decision':decision,
            'selected_option':selected, 'allocation_after':allocation, 'graph_after':graph,
            'framework_after':framework, 'panels_after':panels, 'loads_after':loads}

def run(case, output):
    output = Path(output)
    try:
        inputs, historical, manifest = load_case(case)
        stage = build_stage(inputs, manifest['transaction_id'])
        report = validate(inputs, stage, historical, manifest)
        replay_matches = {
            'requirement': stage['requirement'] == historical['requirement'],
            'selected_option_id': stage['decision']['selected_option_id'] == historical['decision']['selected_option_id'],
            'cutting_ledger': stage['selected_option']['supply']['ledger'] == historical['ledger']['entries'],
            'analysis_plan': stage['framework_after']['plan'] == historical['framework_after']['plan'],
            'panel_loads': stage['loads_after'] == historical['loads_after']}
        report['historical_replay_comparison'] = replay_matches
        if not all(replay_matches.values()):
            report['offline_replay_status'] = 'FAIL'
            report['accepted_for_offline_replay'] = False
            report['checks'].append({'check':'historical_baseline_match','status':'FAIL','reason':'REPLAY_DIFFERS_FROM_FROZEN_BASELINE'})
        for name in ['requirement','options','ranking','decision','allocation_after','graph_after','framework_after','panels_after','loads_after']:
            write(output / (name + '.json'), stage[name])
        write(output / 'input-bindings.json', stage['input_digests'])
        if report['accepted_for_offline_replay']:
            result = historical['structural_result']
            report['historical_structure_summary'] = {
                'evidence_kind':'HISTORICAL_NOT_RECOMPUTED',
                'historical_reported_source':result['result_source'],
                'reported_max_displacement_mm':result['max_displacement_mm'],
                'case_displacements_mm':{k:v.get('max_displacement_mm') for k,v in result['cases'].items()},
                'solver_input_binding':'UNKNOWN_IN_ORIGINAL_RESULT',
                'not_a_code_combination_or_capacity_approval':True}
    except (ValueError, KeyError, TypeError, IndexError, FileNotFoundError) as exc:
        report = {'offline_replay_status':'FAIL', 'accepted_for_offline_replay':False,
                  'engineering_approval':'UNKNOWN', 'approved_for_construction':False,
                  'checks':[{'check':'replay_execution','status':'FAIL','reason':str(exc)}]}
    write(output / 'verification.json', report)
    write(output / 'run-status.json', {'status':report['offline_replay_status'],
          'accepted_for_offline_replay':report['accepted_for_offline_replay'],
          'verification_sha256':digest(report), 'solver_executed':False})
    print(json.dumps({'status':report['offline_replay_status'],
                     'metrics':report.get('metrics'),
                     'failures':[r for r in report['checks'] if r['status']=='FAIL'],
                     'engineering_approval':report['engineering_approval'],
                     'output':str(output.resolve())}, ensure_ascii=False, indent=2))
    return 0 if report['accepted_for_offline_replay'] else 1

def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', type=Path, default=root / 'case')
    parser.add_argument('--output', type=Path, default=root / 'results' / 'baseline')
    args = parser.parse_args()
    return run(args.case, args.output)

if __name__ == '__main__':
    sys.exit(main())
