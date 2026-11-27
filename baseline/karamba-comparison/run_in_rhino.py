"""Run in Rhino's Python runtime with Karamba loaded; no GH document mutation.

Builder and result extraction adapted from the user's original Karamba scripts.
Both cases use the same recorded research material, not verified timber grades.
"""
from __future__ import print_function
import io
import os
import sys
import json
import math
import hashlib
import traceback
import datetime


def read(path):
    with io.open(path,'r',encoding='utf-8-sig') as handle:
        return json.load(handle)


def write(path,value):
    parent=os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    text=json.dumps(value,ensure_ascii=True,indent=2,allow_nan=False)
    with io.open(path,'w',encoding='utf-8') as handle:
        handle.write(text if isinstance(text,type(u'')) else text.decode('utf-8'))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def file_hash(path):
    with open(path,'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def require(condition,message):
    if not condition:
        raise ValueError(message)


def vector(value):
    return [float(value.X),float(value.Y),float(value.Z)]


def magnitude(value):
    return math.sqrt(sum(v*v for v in value))


def execute_case(folder,output,name,environment,native):
    import System
    from System.Collections.Generic import List
    from Karamba.Geometry import Point3,Vector3
    from Karamba.Loads import LoadOrientation
    from Karamba.Results import BeamDisplacements,BeamForces,NodeDisplacements,Reaction
    from KarambaCommon import Toolkit
    framework=read(os.path.join(folder,'inputs',name+'-framework.json'))
    panel_loads=read(os.path.join(folder,'inputs',name+'-loads.json'))
    load_definition=read(os.path.join(folder,'inputs','common-load-definition.json'))
    request=read(os.path.join(folder,'inputs',name+'-request.json'))
    unsigned=dict(request);unsigned.pop('request_digest')
    require(digest(unsigned)==request['request_digest'],'REQUEST_DIGEST_MISMATCH')
    # IronPython 2 and CPython 3 serialize floating-point values differently.
    # Bind the exact JSON bytes actually parsed, rather than reserialize floats.
    require(file_hash(os.path.join(folder,'inputs',name+'-framework.json'))==request['framework_file_sha256'],'FRAMEWORK_FILE_MISMATCH')
    require(file_hash(os.path.join(folder,'inputs',name+'-loads.json'))==request['loads_file_sha256'],'LOADS_FILE_MISMATCH')
    require(file_hash(os.path.join(folder,'inputs','common-load-definition.json'))==request['common_load_file_sha256'],'COMMON_LOAD_FILE_MISMATCH')
    plan=framework['plan']
    material_names={'LOW_STIFFNESS':'(VH)III','REFERENCE_STIFFNESS':'(VH)II','HIGH_STIFFNESS':'Wood'}
    material_name=material_names[plan['material_scenario']]
    table=os.path.join(os.path.dirname(environment['karamba_assembly_path']),'Materials','MaterialProperties.csv')
    material=next(m for m in Toolkit().Material.ReadMaterialTable(table) if m.family=='Wood' and m.name==material_name)
    material_evidence={'scenario':plan['material_scenario'],'family':str(material.family),'name':str(material.name),
        'display_ascii_escaped':type(u'')(material).encode('ascii','backslashreplace').decode('ascii'),'table_sha256':file_hash(table),
        'policy':'Common research material for every physical member; seller species and timber grade are not verified.'}
    k,elements,points,supports,loads=native.native_inputs(plan,material,'LL_FLOOR_ASSEMBLY_100PSF')
    loads.Clear()
    loads.Add(k.Load.GravityLoad(Vector3(0.0,0.0,-1.0),'DL_STRUCTURAL_TIMBER'))
    for row in load_definition['floor_live_load']['line_loads']:
        loads.Add(k.Load.ConstantForceLoad(Vector3(*row['direction']),row['line_load_kN_m'],0.0,1.0,
                    getattr(LoadOrientation,'global'),'LL_FLOOR_ASSEMBLY_100PSF',row['element_id']))
    physical=plan['beams']+plan.get('allocated_braces',[])
    mapping=[]
    for row in panel_loads['load_objects']:
        choices=[]
        for beam in physical:
            if beam['parent_member_id']!=row['physical_member_id']:
                continue
            start=plan['nodes'][beam['start']]['coordinates_mm'];end=plan['nodes'][beam['end']]['coordinates_mm']
            axis=[end[i]-start[i] for i in range(3)];length2=sum(v*v for v in axis)
            if length2<=1e-12:
                continue
            raw=sum((row['contact_coordinates_mm'][i]-start[i])*axis[i] for i in range(3))/length2
            t=max(0.0,min(1.0,raw))
            distance=magnitude([row['contact_coordinates_mm'][i]-start[i]-t*axis[i] for i in range(3)])
            section=beam['section'];radius=0.5*math.hypot(section['width_mm'],section['depth_mm'])
            choices.append((distance,abs(raw-t),radius,beam['element_id'],t))
        require(bool(choices),'PANEL_RECEIVER_MISSING:'+row['panel_id'])
        distance,outside,radius,element_id,t=min(choices)
        require(outside<=1e-6 and distance<=radius+1e-3,'PANEL_CONTACT_OUTSIDE_SECTION:'+row['panel_id'])
        loads.Add(k.Load.ConcentratedForceLoad(t,Vector3(*row['force_kN']),getattr(LoadOrientation,'global'),
                    row['load_case'],List[System.String]([element_id]),List[System.Guid]()))
        mapping.append({'panel_id':row['panel_id'],'element_id':element_id,'t':t,
                        'surface_to_axis_offset_mm':distance,'eccentricity_capacity':'NOT_VERIFIED'})
    assembler=next(m for m in k.Model.GetType().GetMethods() if m.Name=='AssembleModel' and len(m.GetParameters())==14)
    args=System.Array[System.Object]([elements,supports,loads,None,System.Double(0),Point3(),None,False,None,points,None,System.Double(1e-9),None,None])
    model=assembler.Invoke(k.Model,args)
    require(model is not None,'ASSEMBLED_MODEL_NULL')
    assembly_messages=[str(args[3] or ''),str(args[6] or '')]
    # Verify actual assembled SI values, rather than infer units from display labels.
    by_id={str(e.id):e for e in model.elems}
    section_checks=[]
    for beam in physical:
        elem=by_id[beam['element_id']];section=beam['section']
        b=section['width_mm'];h=section['depth_mm']
        require(abs(float(elem.crosec.A)*1e6-b*h)<1e-4,'ASSEMBLED_SECTION_AREA_MISMATCH:'+beam['element_id'])
        actual=sorted([float(elem.crosec.Iyy)*1e12,float(elem.crosec.Izz)*1e12])
        expected=sorted([b*h**3/12.0,h*b**3/12.0])
        require(all(abs(a-e)<=max(1e-3,abs(e)*1e-8) for a,e in zip(actual,expected)),'ASSEMBLED_SECTION_INERTIA_MISMATCH')
        section_checks.append({'element_id':beam['element_id'],'area_mm2':float(elem.crosec.A)*1e6,'inertia_mm4':actual})
    require(model.nodes.Count==len(plan['nodes']),'ASSEMBLED_NODE_COUNT_MISMATCH')
    for index,node in enumerate(model.nodes):
        require(all(abs(a*1000-b)<1e-6 for a,b in zip(vector(node.pos),plan['nodes'][index]['coordinates_mm'])),'ASSEMBLED_NODE_UNITS_MISMATCH')
    cases=['DL_STRUCTURAL_TIMBER','LL_FLOOR_ASSEMBLY_100PSF']
    binding={'request_digest':request['request_digest'],'runner_sha256':environment['runner_sha256'],
             'builder_sha256':environment['builder_sha256'],'karamba_version':environment['karamba_version'],
             'material':material_evidence,'run_id':environment['run_id']}
    write(os.path.join(output,name+'-preflight.json'),{'binding':binding,'section_and_node_units':'PASS',
        'assembly_messages':assembly_messages,'physical_section_checks':section_checks,'panel_mappings':mapping,
        'model_elements':model.elems.Count,'nodes':model.nodes.Count,'load_objects':loads.Count})
    method=next(m for m in k.Algorithms.GetType().GetMethods() if m.Name=='Analyze' and len(m.GetParameters())==6)
    solve_args=System.Array[System.Object]([model,List[System.String](cases),None,None,None,None])
    solved=method.Invoke(k.Algorithms,solve_args)
    require(solved is not None,'SOLVER_RETURNED_NULL')
    message=str(solve_args[5] or '')
    require(not message.strip(),'SOLVER_MESSAGE_REQUIRES_REVIEW:'+message)
    solver_displacements=[float(v) for v in (solve_args[2] or [])]
    require(len(solver_displacements)==len(cases),'SOLVER_CASE_COUNT_MISMATCH')
    element_ids=List[System.String]([row['element_id'] for row in physical])
    stations=List[System.Double]([i/20.0 for i in range(21)])
    results={}
    for case in cases:
        args=(solved,element_ids,List[System.Guid](),case,stations)
        forces=BeamForces.solve(*args);displacements=BeamDisplacements.solve(*args)
        nodes=NodeDisplacements.solve(solved,case,List[System.Int32]())
        rows=[]
        for index,beam in enumerate(physical):
            require(str(solved.elems[int(forces[-1][index])].id)==beam['element_id'],'RESULT_ELEMENT_ID_MISMATCH')
            samples=[]
            for j,t in enumerate(stations):
                translation=vector(displacements[0][index][j][0]);force=vector(forces[0][index][j][0]);moment=vector(forces[1][index][j][0])
                values=translation+force+moment
                require(all(not math.isnan(v) and not math.isinf(v) for v in values),'NONFINITE_RESULT')
                samples.append({'t':float(t),'displacement_mm':magnitude(translation)*1000,
                                'translation_m':translation,'force_kN':force,'moment_kNm':moment})
            rows.append({'element_id':beam['element_id'],'member_id':beam['parent_member_id'],
                'max_sampled_displacement_mm':max(s['displacement_mm'] for s in samples),
                'max_abs_axial_force_kN':max(abs(s['force_kN'][0]) for s in samples),
                'max_shear_resultant_kN':max(math.hypot(s['force_kN'][1],s['force_kN'][2]) for s in samples),
                'max_bending_resultant_kNm':max(math.hypot(s['moment_kNm'][1],s['moment_kNm'][2]) for s in samples),
                'samples':samples})
        reaction=Reaction.solve(solved,case,List[System.Int32]())
        results[case]={'max_physical_sampled_displacement_mm':max(r['max_sampled_displacement_mm'] for r in rows),
            'max_nodal_displacement_mm':max(magnitude(vector(row[0]))*1000 for row in nodes[0]),
            'element_results':rows,'reaction_sum_force_kN':[vector(v) for v in reaction[3]],
            'reaction_sum_moment_kNm':[vector(v) for v in reaction[4]]}
    result={'schema':'TIMBER_BOUND_KARAMBA_RESULT_V1','case':name,'status':'SOLVED_RESEARCH_MODEL',
        'solver_executed':True,'binding':binding,'binding_digest':digest(binding),'cases':results,
        'solver_reported_displacements_m':solver_displacements,'model_elements':solved.elems.Count,
        'node_count':solved.nodes.Count,'sample_stations_per_element':21,
        'engineering_approval':'UNKNOWN','approved_for_construction':False,'utilisation':None,
        'limits':['Research stiffness shared across all timber; no verified grading.',
                  'Connection stiffness and foundations remain research assumptions.',
                  'Separate DL/LL cases; no code load combinations or acceptance limits supplied.',
                  'Member maxima are sampled at 21 stations, not exact analytical extrema.']}
    write(os.path.join(output,name+'-result.json'),result)
    return result


def main(folder):
    import System
    import Rhino
    folder=os.path.abspath(folder)
    run_id=datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')
    output=os.path.join(folder,'runs',run_id)
    manifest=read(os.path.join(folder,'input-manifest.json'))
    for relative,expected in manifest['files'].items():
        require(file_hash(os.path.join(folder,relative))==expected,'FROZEN_INPUT_MODIFIED:'+relative)
    assemblies=[a for a in System.AppDomain.CurrentDomain.GetAssemblies() if a.GetName().Name=='KarambaCommon']
    require(len(assemblies)==1,'KARAMBA_ASSEMBLY_NOT_LOADED_OR_AMBIGUOUS')
    assembly=assemblies[0]
    import clr
    clr.AddReference(assembly)
    environment={'run_id':run_id,'rhino_version':str(Rhino.RhinoApp.Version),
        'rhino_units':str(Rhino.RhinoDoc.ActiveDoc.ModelUnitSystem),
        'karamba_version':str(assembly.GetName().Version),'karamba_assembly_path':str(assembly.Location),
        'runner_sha256':file_hash(os.path.join(folder,'run_in_rhino.py')),
        'builder_sha256':file_hash(os.path.join(folder,'vendor','karamba_connected_builder.py')),
        'python_version':sys.version}
    write(os.path.join(output,'environment.json'),environment)
    # Load the pinned helper into a fresh namespace, avoiding a cached module
    # from the user's live project and any writes to its active transaction.
    import types
    native=types.ModuleType('timber_comparison_native')
    path=os.path.join(folder,'vendor','karamba_connected_builder.py')
    with io.open(path,encoding='utf-8-sig') as handle:
        exec(compile(handle.read(),path,'exec'),native.__dict__)
    summary={'run_id':run_id,'status':'RUNNING','cases':{},'engineering_approval':'UNKNOWN',
             'approved_for_construction':False,'gh_canvas_modified':False,'original_active_pointers_modified':False}
    write(os.path.join(output,'run-status.json'),summary)
    for name in ['baseline','candidate']:
        try:
            result=execute_case(folder,output,name,environment,native)
            summary['cases'][name]={'status':result['status'],'binding_digest':result['binding_digest'],
                'result_file_sha256':file_hash(os.path.join(output,name+'-result.json')),
                'preflight_file_sha256':file_hash(os.path.join(output,name+'-preflight.json'))}
        except Exception:
            error=traceback.format_exc()
            summary['cases'][name]={'status':'FAILED','error':error}
            write(os.path.join(output,name+'-error.json'),summary['cases'][name])
            # Do not continue through a failure with estimated or old results.
            summary['status']='FAILED'
            break
    if len(summary['cases'])==2 and all(v['status']=='SOLVED_RESEARCH_MODEL' for v in summary['cases'].values()):
        summary['status']='BOTH_CASES_SOLVED'
    for relative,expected in manifest['files'].items():
        require(file_hash(os.path.join(folder,relative))==expected,'INPUT_CHANGED_DURING_SOLVE:'+relative)
    write(os.path.join(output,'run-status.json'),summary)
    write(os.path.join(folder,'latest-run.json'),{'run_id':run_id,'path':output,'status':summary['status']})
    print(json.dumps({'status':summary['status'],'output':output}))
    return summary


if __name__=='__main__':
    main(os.path.dirname(os.path.abspath(__file__)))
