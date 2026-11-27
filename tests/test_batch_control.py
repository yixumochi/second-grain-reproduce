"""Control-flow tests use explicit mocks, not claimed inference outputs."""
import sys,tempfile,unittest,json,importlib.util
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('batch',ROOT/'scripts/run_batch.py');batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)

class ControlTests(unittest.TestCase):
    def test_failure_continues_and_resume_avoids_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake(job,name,seconds):
                calls.append((job['record']['listing_id'],name))
                return dict(status='FAILED' if job['record']['listing_id']=='120235' else 'COMPLETE',detail='MOCK_ONLY')
            args=['run_batch.py','--ids','120235','117692','--output',tmp]
            with patch.object(batch,'preflight'),patch.object(batch,'reuse_masks',return_value=False),patch.object(batch,'stage',side_effect=fake),patch.object(sys,'argv',args):batch.main()
            result=json.loads((Path(tmp)/'batch_summary.json').read_text())['records']
            self.assertEqual(set(result),{'120235','117692'})
            self.assertEqual(result['120235']['status'],'PARTIAL_RESEARCH_OUTPUT')
            self.assertEqual(result['117692']['status'],'COMPLETE_RESEARCH_OUTPUT')
            for r in result.values():
                g=json.loads(((Path(tmp)/r['report']).parent/'grade_hypothesis.json').read_text())
                self.assertEqual(g['formal_grade'],'UNKNOWN');self.assertFalse(g['rule_basis_applied'])
            calls.clear()
            with patch.object(batch,'preflight'),patch.object(batch,'stage',side_effect=fake),patch.object(sys,'argv',args):batch.main()
            self.assertEqual(calls,[])
            self.assertFalse((Path(tmp)/'.batch.lock').exists())

if __name__=='__main__':unittest.main()
