"""Read-only pilot acceptance checks; never starts or retries inference."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
IDS={'117692':4,'120235':3,'111575':3,'117165':6,'115685':1}
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
out=ROOT/'outputs';summary=read(out/'batch_summary.json')['records'];checks=[]
for listing,count in IDS.items():
    entry=summary.get(listing);issues=[]
    if not entry:
        checks.append(dict(listing=listing,status='NEEDS_FIX',issues=['No output record']));continue
    folder=(out/entry['report']).parent
    run=read(folder/'run.json');grade=read(folder/'grade_hypothesis.json');inp=read(folder/'input.json')
    if len(inp['images'])!=count:issues.append('Input gallery incomplete')
    if grade['formal_grade']!='UNKNOWN' or grade['rule_basis_applied'] or grade['strength_values'] is not None:
        issues.append('Grade safety invariant violated')
    if run.get('report_error') or not (folder/'review.html').is_file():issues.append('HTML report missing or failed')
    stages=run.get('stages',{})
    for stage in ['sam2','lines']:
        if stages.get(stage,{}).get('status')!='COMPLETE':issues.append(stage+' did not complete')
    fresh=listing in ['117165','115685']
    if fresh:
        execution=folder/'sam2/execution.json'
        if not execution.exists() or not read(execution).get('new_gpu_inference'):issues.append('Fresh automatic SAM2 inference not demonstrated')
    for i in range(1,count+1):
        for name in [f'sam2/{i:02d}_mask.png',f'lines/{i:02d}_key_edges.png']:
            if not (folder/name).is_file():issues.append('Missing '+name)
    if count>1:
        for stage in ['vggt','surface']:
            if stages.get(stage,{}).get('status')!='COMPLETE':issues.append(stage+' did not complete')
        f=folder/'surface/surface_fit.json'
        if f.exists():
            fit=read(f)
            if fit['raw_points_modified'] or fit['metric_accuracy_verified']:issues.append('Geometry provenance invariant violated')
            if fit['estimated_patches']==0:issues.append('No supported surface; inspect whether input failure is local or systematic')
            if not any(face['texture_supported_pixels']>0 for face in fit['faces']):issues.append('No supported photographed texture')
        e=folder/'vggt/execution.json'
        if e.exists():
            metadata=read(e)
            if metadata.get('model_weights_dtype')!='float32' or metadata.get('autocast')!='bfloat16':issues.append('Unexpected VGGT precision recipe')
        else:issues.append('VGGT execution provenance missing')
    elif stages.get('vggt',{}).get('status')!='SINGLE_VIEW_2D_ONLY':issues.append('Single-view route was not labelled correctly')
    checks.append(dict(listing=listing,images=count,fresh_sam2_required=fresh,
        status='NEEDS_REVIEW_OR_FIX' if issues else 'READY_FOR_VISUAL_REVIEW',issues=issues,
        run_status=run['status'],seconds=run.get('seconds'),report=entry['report']))
result=dict(status='NEEDS_REVIEW_OR_FIX' if any(c['issues'] for c in checks) else 'READY_FOR_VISUAL_REVIEW',
    full_batch_started=False,visual_acceptance='NOT_YET_REVIEWED',checks=checks,
    remaining_review=['SAM2 selected timber rather than floor/background',
        'Multi-view geometry and projected photo textures are useful or their failures are understandable',
        'Named grade candidates remain conditional; no unsupported grade or strength assigned',
        'Runtime, memory and output volume acceptable before processing 762 listings'])
path=out/'pilot_acceptance.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
print('Pilot only. No automatic full-batch launch. Export with: bash export_results.sh --ids 117692 120235 111575 117165 115685')
