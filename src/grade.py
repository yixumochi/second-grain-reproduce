"""Named conditional design-basis hypotheses; never a photo-derived strength grade."""
import re
from src.io_utils import read, ROOT

DEFECTS=['decay','knots','slope_of_grain','checks_and_splits','holes_and_metal','warp','moisture','section_loss']

def evaluate(record, evidence=None):
    rules=read(ROOT/'configs/grade_rules.json');evidence=evidence or {}
    d=record.get('nominal_dimensions') or {};title=record.get('title','')
    t=d.get('thickness_in');w=d.get('width_in')
    t=t if isinstance(t,(int,float)) else (d.get('thickness_mm') or 0)/25.4
    w=w if isinstance(w,(int,float)) else (d.get('width_mm') or 0)/25.4
    t,w=sorted([t or 0,w or 0])
    engineered=bool(re.search(r'laminat|plywood|glulam|\blvl\b|\bpsl\b|\blsl\b|\bosb\b|\bmdf\b|particleboard',title,re.I))
    ranged=any(isinstance(d.get('title_axes_in',{}).get(a),list) and len(d['title_axes_in'][a])==2
               and abs(d['title_axes_in'][a][1]-d['title_axes_in'][a][0])>.05 for a in ['thickness','width'])
    premises={k:'UNKNOWN' for k in rules['required']}
    # An explicit evidence record can disprove a hypothesis; no photos are silently
    # converted into confirmation of decay absence or good condition.
    for k,v in evidence.items():
        if k in premises and v in ['SUPPORTED','CONTRADICTED','UNKNOWN']:premises[k]=v
    candidates=[];status='DIMENSION_OR_PRODUCT_UNRESOLVED'
    if engineered:
        status='ENGINEERED_OR_LAMINATED_PRODUCT_REVIEW';premises['solid_sawn_product']='UNRESOLVED_TITLE_INDICATES_ENGINEERED'
    elif ranged:status='SECTION_RANGE_REQUIRES_CLASSIFICATION'
    elif t>=5:
        status='SELLER_SIZE_OUTSIDE_DIMENSION_BRANCH'
    elif 2<=t<5 and w>=2:
        assumed_t,assumed_w=t,w
        grade='Stud' if abs(t-2)<.01 and w<=6.01 else 'No. 2'
        candidates.append(dict(grade=grade,species_design_assumption='spruce-pine-fir' if grade=='Stud' else 'hem-fir',
            hypothesis_kind='CONDITIONAL_CODE_DESIGN_BASIS',nominal_section_scenario_in=[assumed_t,assumed_w],
            size_basis='SELLER_TITLE_AS_NOMINAL_SCENARIO_NOT_VERIFIED'))
        status='CONDITIONAL_NAMED_HYPOTHESIS'
    elif t>0 and w>0:
        # Common dressed-size scenario, explicitly NOT a measured/nominal conversion.
        # Restrict to familiar size pairs; do not expand arbitrary boards into dimension lumber.
        pairs=[(1.5,3.5,2,4),(1.5,5.5,2,6),(1.5,7.25,2,8),(1.5,9.25,2,10),(1.5,11.25,2,12),
               (2.5,3.5,3,4),(3.5,3.5,4,4),(3.5,5.5,4,6)]
        match=next((p for p in pairs if abs(t-p[0])<.03 and abs(w-p[1])<.03),None)
        if match:
            nt,nw=match[2:];grade='Stud' if nt==2 and nw<=6 else 'No. 2'
            candidates.append(dict(grade=grade,species_design_assumption='spruce-pine-fir' if grade=='Stud' else 'hem-fir',
                hypothesis_kind='CONDITIONAL_CODE_DESIGN_BASIS',nominal_section_scenario_in=[nt,nw],
                size_basis='IF_COMMON_DRESSED_TO_NOMINAL_CLASS_IS_CONFIRMED_NOT_AUTOMATIC_CONVERSION'))
            status='CONDITIONAL_NOMINAL_CLASS_SCENARIO'
        else:status='BOARD_OR_NONSTANDARD_SECTION_REVIEW'
    blockers=[k for k,v in premises.items() if v=='CONTRADICTED']
    if blockers:status='HYPOTHESIS_PREMISE_CONTRADICTED'
    for c in candidates:
        c.update(status='NOT_APPLIED' if not blockers else 'NOT_AVAILABLE_UNDER_RECORDED_EVIDENCE',
                 conditions=list(premises),probability=None)
    return dict(schema='GradeHypothesis/1',listing_id=record['listing_id'],status=status,
        seller_title=title,seller_section_in=[t,w],seller_dimensions_status='SELLER_REPORTED_NOT_INSPECTED',
        conditional_candidates=candidates,premises=premises,contradicted_premises=blockers,
        visual_grade_estimate='UNRESOLVED',formal_grade='UNKNOWN',grade_range=None,
        inferred_species='UNKNOWN',strength_values=None,rule_basis_applied=False,
        structural_verification='NOT_RUN',confidence='UNRANKED_CONDITIONAL_NOT_A_PROBABILITY',
        same_physical_piece_confirmed=record.get('same_physical_piece_confirmed','unknown'),
        visible_defect_assessment={k:'UNKNOWN_NO_VALIDATED_DETECTOR' for k in DEFECTS},
        source=rules['source'],clause=rules['clause'],
        explanation='Named hypotheses describe a conditional code route, not a CNN grade prediction. Geometry, mask and line success do not establish good condition, no decay, nominal class, species or grade.',
        next_evidence=[k for k,v in premises.items() if v!='SUPPORTED'],
        limitations=['Commercial gallery identity and unseen faces remain uncertain.',
                    'Low resolution can hide defects; absence of a visible signal is not absence of decay.',
                    'Surface residuals cannot be interpreted as physical warp or strength loss without validation.',
                    'Seattle applicability and alternative grade/inspection routes require project-specific review.'])
