"""Native Karamba transport. Loaded by live GH; no allocation or geometry writes."""
import System
from System.Collections.Generic import List
from KarambaCommon import Toolkit
from Karamba.Geometry import Point3, Vector3, Plane3
from Karamba.Elements import BuilderElement
from Karamba.Supports import Support
from Karamba.Loads import Load, LoadOrientation


def native_inputs(plan, material, load_case='SEATTLE_FLOOR_LIVE'):
    k = Toolkit()
    pts = List[Point3]()
    elements = List[BuilderElement]()
    supports = List[Support]()
    loads = List[Load]()
    for node in plan['nodes']:
        pts.Add(Point3(*[v/1000.0 for v in node['coordinates_mm']]))
    for b in plan['beams'] + plan.get('allocated_braces', []):
        s = b['section']
        cs = k.CroSec.Trapezoid(s['depth_mm']/10, s['width_mm']/10, s['width_mm']/10,
                              material, 'CURRENT_ALLOCATED_SECTION', b['parent_member_id'], 'UNVERIFIED_STOCK')
        elements.Add(k.Part.IndexToBeam(b['start'], b['end'], b['element_id'], cs, Vector3(*b['local_z'])))
    # Flow-hypothesis value is an unused factory requirement for numerical arms.
    method = next(m for m in k.Material.GetType().GetMethods()
                  if m.Name == 'IsotropicMaterial' and len(m.GetParameters()) == 11)
    flow_type = method.GetParameters()[8].ParameterType
    flow = System.Enum.GetValues(flow_type).GetValue(0)
    factor = plan['connection_factor']
    args = System.Array[System.Object]([
        'NUMERICAL_CONNECTION_ONLY', 'MASSLESS_PENALTY_'+str(factor),
        # Material factory takes kN/m2 (SI); display strings use kN/cm2.
        System.Double(1000*factor*1e4), System.Double(400*factor*1e4), System.Double(400*factor*1e4),
        System.Double(0), System.Double(1), System.Double(-1), flow, System.Double(0), None])
    num_mat = method.Invoke(k.Material, args)
    num_cs = k.CroSec.Trapezoid(10.0, 10.0, 10.0, num_mat,
                              'NUMERICAL_ONLY_NOT_STOCK', 'PENALTY_ARM', 'DIAGNOSTIC_ONLY')
    for b in plan['numerical_arms']:
        elements.Add(k.Part.IndexToBeam(b['start'], b['end'], b['element_id'], num_cs))
    for s in plan['numerical_springs']:
        c = s['translation_kN_m']
        values = [c,c,c,0,0,0] if s['kind']=='PINNED_CONNECTION' else [0,0,c,0,0,0]
        cs = k.CroSec.Spring(System.Array[System.Double](values),
                            'NUMERICAL_INTERFACE', s['element_id'], 'DIAGNOSTIC_ONLY')
        if s['normal'] is None:
            beam = k.Part.IndexToBeam(s['start'], s['end'], s['element_id'], cs)
        else:
            beam = k.Part.IndexToBeam(s['start'], s['end'], s['element_id'], cs, Vector3(*s['normal']))
        elements.Add(beam)
    for b in plan.get('research_braces', []):
        cs = k.CroSec.Spring(System.Array[System.Double]([
            b['translation_kN_m'], 0., 0., 0., 0., 0.]),
            'RESEARCH_AXIAL_ONLY_NOT_STOCK', b['element_id'], 'DIAGNOSTIC_ONLY')
        elements.Add(k.Part.IndexToBeam(b['start'], b['end'], b['element_id'], cs))
    for s in plan['supports']:
        frame=s.get('support_frame_mm') or s.get('source',{}).get('original_support_record',{}).get('support_frame_mm')
        if frame:
            plane=Plane3(Point3(*[v/1000 for v in frame['origin_mm']]),Vector3(*frame['x_axis']),Vector3(*frame['y_axis']))
            supports.Add(k.Support.Support(s['node_index'],List[System.Boolean](s['fixed_dofs']),plane))
        else:supports.Add(k.Support.Support(s['node_index'],List[System.Boolean](s['fixed_dofs'])))
    for l in plan['loads']:
        loads.Add(k.Load.ConstantForceLoad(Vector3(0,0,-1), l['line_load_kN_m'], 0., 1.,
                                         getattr(LoadOrientation,'global'), load_case, l['element_id']))
    return k, elements, pts, supports, loads


def assemble(plan, material, load_case='SEATTLE_FLOOR_LIVE'):
    k, elements, pts, supports, loads = native_inputs(plan, material, load_case)
    method = next(m for m in k.Model.GetType().GetMethods() if m.Name=='AssembleModel')
    args = System.Array[System.Object]([elements, supports, loads, None, System.Double(0),
        Point3(), None, False, None, pts, None, System.Double(1e-9), None, None])
    model = method.Invoke(k.Model, args)
    return k, model, [str(args[3] or ''), str(args[6] or '')]


def diagnostic_solve(k, model, load_case='SEATTLE_FLOOR_LIVE'):
    method = next(m for m in k.Algorithms.GetType().GetMethods() if m.Name=='Analyze')
    args = System.Array[System.Object]([model, List[System.String]([load_case]), None, None, None, None])
    solved = method.Invoke(k.Algorithms, args)
    return solved, str(args[5] or ''), [float(v) for v in (args[2] or [])]
