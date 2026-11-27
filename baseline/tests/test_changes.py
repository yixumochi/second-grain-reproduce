from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from timber_baseline.replay import load_case, build_stage
from timber_baseline.change_experiment import experiment, scenarios, available_pool, reserve, subtract
from timber_baseline.verification import digest, validate


class ChangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs, cls.history, cls.manifest = load_case(ROOT/'case')
        cls.base = build_stage(cls.inputs, cls.manifest['transaction_id'])
        cls.events = scenarios(cls.inputs,cls.base)
        cls.short = experiment(cls.inputs,cls.base,cls.history,cls.manifest,cls.events['shortened'])

    def run_event(self, name='shortened', **updates):
        event = {**deepcopy(self.events[name]), **updates}
        return experiment(self.inputs,self.base,self.history,self.manifest,event)

    def test_coordinate_change_preserves_every_assignment(self):
        report, inputs, stage = self.run_event('coordinate_only')
        self.assertEqual(report['status'],'UNCHANGED')
        self.assertEqual(report['allocation_retained_digest'],digest(self.base['selected_option']['supply']['assignments']))
        self.assertIsNone(inputs)
        self.assertIsNone(stage)
        self.assertFalse(report['diffcheck_executed'])

    def test_shortening_repairs_one_and_preserves_fourteen(self):
        report, inputs, stage = self.short
        self.assertEqual(report['status'],'REALLOCATED')
        self.assertEqual(report['changed_member_ids'],['SECONDARY_BACKING__A__RAIL_01'])
        self.assertEqual(report['unchanged_member_count'],14)
        self.assertTrue(report['locked_assignments_preserved'])
        self.assertTrue(report['existing_physical_cuts_preserved'])
        change = report['member_changes'][0]
        self.assertNotEqual(change['before']['source_stock_instance_id'],change['after']['source_stock_instance_id'])
        self.assertEqual(change['before']['start_mm'],change['after']['start_mm'])
        self.assertEqual(change['before']['end_mm'],change['after']['end_mm'])
        self.assertTrue(report['verification']['accepted_for_offline_replay'])
        self.assertEqual(stage['input_digests'],{k:digest(v) for k,v in inputs.items()})

    def test_new_section_requires_new_solve_and_omits_old_values(self):
        report, inputs, stage = self.short
        self.assertTrue(report['section_or_material_family_changed'])
        self.assertEqual(report['analysis_status'],'REQUIRES_NEW_SOLVE')
        self.assertFalse(report['solver_executed'])
        self.assertFalse(report['historical_solver_values_reused'])
        self.assertNotIn('historical_structure_summary',report)
        self.assertFalse(report['approved_for_construction'])
        self.assertEqual(report['new_solver_request_binding']['framework_digest'],digest(stage['framework_after']))
        self.assertEqual(report['new_solver_request_digest'],digest(report['new_solver_request_binding']))
        self.assertEqual(next(c['status'] for c in report['verification']['checks'] if c['check']=='historical_association'),'NOT_APPLICABLE')

    def test_missing_endpoint_does_not_update_inventory(self):
        report, inputs, stage = self.run_event('missing_endpoint')
        self.assertEqual(report['status'],'NEEDS_EVIDENCE')
        self.assertIsNone(inputs)
        self.assertIsNone(stage)

    def test_uncertain_measurement_does_not_silently_become_exact(self):
        report, inputs, stage = self.run_event(uncertainty_mm=2.0)
        self.assertEqual(report['status'],'NEEDS_EVIDENCE')
        self.assertIsNone(inputs)
        self.assertIsNone(stage)

    def test_existing_material_loss_is_not_locally_repaired(self):
        report, inputs, stage = self.run_event(length_mm=3000.0)
        self.assertEqual(report['status'],'UNSUPPORTED_SCOPE')
        self.assertIsNone(inputs)
        self.assertIsNone(stage)

    def test_empty_repair_pool_does_not_publish_partial_stage(self):
        # Controlled scarcity at the reservation boundary: actually run the
        # allocator with zero available sources, rather than fabricate success.
        with patch('timber_baseline.change_experiment.reserve',return_value=[]):
            report, inputs, stage = self.run_event()
        self.assertEqual(report['status'],'NO_FEASIBLE_REPAIR_FOUND')
        self.assertFalse(report['partial_repair_committed'])
        self.assertFalse(report['global_infeasibility_proven'])
        self.assertIsNone(stage)

    def test_small_shortening_revalidates_without_reassigning(self):
        report, inputs, stage = self.run_event(length_mm=4200.0)
        self.assertEqual(report['status'],'REVALIDATED')
        self.assertEqual(report['changed_member_ids'],[])
        self.assertEqual(report['unchanged_member_count'],15)
        self.assertTrue(report['verification']['accepted_for_offline_replay'])

    def test_length_growth_does_not_release_unobserved_new_interval(self):
        report, inputs, stage = self.run_event(length_mm=4300.0)
        self.assertEqual(report['status'],'REVALIDATED')
        bounds = [r['available_interval_mm'][1] for r in available_pool(inputs)
                  if r['stock_instance_id']==self.events['shortened']['stock_id']]
        self.assertLessEqual(max(bounds),4267.2)

    def test_forged_prior_digest_rejected(self):
        with self.assertRaisesRegex(ValueError,'STALE_OBSERVATION_BASE'):
            self.run_event(prior_inventory_digest='forged')

    def test_installed_member_movement_is_not_a_scan_coordinate_change(self):
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_CHANGE_SCOPE'):
            self.run_event('coordinate_only',change_scope='INSTALLED_MEMBER_MOVEMENT')

    def test_invalid_lengths_and_uncertainties_rejected(self):
        for value in [float('nan'),float('inf'),-5,0,True]:
            with self.subTest(length=value), self.assertRaisesRegex(ValueError,'INVALID_OBSERVED_LENGTH'):
                self.run_event(length_mm=value)
        for value in [float('nan'),float('inf'),-1,True]:
            with self.subTest(uncertainty=value), self.assertRaisesRegex(ValueError,'INVALID_UNCERTAINTY'):
                self.run_event(uncertainty_mm=value)

    def test_endpoint_distance_must_agree_with_reported_length(self):
        with self.assertRaisesRegex(ValueError,'ENDPOINT_LENGTH_MISMATCH'):
            self.run_event('coordinate_only',observed_endpoints_mm=[[0,0,0],[10,0,0]])

    def test_reservation_removes_cuts_and_kerfs(self):
        pool = available_pool(self.inputs)
        assignments = self.base['selected_option']['supply']['assignments']
        free = reserve(pool,assignments)
        for segment in free:
            a,b = segment['available_interval_mm']
            for row in assignments:
                if row['source_stock_instance_id'] != segment['stock_instance_id']:
                    continue
                for start,end in [row['source_interval_mm']] + ([row['kerf_interval_mm']] if row['kerf_interval_mm'] else []):
                    self.assertLessEqual(min(b,end)-max(a,start),1e-5)
        with self.assertRaisesRegex(ValueError,'OVERLAPPING_RESERVATIONS'):
            subtract([0,100],[[0,30],[20,50]])

    def test_multiple_residual_gaps_conserve_length(self):
        self.assertEqual(subtract([0,100],[[20,30],[50,70]]),[[0,20],[30,50],[70,100]])
        report, inputs, stage = self.short
        for entry in stage['selected_option']['supply']['ledger']:
            parts = entry['cut_intervals_mm']+entry['kerf_intervals_mm']+entry['residual_intervals_after_mm']
            self.assertAlmostEqual(sum(b-a for a,b in parts),entry['available_interval_before_mm'][1]-entry['available_interval_before_mm'][0])

    def test_independent_validator_detects_corrupted_new_ledger(self):
        report, inputs, original = self.short
        stage = deepcopy(original)
        stage['selected_option']['supply']['ledger'][0]['residual_intervals_after_mm'].append([0,1])
        checked = validate(inputs,stage,self.history,self.manifest,evidence_mode='revision')
        self.assertFalse(checked['accepted_for_offline_replay'])
        self.assertIn('cutting_ledger',[c['check'] for c in checked['checks'] if c['status']=='FAIL'])

    def test_repeatable_and_baseline_immutable(self):
        before = digest(self.inputs)
        repeated = self.run_event()
        self.assertEqual(digest(repeated),digest(self.short))
        self.assertEqual(before,digest(self.inputs))
        fresh,_,_ = load_case(ROOT/'case')
        self.assertEqual(digest(fresh),before)


if __name__ == '__main__':
    unittest.main()
