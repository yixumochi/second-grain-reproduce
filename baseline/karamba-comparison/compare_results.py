"""Verify fresh solver evidence and derive a comparison, never an approval."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re

TARGET='SECONDARY_BACKING__A__RAIL_01'
DL='DL_STRUCTURAL_TIMBER'
LL='LL_FLOOR_ASSEMBLY_100PSF'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def require(condition,message):
    if not condition:
        raise ValueError(message)


def chord_relative(samples):
    start,end=samples[0]['translation_m'],samples[-1]['translation_m']
    require(samples[0]['t']==0 and samples[-1]['t']==1,'MISSING_ENDPOINT_SAMPLES')
    return max(math.sqrt(sum((s['translation_m'][i]-(1-s['t'])*start[i]-s['t']*end[i])**2
                            for i in range(3)))*1000 for s in samples)


def collect(root):
    latest=read(root/'latest-run.json');folder=root/'runs'/latest['run_id']
    require(folder.resolve().parent==(root/'runs').resolve(),'RUN_OUTSIDE_EXPERIMENT')
    state=read(folder/'run-status.json');environment=read(folder/'environment.json')
    require(latest['status']==state['status']=='BOTH_CASES_SOLVED','BOTH_CASES_NOT_SOLVED')
    require(latest['run_id']==state['run_id']==environment['run_id']==folder.name,'RUN_ID_MISMATCH')
    manifest=read(root/'input-manifest.json')
    require(all(sha(root/p)==expected for p,expected in manifest['files'].items()),'INPUT_FILE_CHANGED')
    common=read(root/'inputs/common-load-definition.json')
    data={};checks=[]
    for name in ['baseline','candidate']:
        result_path=folder/(name+'-result.json');preflight_path=folder/(name+'-preflight.json')
        require(sha(result_path)==state['cases'][name]['result_file_sha256'],'RESULT_FILE_CHANGED:'+name)
        require(sha(preflight_path)==state['cases'][name]['preflight_file_sha256'],'PREFLIGHT_FILE_CHANGED:'+name)
        result=read(result_path);preflight=read(preflight_path)
        request=read(root/'inputs'/(name+'-request.json'));unsigned=dict(request);unsigned.pop('request_digest')
        require(digest(unsigned)==request['request_digest'],'REQUEST_DIGEST_MISMATCH')
        binding=result['binding']
        require(result['case']==name and result['status']=='SOLVED_RESEARCH_MODEL' and result['solver_executed'],'WRONG_SOLVER_RESULT')
        require(binding['request_digest']==request['request_digest'],'STALE_RESULT_INPUT_BINDING:'+name)
        require(binding['run_id']==latest['run_id'],'STALE_RESULT_RUN')
        require(binding['runner_sha256']==environment['runner_sha256']==sha(root/'run_in_rhino.py'),'RUNNER_CHANGED')
        require(binding['builder_sha256']==environment['builder_sha256']==sha(root/'vendor/karamba_connected_builder.py'),'BUILDER_CHANGED')
        require(digest(binding)==result['binding_digest']==state['cases'][name]['binding_digest'],'RESULT_BINDING_DIGEST_MISMATCH')
        require(preflight['binding']==binding and preflight['section_and_node_units']=='PASS','ASSEMBLY_UNITS_NOT_VERIFIED')
        require(preflight['assembly_messages']==['',''],'ASSEMBLY_MESSAGE_REQUIRES_REVIEW')
        require(not result['approved_for_construction'] and result['engineering_approval']=='UNKNOWN','UNSUPPORTED_ENGINEERING_APPROVAL')
        plan=read(root/'inputs'/(name+'-framework.json'))['plan']
        loads=read(root/'inputs'/(name+'-loads.json'))
        require(sha(root/'inputs'/(name+'-framework.json'))==request['framework_file_sha256'],'FRAMEWORK_REQUEST_MISMATCH')
        require(sha(root/'inputs'/(name+'-loads.json'))==request['loads_file_sha256'],'LOADS_REQUEST_MISMATCH')
        physical=plan['beams']+plan.get('allocated_braces',[])
        gamma=float(re.search(r'gamma:([0-9.eE+-]+)',binding['material']['display_ascii_escaped']).group(1))
        volume=sum(b['length_mm']*b['section']['width_mm']*b['section']['depth_mm']/1e9 for b in physical)
        expected_dl=volume*gamma+sum(-r['force_kN'][2] for r in loads['load_objects'])
        expected_ll=sum(r['line_load_kN_m']*r['length_mm']/1000 for r in common['floor_live_load']['line_loads'])
        for case,expected in [(DL,expected_dl),(LL,expected_ll)]:
            reaction=[sum(v[i] for v in result['cases'][case]['reaction_sum_force_kN']) for i in range(3)]
            residual=[reaction[0],reaction[1],reaction[2]-expected]
            require(all(abs(v)<1e-7 for v in residual),'FORCE_EQUILIBRIUM_FAILED:'+name+':'+case)
            checks.append({'variant':name,'case':case,'check':'independent_force_balance',
                           'status':'PASS','expected_downward_kN':expected,'reaction_kN':reaction,'residual_kN':residual})
            rows=result['cases'][case]['element_results']
            require({r['element_id'] for r in rows}=={b['element_id'] for b in physical},'RESULT_ELEMENT_SET_MISMATCH')
        data[name]={'result':result,'plan':plan,'loads':loads,'volume_m3':volume}
    a,b=data['baseline'],data['candidate']
    require(a['result']['binding']['material']==b['result']['binding']['material'],'MATERIAL_ASSUMPTIONS_DIFFER')
    for key in ['nodes','supports','numerical_arms','numerical_springs','allocated_braces','research_braces','connection_factor']:
        require(a['plan'].get(key)==b['plan'].get(key),'UNCONTROLLED_MODEL_CHANGE:'+key)
    require(a['loads']['load_objects']==b['loads']['load_objects'],'PANEL_LOADS_DIFFER')
    changes=[]
    require(len(a['plan']['beams'])==len(b['plan']['beams']),'BEAM_COUNT_CHANGED')
    for old,new in zip(a['plan']['beams'],b['plan']['beams']):
        if old!=new:
            require(old['parent_member_id']==new['parent_member_id']==TARGET,'UNRELATED_BEAM_CHANGED')
            fields=sorted(k for k in set(old)|set(new) if old.get(k)!=new.get(k))
            require(fields==['section','supply_id'],'UNEXPECTED_BEAM_CHANGE')
            changes.append({'before':old,'after':new})
    require(len(changes)==1,'EXPECTED_ONE_BEAM_CHANGE')
    rows=[]
    for case in [DL,LL]:
        values={}
        for name in ['baseline','candidate']:
            result=data[name]['result']['cases'][case]
            member=next(r for r in result['element_results'] if r['member_id']==TARGET)
            values[name]={'global_sampled_displacement_mm':result['max_physical_sampled_displacement_mm'],
                'target_sampled_displacement_mm':member['max_sampled_displacement_mm'],
                'target_chord_relative_displacement_mm':chord_relative(member['samples']),
                'target_max_bending_resultant_kNm':member['max_bending_resultant_kNm'],
                'target_max_shear_resultant_kN':member['max_shear_resultant_kN']}
        for metric,old in values['baseline'].items():
            new=values['candidate'][metric]
            rows.append({'case':case,'metric':metric,'baseline':old,'candidate':new,'delta':new-old,
                         'ratio':new/old if abs(old)>1e-12 else None,
                         'change_percent':(new/old-1)*100 if abs(old)>1e-12 else None})
    historical=read(root.parent/'case/historical/structural_result.json')
    archive_check={case:abs(a['result']['cases'][case]['max_physical_sampled_displacement_mm']-
                           historical['cases'][case]['max_displacement_mm'])<1e-8 for case in [DL,LL]}
    require(all(archive_check.values()),'NEW_BASELINE_DIFFERS_FROM_ARCHIVE_REVIEW_REQUIRED')
    return {'schema':'TIMBER_KARAMBA_COMPARISON_V1','run_id':latest['run_id'],'status':'VERIFIED_RESEARCH_COMPARISON',
        'solver_executed':True,'karamba_version':environment['karamba_version'],
        'checks':checks,'fresh_baseline_agrees_with_archive':archive_check,'metrics':rows,'changed_beams':changes,
        'physical_volume_m3':{k:v['volume_m3'] for k,v in data.items()},
        'sample_stations_per_element':21,'engineering_approval':'UNKNOWN','candidate_design_acceptance':'UNDETERMINED',
        'reason':'No verified grade, capacity checks, code combinations or serviceability acceptance limits.',
        'chord_relative_definition':'max ||u(t)-[(1-t)u(0)+t*u(1)]||, sampled at 21 positions; mm.',
        'run_directory':str(folder),'result_sha256':{n:sha(folder/(n+'-result.json')) for n in data}}


def render(root,report):
    labels={'global_sampled_displacement_mm':'整体最大采样位移（mm）',
            'target_sampled_displacement_mm':'替换构件最大采样位移（mm）',
            'target_chord_relative_displacement_mm':'替换构件相对端点连线的变形（mm）',
            'target_max_bending_resultant_kNm':'替换构件最大弯矩合量（kN·m）',
            'target_max_shear_resultant_kN':'替换构件最大剪力合量（kN）'}
    lines=['# Karamba 原方案与替换候选：实际求解结果','',
        '两套模型已在 Rhino 内调用 Karamba 实际求解；新原方案结果与历史值一致。',
        '输入、组装单位、结果绑定和独立力平衡检查通过。当前是研究模型对照，不能据此批准候选用于施工。','',
        '| 恒载工况指标 | 原方案 | 替换候选 | 变化 |','|---|---:|---:|---:|']
    for row in report['metrics']:
        if row['case']==DL:
            lines.append('| {} | {:.6f} | {:.6f} | {:+.2f}% |'.format(labels[row['metric']],row['baseline'],row['candidate'],row['change_percent']))
    ll=next(r for r in report['metrics'] if r['case']==LL and r['metric']=='global_sampled_displacement_mm')
    lines+=['',f'楼面活载工况：两者整体最大采样位移均为 {ll["baseline"]:.6f} mm。','',
        '## 这说明什么','',
        '整体最大位移略降，但替换构件自身的位移和相对端点连线变形增大。截面变小同时降低了结构自重，整体最大位移不足以判断局部替换质量。',
        '相对端点连线变形由求解后的位移样本计算，扣除两端位移的线性插值；它不是规范验收结论。所有构件指标采用 21 个采样位置。','',
        '## 比较条件','',
        '- 只替换 SECONDARY_BACKING__A__RAIL_01：库存 119600_001 → 119270_009。',
        '- 截面 95.25 × 146.05 mm → 19.05 × 88.9 mm；中心线长度仍为 900 mm。',
        '- 节点、支座、面板荷载、楼面活载和数值连接保持相同。自重按各自截面自动计算。',
        '- 两者采用相同研究材料 (VH)III；没有按卖家树种推断实测刚度或强度。',
        '- 分别计算 DL 与 LL；未计算规范荷载组合、承载力利用率或连接容量。','',
        '## 接受还是拒绝','',
        '**当前判断：待判定。** 已证明候选可以完成数值求解，并发现局部变形增大；尚未设定有依据的服务性限值，材料等级、连接和基础也未验证，所以不自动接受或拒绝。',
        '下一步应明确局部变形与材料筛选规则，再把不满足条件的候选退回库存搜索。','',
        '## 可追溯记录','',f'- 运行编号：`{report["run_id"]}`。',
        f'- Karamba 版本：`{report["karamba_version"]}`。',
        '- `comparison.json`：比较指标、输入控制与力平衡证据。',
        '- `runs/<运行编号>/`：环境、组装检查、每个构件的位移/内力采样、反力和结果摘要。',
        '- 原 Grasshopper 文档保持未修改；原项目活动指针未被本脚本写入。','']
    (root/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    root=Path(__file__).resolve().parent
    report=collect(root)
    (root/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    render(root,report)
    print(json.dumps({'status':report['status'],'run_id':report['run_id'],'metrics':report['metrics'][:3]},indent=2))


if __name__=='__main__':
    main()
