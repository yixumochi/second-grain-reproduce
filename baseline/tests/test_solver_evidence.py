"""Offline verification of recorded live-solver evidence; never invokes Rhino."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'karamba-comparison'
spec=importlib.util.spec_from_file_location('karamba_compare',ROOT/'compare_results.py')
comparison=importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class SolverEvidenceTests(unittest.TestCase):
    def test_live_run_passes_input_binding_and_force_balance(self):
        report=comparison.collect(ROOT)
        self.assertEqual(report['status'],'VERIFIED_RESEARCH_COMPARISON')
        self.assertTrue(report['solver_executed'])
        self.assertEqual(len(report['checks']),4)
        self.assertEqual(report['candidate_design_acceptance'],'UNDETERMINED')

    def test_changed_result_file_is_rejected(self):
        original=comparison.sha
        with patch.object(comparison,'sha',side_effect=lambda p:'0'*64 if p.name=='candidate-result.json' else original(p)):
            with self.assertRaisesRegex(ValueError,'RESULT_FILE_CHANGED'):
                comparison.collect(ROOT)

    def changed_read(self,mutate):
        original=comparison.read
        def reader(path):
            value=original(path)
            if path.name=='candidate-result.json':
                mutate(value)
            return value
        return patch.object(comparison,'read',side_effect=reader)

    def test_old_input_binding_is_rejected(self):
        with self.changed_read(lambda v:v['binding'].update(request_digest='old-request')):
            with self.assertRaisesRegex(ValueError,'STALE_RESULT_INPUT_BINDING'):
                comparison.collect(ROOT)

    def test_previous_run_result_is_rejected(self):
        with self.changed_read(lambda v:v['binding'].update(run_id='previous-run')):
            with self.assertRaisesRegex(ValueError,'STALE_RESULT_RUN'):
                comparison.collect(ROOT)

    def test_unbalanced_reaction_is_rejected(self):
        def mutate(v):
            v['cases'][comparison.DL]['reaction_sum_force_kN'][0][2]+=0.1
        with self.changed_read(mutate):
            with self.assertRaisesRegex(ValueError,'FORCE_EQUILIBRIUM_FAILED'):
                comparison.collect(ROOT)

    def test_unsupported_approval_is_rejected(self):
        with self.changed_read(lambda v:v.update(approved_for_construction=True)):
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_ENGINEERING_APPROVAL'):
                comparison.collect(ROOT)

    def test_chord_measure_removes_linear_endpoint_motion(self):
        samples=[{'t':0,'translation_m':[2,3,4]},
                 {'t':0.5,'translation_m':[3,4,5]},
                 {'t':1,'translation_m':[4,5,6]}]
        self.assertAlmostEqual(comparison.chord_relative(samples),0)
        samples[1]['translation_m'][2]+=0.001
        self.assertAlmostEqual(comparison.chord_relative(samples),1.0)


if __name__=='__main__':
    unittest.main()
