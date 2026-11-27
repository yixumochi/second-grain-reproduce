import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.grade import evaluate

def rec(t,w,title='Used timber'):
    return dict(listing_id='TEST',title=title,nominal_dimensions=dict(thickness_in=t,width_in=w))

class GradeTests(unittest.TestCase):
    def test_stud_condition_not_grade(self):
        h=evaluate(rec(2,4));self.assertEqual(h['conditional_candidates'][0]['grade'],'Stud')
        self.assertFalse(h['rule_basis_applied']);self.assertEqual(h['formal_grade'],'UNKNOWN')
        self.assertEqual(h['premises']['devoid_of_decay'],'UNKNOWN')
    def test_other_dimension(self):self.assertEqual(evaluate(rec(2,8))['conditional_candidates'][0]['grade'],'No. 2')
    def test_heavy(self):self.assertEqual(evaluate(rec(13.375,14))['conditional_candidates'],[])
    def test_laminated(self):self.assertEqual(evaluate(rec(2,4,'Laminated oak'))['conditional_candidates'],[])
    def test_board(self):self.assertEqual(evaluate(rec(.75,5.5))['conditional_candidates'],[])
    def test_dressed_is_only_scenario(self):self.assertEqual(evaluate(rec(1.5,3.5))['status'],'CONDITIONAL_NOMINAL_CLASS_SCENARIO')
    def test_contradicted(self):
        h=evaluate(rec(2,4),{'devoid_of_decay':'CONTRADICTED'})
        self.assertEqual(h['conditional_candidates'][0]['status'],'NOT_AVAILABLE_UNDER_RECORDED_EVIDENCE')
    def test_supported_still_not_auto_applied(self):
        h=evaluate(rec(2,4));h=evaluate(rec(2,4),{k:'SUPPORTED' for k in h['premises']})
        self.assertFalse(h['rule_basis_applied'])

if __name__=='__main__':unittest.main()
