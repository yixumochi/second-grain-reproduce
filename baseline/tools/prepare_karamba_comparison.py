"""Freeze two auditable Karamba requests; never touch the original active pointers."""
from pathlib import Path
import argparse
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from timber_baseline.replay import load_case, build_stage, write
from timber_baseline.verification import digest, validate
from timber_baseline.change_experiment import experiment, scenarios


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--builder-source',type=Path,required=True)
    args=parser.parse_args()
    folder=ROOT/'karamba-comparison'
    inputs,history,manifest=load_case(ROOT/'case')
    baseline=build_stage(inputs,manifest['transaction_id'])
    assert validate(inputs,baseline,history,manifest)['accepted_for_offline_replay']
    event=scenarios(inputs,baseline)['shortened']
    report,revised,candidate=experiment(inputs,baseline,history,manifest,event)
    assert report['status']=='REALLOCATED'
    common=baseline['framework_after']['archsim_reference_manifest']['load_definition']
    assert common==candidate['framework_after']['archsim_reference_manifest']['load_definition']
    for key in ['nodes','supports','numerical_arms','numerical_springs','research_braces','allocated_braces','material_scenario','connection_factor']:
        assert baseline['framework_after']['plan'].get(key)==candidate['framework_after']['plan'].get(key),key
    assert baseline['loads_after']['load_objects']==candidate['loads_after']['load_objects']
    write(folder/'inputs'/'common-load-definition.json',common)
    source=args.builder_source.read_bytes()
    (folder/'vendor').mkdir(parents=True,exist_ok=True)
    (folder/'vendor'/'karamba_connected_builder.py').write_bytes(source)
    requests={}
    for name,stage in [('baseline',baseline),('candidate',candidate)]:
        framework=stage['framework_after']; loads=stage['loads_after']
        write(folder/'inputs'/(name+'-framework.json'),framework)
        write(folder/'inputs'/(name+'-loads.json'),loads)
        request={'case':name,'upstream_transaction_id':stage['transaction_id'],
                 'input_digests':stage['input_digests'],
                 'framework_digest':digest(framework),'loads_digest':digest(loads),
                 'common_load_definition_digest':digest(common),
                 'framework_file_sha256':hashlib.sha256((folder/'inputs'/(name+'-framework.json')).read_bytes()).hexdigest(),
                 'loads_file_sha256':hashlib.sha256((folder/'inputs'/(name+'-loads.json')).read_bytes()).hexdigest(),
                 'common_load_file_sha256':hashlib.sha256((folder/'inputs'/'common-load-definition.json').read_bytes()).hexdigest(),
                 'source_builder_sha256':hashlib.sha256(source).hexdigest(),
                 'changed_member_ids':report['changed_member_ids'] if name=='candidate' else [],
                 'material_policy':'COMMON_RESEARCH_STIFFNESS_NOT_VERIFIED_SPECIES_OR_GRADE',
                 'engineering_approval':'UNKNOWN'}
        request['request_digest']=digest(request)
        write(folder/'inputs'/(name+'-request.json'),request)
        requests[name]=request
    write(folder/'inputs'/'change-report.json',report)
    files={str(p.relative_to(folder)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted((folder/'inputs').glob('*.json'))}
    files['vendor/karamba_connected_builder.py']=hashlib.sha256(source).hexdigest()
    write(folder/'input-manifest.json',{'schema':'TIMBER_KARAMBA_COMPARISON_INPUTS_V1',
        'files':files,'source_builder_path':str(args.builder_source.resolve()),
        'controlled_stock_change':True,'loads_and_supports_equal':True,
        'comparison_type':'Same assumed material model; changed section and stock identity.',
        'baseline_case_transaction':manifest['transaction_id']})
    print('Prepared: '+str(folder.resolve()))


if __name__=='__main__':
    main()
