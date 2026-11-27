"""Same-run sparse surfaces + real-photo UV projection. No per-view alignment."""
from pathlib import Path
import numpy as np
import cv2
from PIL import Image,ImageDraw,ImageFont
from scipy.spatial import cKDTree,ConvexHull
from src.io_utils import read,save,sha

def build(job,out):
    vggt=Path(job['vggt']);samples=np.load(vggt/'timber_samples.npz',allow_pickle=False)
    points=samples['points'];rgb=samples['rgb'];views=samples['views'];pixels=samples['pixels']
    if len(points)<80:raise ValueError('Insufficient finite masked cloud points')
    center=np.median(points,axis=0);_,_,axes=np.linalg.svd(points-center,full_matrices=False)
    local=(points-center)@axes.T;lo,hi=np.quantile(local,[.01,.99],axis=0);extent=hi-lo
    length=float(extent[0]);center=center+((lo+hi)/2)@axes
    if length<=1e-8:raise ValueError('Degenerate cloud')
    q=(points-center)@axes.T/length
    normals=np.zeros_like(q);flatness=np.ones(len(q))
    for view in np.unique(views):
        take=np.flatnonzero(views==view)
        if len(take)<18:continue
        _,ids=cKDTree(q[take]).query(q[take],k=18);neigh=q[take][ids];shifted=neigh-neigh.mean(1)[:,None,:]
        _,s,vh=np.linalg.svd(shifted,full_matrices=False);normals[take]=vh[:,-1];flatness[take]=s[:,-1]/np.maximum(s[:,1],1e-10)
    cfg=job['config']['surface'];tol=cfg['tolerance'];rng=np.random.default_rng(int(job['record']['listing_id']))
    pending=np.ones(len(q),bool);planes=[];normalcos=np.cos(np.deg2rad(32));min_points=80
    for attempt in range(cfg['max_patches']):
        pool=np.flatnonzero(pending&(flatness<.4))
        if len(pool)<min_points:break
        best=None
        for _ in range(450):
            a,b,c=q[rng.choice(pool,3,replace=False)];n=np.cross(b-a,c-a);nn=np.linalg.norm(n)
            if nn<1e-8:continue
            n/=nn;axis=int(np.argmax(np.abs(n)))
            if abs(n[axis])<np.cos(np.deg2rad(25)):continue
            if n[axis]<0:n=-n
            offset=float(a@n)
            if any(p['axis']==axis and abs(offset-p['offset'])<.07 for p in planes):continue
            good=pending&(np.abs(q@n-offset)<=tol)&(np.abs(normals@n)>=normalcos);count=int(good.sum())
            if best is None or count>best[0]:best=count,n,offset,good,axis
        if best is None or best[0]<min_points:break
        _,n,offset,good,axis=best
        for _ in range(4):
            if good.sum()<min_points:break
            pc=q[good].mean(0);_,_,vh=np.linalg.svd(q[good]-pc,full_matrices=False);n=vh[-1]
            if n[axis]<0:n=-n
            offset=float(pc@n);good=pending&(np.abs(q@n-offset)<=tol)&(np.abs(normals@n)>=normalcos)
        if good.sum()<min_points:break
        tangent=np.eye(3)[0 if axis!=0 else 1];u=tangent-n*(tangent@n);u/=np.linalg.norm(u);v=np.cross(n,u);origin=offset*n
        uv=(q[good]-origin)@np.stack([u,v]).T
        try:hull=ConvexHull(uv)
        except Exception:break
        ids=np.flatnonzero(good);planes.append(dict(axis=axis,offset=offset,normal=n,u=u,v=v,origin=origin,
            polygon_uv=uv[hull.vertices],ids=ids,counts=[int(np.sum(views[ids]==i)) for i in range(len(job['images']))]))
        pending[good]=False
    projected=q.copy();assignment=np.full(len(q),-1,np.int16);residual=np.zeros(len(q));records=[]
    for i,p in enumerate(planes):
        ids=p['ids'];signed=q[ids]@p['normal']-p['offset'];projected[ids]-=signed[:,None]*p['normal'];assignment[ids]=i;residual[ids]=abs(signed)
        records.append(dict(id=i,label=f'Estimated patch {i+1}',normal_display=p['normal'].tolist(),
            dominant_axis=['longitudinal / possible end','transverse A','transverse B'][p['axis']],
            polygon_display=(p['origin']+p['polygon_uv'][:,0,None]*p['u']+p['polygon_uv'][:,1,None]*p['v']).tolist(),
            point_count=len(ids),support_by_photo=p['counts'],status='VGGT_ESTIMATED_PLANAR_PATCH',
            boundary='CONVEX_SUPPORT_ENVELOPE_NOT_MEASURED_EDGE'))
    np.testing.assert_array_equal(projected[assignment<0],q[assignment<0])
    cameras=read(vggt/'cameras.json');pred=np.load(vggt/'predictions.npz',allow_pickle=False)
    textures(out,job,planes,records,q,views,center,axes,length,cameras,pred)
    dimensions=job['record'].get('nominal_dimensions') or {};seller=np.array([dimensions.get(k) or 0 for k in ['length_mm','width_mm','thickness_mm']],float)
    section=sorted(extent[1:],reverse=True);scaled=np.array([extent[0]]+section)/length*(seller[0] or 1)
    directdiff=np.linalg.norm(points-samples['direct_points'],axis=1)/length
    summary=dict(source_run=job['run_key'],input_points=len(q),supported_points=int((assignment>=0).sum()),
        unassigned_points=int((assignment<0).sum()),estimated_patches=len(planes))
    fit=dict(**summary,status='EXPERIMENTAL_SURFACE_HYPOTHESIS' if planes else 'NO_SUPPORTED_PLANE',
        display_transform=dict(center_world=center.tolist(),axes_rows=axes.tolist(),length_scene=length),
        principal_axis_world=axes[0].tolist(),obb=dict(extents_scene_units=extent.tolist(),bounds='1st-to-99th percentile PCA box of partial cloud, not complete object'),
        seller_dimensions_mm=seller.tolist(),nominal_length_scale_scenario=dict(status='PRIOR_CONSTRAINED_NOT_MEASURED',
            approximate_LWH_mm=scaled.tolist() if seller[0]>0 else None,
            section_relative_disagreement=(scaled[1:]/seller[1:]-1).tolist() if np.all(seller>0) else None,
            applied_to_points_or_textures=False),
        head_disagreement_median_fraction=float(np.median(directdiff)),head_disagreement_p90_fraction=float(np.quantile(directdiff,.9)),
        cross_view_registration='NOT_PERFORMED',coherent_object_geometry='UNVERIFIED',
        raw_points_modified=False,metric_accuracy_verified=False,same_physical_piece_confirmed=job['record'].get('same_physical_piece_confirmed','unknown'),
        grade='UNKNOWN',faces=records,unobserved_faces='UNOBSERVED; no closed box faces are synthesized',
        evidence_states=['SELLER_REPORTED','OBSERVED_2D','VGGT_ESTIMATED','PRIOR_CONSTRAINED','UNOBSERVED'],
        parameters=dict(distance_gate_fraction=tol,normal_neighbors=18,ransac_trials=450,min_points=min_points,seed=int(job['record']['listing_id'])),
        limitations=['Shared model coordinates can still disagree between seller views; no same-piece assertion.',
        'The PCA box describes partial predicted support, not measured full timber dimensions.',
        'Plane projection is a reversible display regularization, not new evidence or increased inspected area.',
        'Texture visibility uses estimated depth, SAM2 and nearby same-view support, not ground truth occlusion.',
        'Neither planes nor lines are defect or strength classifiers.'])
    save(out/'surface_fit.json',fit)
    data=dict(points=q.tolist(),projected=projected.tolist(),rgb=rgb.tolist(),views=views.tolist(),
        assignment=assignment.tolist(),residual=residual.tolist(),planes=records,tolerance=tol,
        palette=['#3aa5ac','#e5b34d','#aa8bcb','#c57167','#85a44c','#6594ce'],summary=summary)
    import json
    (out/'surface_data.js').write_text('window.TIMBER_SURFACE='+json.dumps(data,separators=(',',':'))+';',encoding='utf-8')
    np.savez_compressed(out/'surface_projection.npz',source_world=points,source_views=views,source_pixels=pixels,
        display_original=q,display_projected=projected,assignment=assignment,residual=residual)
    render(out,records)

def textures(out,job,planes,records,q,views,center,axes,length,cameras,pred):
    folder=out/'textures';folder.mkdir(exist_ok=True);images=[np.asarray(Image.open(p).convert('RGB')) for p in job['images']]
    masks=np.array([cv2.erode(m.astype('uint8'),np.ones((3,3),np.uint8)) for m in pred['timber_masks']])
    atlas=Image.new('RGB',(1000,max(1,len(planes))*240),'#e9ede5');draw=ImageDraw.Draw(atlas)
    for p,rec in zip(planes,records):
        uv=(q[p['ids']]-p['origin'])@np.stack([p['u'],p['v']]).T;lo,hi=uv.min(0),uv.max(0)
        width,height=np.maximum(24,np.ceil((hi-lo)/(hi-lo).max()*job['config']['surface']['texture_long_side']).astype(int))
        uu,vv=np.meshgrid(np.linspace(lo[0],hi[0],width),np.linspace(lo[1],hi[1],height));grid=np.c_[uu.ravel(),vv.ravel()]
        local=p['origin']+grid[:,0,None]*p['u']+grid[:,1,None]*p['v'];world=local*length@axes+center
        hull=ConvexHull(uv);inside=np.all(grid@hull.equations[:,:2].T+hull.equations[:,2]<=1e-8,axis=1)
        tex=np.zeros((len(grid),4),np.uint8);winner=np.full(len(grid),-1,int);best=np.full(len(grid),-np.inf)
        for view in range(len(images)):
            vi=views[p['ids']]==view
            if vi.sum()<15:continue
            dist,_=cKDTree(uv[vi]).query(grid);e=np.array(cameras['extrinsics'][view]);k=np.array(cameras['intrinsics'][view])
            camera=world@e[:,:3].T+e[:,3];hom=camera@k.T;pix=hom[:,:2]/np.maximum(hom[:,2,None],1e-10)
            xy=np.rint(pix).astype(int);h,w=masks[view].shape
            valid=inside&(dist<=.015)&(camera[:,2]>0)&(xy[:,0]>=1)&(xy[:,0]<w-1)&(xy[:,1]>=1)&(xy[:,1]<h-1)
            ix=np.flatnonzero(valid);x,y=xy[ix,0],xy[ix,1];depth=pred['depth'][view,y,x]
            valid[ix]&=(masks[view,y,x]>0)&(np.abs(camera[ix,2]-depth)<=np.maximum(.02*depth,.008*length))
            cworld=-e[:,:3].T@e[:,3];normal=p['normal']@axes;ray=cworld-world
            cos=np.abs(ray@normal)/np.maximum(np.linalg.norm(ray,axis=1),1e-10)
            score=cos*np.sqrt(k[0,0]*k[1,1])/np.maximum(camera[:,2],1e-5)/(1+dist/.006)
            use=valid&(score>best)&(cos>.12)
            inv=np.array(cameras['transforms'][view]['input_to_original']);orig=np.c_[pix,np.ones(len(pix))]@inv.T
            sampled=cv2.remap(images[view],orig[:,0].reshape(height,width).astype('float32'),orig[:,1].reshape(height,width).astype('float32'),cv2.INTER_LINEAR).reshape(-1,3)
            tex[use,:3]=sampled[use];tex[use,3]=255;winner[use]=view;best[use]=score[use]
        name=f'patch_{rec["id"]+1:02d}';image=Image.fromarray(tex.reshape(height,width,4));image.save(folder/(name+'.png'))
        Image.fromarray((winner.reshape(height,width)+1).astype('uint8')).save(folder/(name+'_source.png'))
        quad=np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]])
        rec.update(texture_path='textures/'+name+'.png',texture_quad_display=(p['origin']+quad[:,0,None]*p['u']+quad[:,1,None]*p['v']).tolist(),
            texture_source='Original seller photo pixels projected by same-run cameras; not point colors',
            texture_status='ESTIMATED_DEPTH_CHECKED_PARTIAL_PROJECTION',texture_supported_pixels=int((winner>=0).sum()),
            texture_source_pixel_counts=[int((winner==i).sum()) for i in range(len(images))],
            texture_source_map='textures/'+name+'_source.png',source_map_encoding='0 UNOBSERVED; 1..N gallery view')
        thumb=image.copy();thumb.thumbnail((970,205));atlas.paste(thumb,(15,rec['id']*240+28),thumb)
        draw.text((15,rec['id']*240+8),f'Patch {rec["id"]+1} | support only | gaps UNOBSERVED',fill='#264e43')
    if not planes:draw.text((20,20),'UNOBSERVED: no supported planar texture',fill='#264e43')
    atlas.save(folder/'atlas.png')
    obj=['# Open experimental patches; no closed timber mesh','mtllib surface.mtl'];mtl=[]
    for i,r in enumerate(records):
        for v in r['texture_quad_display']:obj.append('v '+' '.join(map(str,v)))
        for uv in [(0,1),(1,1),(1,0),(0,0)]:obj.append('vt '+' '.join(map(str,uv)))
        obj += [f'usemtl patch{i}',f'f {4*i+1}/{4*i+1} {4*i+2}/{4*i+2} {4*i+3}/{4*i+3} {4*i+4}/{4*i+4}']
        mtl += [f'newmtl patch{i}','Kd 1 1 1',f'map_Kd {r["texture_path"]}','']
    (out/'surface.obj').write_text('\n'.join(obj)+'\n');(out/'surface.mtl').write_text('\n'.join(mtl)+'\n')

def render(out,records):
    w,h=1200,600;canvas=np.full((h,w,3),(238,241,233),np.uint8);yaw,pitch=-.52,.52
    def proj(p):
        p=np.asarray(p);x=np.cos(yaw)*p[:,0]+np.sin(yaw)*p[:,2];z=-np.sin(yaw)*p[:,0]+np.cos(yaw)*p[:,2]
        return np.stack([w/2+x*900,h/2-(np.cos(pitch)*p[:,1]-np.sin(pitch)*z)*900,np.sin(pitch)*p[:,1]+np.cos(pitch)*z],1)
    for r in sorted(records,key=lambda r:proj(r['texture_quad_display'])[:,2].mean()):
        tex=np.asarray(Image.open(out/r['texture_path']));th,tw=tex.shape[:2]
        matrix=cv2.getPerspectiveTransform(np.array([[0,0],[tw-1,0],[tw-1,th-1],[0,th-1]],np.float32),proj(r['texture_quad_display'])[:,:2].astype('float32'))
        warped=cv2.warpPerspective(tex,matrix,(w,h));alpha=warped[:,:,3:4]/255.;canvas=(warped[:,:,:3]*alpha+canvas*(1-alpha)).astype('uint8')
    im=Image.fromarray(canvas);d=ImageDraw.Draw(im);d.text((20,20),'Experimental photo-projected surfaces | open areas UNOBSERVED',fill='#244338')
    im.save(out/'surface_render.jpg',quality=88)
