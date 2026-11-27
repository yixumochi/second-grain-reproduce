from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from timber_baseline.replay import build_stage, load_case
from timber_baseline.verification import validate, digest
from timber_baseline.secondary_backing_agent import (apply_to_analysis_framework,
    coordinator_decision, update_graph)
from timber_baseline.allocation_revision_binding import rebind_allocation

class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs, cls.historical, cls.manifest = load_case(ROOT / 'case')
        cls.stage = build_stage(cls.inputs, cls.manifest['transaction_id'])
        cls.outcomes = []

    @classmethod
    def tearDownClass(cls):
        out = ROOT / 'results' / 'fault-injection.json'
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(cls.outcomes, indent=2), encoding='utf-8')

    def assess(self, label, stage=None, inputs=None, historical=None, expected_failed_check=None):
        report = validate(inputs or self.inputs, stage or self.stage,
                          historical or self.historical, self.manifest)
        failed = [r for r in report['checks'] if r['status'] == 'FAIL']
        self.outcomes.append({'scenario':label, 'expected_failed_check':expected_failed_check,
                              'accepted':report['accepted_for_offline_replay'], 'failures':failed})
        if expected_failed_check:
            self.assertFalse(report['accepted_for_offline_replay'])
            self.assertIn(expected_failed_check, [r['check'] for r in failed])
        return report

    def test_baseline_matches_independent_frozen_outputs(self):
        result = self.assess('unaltered_baseline')
        self.assertTrue(result['accepted_for_offline_replay'], result)
        self.assertEqual(self.stage['selected_option']['supply']['ledger'], self.historical['ledger']['entries'])
        self.assertEqual(self.stage['framework_after']['plan'], self.historical['framework_after']['plan'])
        self.assertEqual(self.stage['loads_after'], self.historical['loads_after'])
        self.assertEqual(result['metrics']['added_members'], 15)
        self.assertEqual(result['metrics']['stock_sources'], 10)

    def test_unknown_stock_id_rejected(self):
        stage = deepcopy(self.stage)
        stage['selected_option']['supply']['assignments'][0]['source_stock_instance_id'] = 'NONEXISTENT_STOCK'
        self.assess('unknown_stock_id', stage=stage, expected_failed_check='stock_identity_dimensions')

    def test_duplicate_ledger_consumption_rejected(self):
        stage = deepcopy(self.stage)
        stage['selected_option']['supply']['ledger'].append(deepcopy(stage['selected_option']['supply']['ledger'][0]))
        self.assess('duplicate_consumption_of_same_interval', stage=stage, expected_failed_check='cutting_ledger')

    def test_overlapping_cuts_rejected(self):
        stage = deepcopy(self.stage)
        entry = next(r for r in stage['selected_option']['supply']['ledger'] if len(r['cut_intervals_mm']) > 1)
        # Shift the second complete cut+kerf onto the first while keeping its length.
        cut = entry['cut_intervals_mm'][1]
        delta = entry['cut_intervals_mm'][0][0] - cut[0]
        cut[:] = [cut[0]+delta, cut[1]+delta]
        row = next(r for r in stage['selected_option']['supply']['assignments'] if r['element_id']==entry['member_ids'][1])
        if row['kerf_interval_mm']:
            kerf = row['kerf_interval_mm']
            kerf[:] = [kerf[0]+delta, kerf[1]+delta]
        result = self.assess('overlapping_cuts', stage=stage, expected_failed_check='cutting_ledger')
        failure = next(r for r in result['checks'] if r['check']=='cutting_ledger')
        self.assertIn('OVERLAP', failure['reason'])

    def test_missing_panel_receiver_rejected(self):
        stage = deepcopy(self.stage)
        pid = stage['requirement']['affected_panel_ids'][0]
        stage['graph_after']['edges'] = [e for e in stage['graph_after']['edges'] if not (e['from']==pid and e['relation']=='LOAD_RECEIVER')]
        self.assess('missing_panel_receiver', stage=stage, expected_failed_check='declared_load_paths')

    def test_shortened_stock_invalidates_old_allocation(self):
        inputs = deepcopy(self.inputs)
        assignment = self.stage['selected_option']['supply']['assignments'][0]
        stock = next(r for r in inputs['inventory']['stock_instances'] if r['stock_instance_id']==assignment['source_stock_instance_id'])
        stock['length_mm'] = assignment['source_interval_mm'][1] - 10
        self.assess('stock_shorter_than_committed_cut', inputs=inputs, expected_failed_check='stock_identity_dimensions')

    def test_longer_stock_still_invalidates_old_evidence_binding(self):
        inputs = deepcopy(self.inputs)
        sid = self.stage['selected_option']['supply']['assignments'][0]['source_stock_instance_id']
        next(r for r in inputs['inventory']['stock_instances'] if r['stock_instance_id']==sid)['length_mm'] += 10
        self.assess('changed_length_even_if_cut_still_fits', inputs=inputs, expected_failed_check='input_binding')

    def test_wrong_section_rejected(self):
        stage = deepcopy(self.stage)
        stage['selected_option']['supply']['assignments'][0]['section']['width_mm'] += 10
        self.assess('wrong_member_section', stage=stage, expected_failed_check='stock_identity_dimensions')

    def test_stale_structural_result_rejected(self):
        historical = deepcopy(self.historical)
        historical['structural_result']['transaction_id'] = 'PREVIOUS_TRANSACTION'
        self.assess('old_transaction_result', historical=historical, expected_failed_check='historical_association')

    def test_modified_solver_input_rejected(self):
        stage = deepcopy(self.stage)
        stage['framework_after']['plan']['nodes'][0]['coordinates_mm'][0] += 1
        self.assess('changed_analysis_input_with_old_result', stage=stage, expected_failed_check='historical_association')

    def test_missing_analysis_member_rejected(self):
        stage = deepcopy(self.stage)
        mid = stage['selected_option']['supply']['assignments'][0]['element_id']
        stage['framework_after']['model']['members'] = [m for m in stage['framework_after']['model']['members'] if m['member_id']!=mid]
        self.assess('missing_analysis_member', stage=stage, expected_failed_check='analysis_input_consistency')

    def test_missing_panel_load_rejected(self):
        stage = deepcopy(self.stage)
        stage['loads_after']['load_objects'].pop()
        self.assess('missing_panel_self_weight', stage=stage, expected_failed_check='panel_load_conservation')

    def test_changed_existing_allocation_rejected(self):
        stage = deepcopy(self.stage)
        stage['allocation_after']['allocations'][0]['supply_id'] = 'REPLACED_WITHOUT_RECALCULATION'
        self.assess('existing_allocation_changed', stage=stage, expected_failed_check='existing_allocations')

    def test_unknown_engineering_statuses_remain_unknown(self):
        report = validate(self.inputs, self.stage, self.historical, self.manifest)
        self.assertEqual(report['engineering_approval'],'UNKNOWN')
        self.assertFalse(report['approved_for_construction'])
        unknown = {r['check'] for r in report['checks'] if r['status']=='UNKNOWN'}
        self.assertTrue({'live_structural_analysis','material_capacity','connection_capacity','foundation_design'} <= unknown)

    def test_b_cannot_be_selected_or_executed(self):
        b = self.stage['options'][1]
        ranked = next(r for r in self.stage['ranking'] if r['option_id']==b['option_id'])
        self.assertTrue(b['supply']['stock_feasible'])
        self.assertFalse(ranked['eligible'])
        self.assertIn('UNSUPPORTED_EXECUTION_TOPOLOGY', ranked['execution_blockers'])
        with self.assertRaisesRegex(ValueError,'OPTION_NOT_EXECUTABLE'):
            apply_to_analysis_framework(self.inputs['framework_before'],b)
        with self.assertRaisesRegex(ValueError,'OPTION_NOT_EXECUTABLE'):
            update_graph(self.inputs['graph_before'],b,self.stage['requirement'])
        with self.assertRaisesRegex(ValueError,'OPTION_NOT_EXECUTABLE'):
            coordinator_decision(self.inputs['action']['detected_issues'][0],self.stage['options'],
                                 [{'eligible':True,'option_id':b['option_id']}])

    def test_outputs_are_strict_json(self):
        json.dumps(self.stage, allow_nan=False)

class RevisionBindingTests(unittest.TestCase):
    def setUp(self):
        self.frozen = {'building':{'geometry_revision':'G0','demand_revision':'D0'},
                       'dispatch':{'geometry_revision':'G0','demand_revision':'D0'},
                       'inventory':[{'stock_id':'S1','length_mm':1000}]}
        self.result = {'input_digest':digest(self.frozen), 'geometry_revision':'G0',
                       'demand_revision':'D0','assignments':[{'stock_id':'S1','cut_mm':900}]}

    def test_revision_only_rebind_preserves_results_and_inputs(self):
        current = deepcopy(self.frozen)
        for key in ['building','dispatch']:
            current[key]['geometry_revision']='G1'
            current[key]['demand_revision']='D1'
        before = deepcopy(self.result)
        actual = rebind_allocation(current,self.frozen,self.result)
        self.assertEqual(actual['assignments'],self.result['assignments'])
        self.assertFalse(actual['revision_binding']['allocation_recomputed'])
        self.assertEqual(self.result,before)
        self.assertEqual(actual['input_digest'],digest(current))

    def test_material_length_change_cannot_rebind(self):
        current = deepcopy(self.frozen)
        current['inventory'][0]['length_mm']=850
        with self.assertRaisesRegex(ValueError,'content changed'):
            rebind_allocation(current,self.frozen,self.result)

    def test_forged_result_digest_rejected(self):
        self.result['input_digest']='WRONG'
        with self.assertRaisesRegex(ValueError,'STALE_GLOBAL_PATCHWORK_RESULT'):
            rebind_allocation(self.frozen,self.frozen,self.result)

if __name__ == '__main__':
    unittest.main()
