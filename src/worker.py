"""Bounded subprocess stages. The batch supervisor owns time limits and resume."""
from pathlib import Path
import sys,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image,ImageOps,ImageDraw
from src.io_utils import ROOT,read,save,sha,checked_model

def vggt(job,out):
    import torch
    from safetensors.torch import load_file
    sys.path.insert(0,str(ROOT/'vendor/vggt'))
    from vggt.models.vggt import VGGT
    from vggt.utils.load_fn import load_and_preprocess_images
    from vggt.utils.pose_enc import pose_encoding_to_extri_intri
    from vggt.utils.geometry import unproject_depth_map_to_point_map
    from src.mask_transform import transform_masks
    from src.methods.ply import ply
    torch.set_num_threads(4)
    if not torch.cuda.is_available() or torch.cuda.get_device_capability()[0]<8:
        raise RuntimeError('This profile requires a BF16-capable GPU, such as RTX4090D. No silent V100 fallback.')
    paths=job['images'];cfg=job['config']
    if len(paths)<2:raise RuntimeError('SINGLE_VIEW: multi-view geometry not attempted')
    weight,info=checked_model(cfg,'VGGT-1B')
    tensor=load_and_preprocess_images(paths,mode=cfg['loader_mode'])
    rgb=(tensor.permute(0,2,3,1)*255).round().clamp(0,255).byte().numpy()
    masks,valid,transforms=transform_masks(paths,job['masks'],cfg['loader_mode'],tensor.shape[-2:])
    if not masks.any():raise RuntimeError('No masked pixels survive official preprocessing')
    start=time.monotonic();model=VGGT().eval()
    state=load_file(str(weight),device='cpu');model.load_state_dict(state,strict=True);del state
    assert all(p.dtype==torch.float32 for p in model.parameters())
    model.cuda();tensor=tensor.cuda();torch.cuda.reset_peak_memory_stats()
    print('Official loader + model.forward; FP32 weights and BF16 autocast',flush=True)
    with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):pred=model(tensor)
    extr,intr=pose_encoding_to_extri_intri(pred['pose_enc'],tensor.shape[-2:])
    arr=lambda t:t.detach().float().cpu().numpy()[0]
    data=dict(depth=arr(pred['depth'])[...,0],confidence=arr(pred['depth_conf']),
        extrinsic=arr(extr),intrinsic=arr(intr),point_map=arr(pred['world_points']),
        point_confidence=arr(pred['world_points_conf']),rgb=rgb,timber_masks=masks,valid_pixels=valid)
    for name in ['depth','confidence','extrinsic','intrinsic','point_map']:
        if not np.isfinite(data[name]).all():raise RuntimeError('Non-finite '+name)
    depth_world=unproject_depth_map_to_point_map(data['depth'][...,None],data['extrinsic'],data['intrinsic'])
    data['depth_world']=depth_world
    np.savez_compressed(out/'predictions.npz',**data)
    save(out/'cameras.json',dict(intrinsics=data['intrinsic'].tolist(),extrinsics=data['extrinsic'].tolist(),
        transforms=transforms,convention='OpenCV world-to-camera',units='arbitrary_scene_units',source_hashes=[sha(Path(p)) for p in paths]))
    clouds={k:[] for k in ['points','direct_points','rgb','views','pixels']};fullp=[];fullc=[]
    for i in range(len(rgb)):
        eligible=(masks[i]>0)&(valid[i]>0)&np.isfinite(depth_world[i]).all(-1)
        if eligible.any():eligible &= data['confidence'][i]>=np.quantile(data['confidence'][i][eligible],.3)
        y,x=np.where(eligible);take=np.arange(0,len(x),max(1,int(np.ceil(len(x)/1500))))
        y,x=y[take],x[take]
        for k,v in [('points',depth_world[i,y,x]),('direct_points',data['point_map'][i,y,x]),('rgb',rgb[i,y,x]),
                    ('views',np.full(len(x),i)),('pixels',np.c_[x,y])]:clouds[k].append(v)
        ys,xs=np.where((valid[i]>0)&np.isfinite(depth_world[i]).all(-1));s=np.arange(0,len(xs),max(1,int(np.ceil(len(xs)/2500))))
        fullp.append(depth_world[i,ys[s],xs[s]]);fullc.append(rgb[i,ys[s],xs[s]])
        Image.fromarray(rgb[i]).save(out/f'{i+1:02d}_input.png')
        over=rgb[i].copy();m=masks[i]>0;over[m]=(over[m]*.55+np.array([40,220,160])*.45).astype('uint8')
        Image.fromarray(over).save(out/f'{i+1:02d}_mask_overlay.jpg',quality=85)
        d=data['depth'][i];lo,hi=np.quantile(d[valid[i]>0],[.02,.98]);visual=np.uint8(np.clip((d-lo)/max(hi-lo,1e-8),0,1)*255)
        Image.fromarray(visual).save(out/f'{i+1:02d}_depth.png')
    clouds={k:np.concatenate(v) for k,v in clouds.items()}
    np.savez_compressed(out/'timber_samples.npz',**clouds)
    ply(out/'timber_cloud.ply',clouds['points'],clouds['rgb']);ply(out/'scene_cloud.ply',np.concatenate(fullp),np.concatenate(fullc))
    np.savez_compressed(out/'depth_preview.npz',depth=data['depth'][:,::4,::4],confidence=data['confidence'][:,::4,::4],
        downsample_stride=np.array(4),full_intrinsics=data['intrinsic'])
    torch.cuda.synchronize()
    save(out/'execution.json',dict(status='COMPLETE',image_count=len(paths),seconds=time.monotonic()-start,
        checkpoint=info,source_revision='a288dd0f14786c93483e45524328726ab7b1b4ce',recipe=cfg['recipe'],
        input='ORIGINAL_RGB_WITH_SCENE_CONTEXT',model_weights_dtype='float32',autocast='bfloat16',
        peak_gpu_gib=torch.cuda.max_memory_reserved()/1024**3,point_tracks='NOT_REQUESTED',
        metric_accuracy_verified=False,same_physical_piece_confirmed=job['record'].get('same_physical_piece_confirmed','unknown')))

def lines(job,out):
    import cv2
    sys.path.insert(0,str(ROOT/'vendor/DeepLSD'))
    model=None;method='OpenCV LSD fallback';reason=None
    if not job.get('force_lsd'):
        try:
            import torch
            from deeplsd.models.deeplsd_inference import DeepLSD
            checkpoint=ROOT/'models/deeplsd_md.tar'
            if not checkpoint.is_file() or sha(checkpoint)!='56e9bae263977caa289ae49802987a67d4f00f376ae7e542176c8ae0a6cc2083':
                raise RuntimeError('Optional DeepLSD checkpoint absent or hash mismatch')
            model=DeepLSD({'detect_lines':True}).eval()
            # Only this checksum-pinned trusted upstream checkpoint is unpickled.
            model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=False)['model'],strict=True)
            model.cuda();method='DeepLSD MegaDepth pretrained'
        except Exception as e:reason=type(e).__name__+': '+str(e);model=None
    else:reason='Supervisor retried this optional stage once with CPU LSD after DeepLSD failure/timeout'
    records=[]
    for i,(photo,mask) in enumerate(zip(job['images'],job['masks']),1):
        im=ImageOps.exif_transpose(Image.open(photo)).convert('RGB');original_size=im.size;im.thumbnail((1024,1024))
        rgb=np.asarray(im);m=np.asarray(Image.open(mask).resize(im.size,Image.Resampling.NEAREST))>0
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);masked=gray.copy();masked[~m]=0
        if model is None:
            found=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(masked)[0]
            seg=np.empty((0,2,2)) if found is None else found.reshape(-1,2,2)
        else:
            import torch
            with torch.inference_mode():pred=model({'image':torch.from_numpy(masked[None,None].copy()).float().div(255).cuda()})
            seg=np.asarray(pred['lines'][0])
        # Reject boundary-generated lines; every sampled pixel must be in eroded timber.
        interior=cv2.erode(m.astype('uint8'),np.ones((5,5),np.uint8))>0;keep=[]
        for line in seg:
            xy=np.rint(line[0]+np.linspace(0,1,24)[:,None]*(line[1]-line[0])).astype(int)
            xy[:,0]=np.clip(xy[:,0],0,im.width-1);xy[:,1]=np.clip(xy[:,1],0,im.height-1)
            if np.all(interior[xy[:,1],xy[:,0]]) and np.linalg.norm(line[1]-line[0])>=20:keep.append(line)
        seg=np.asarray(keep).reshape(-1,2,2);overlay=rgb.copy();key=rgb.copy()
        for a,b in seg:cv2.line(overlay,tuple(np.rint(a).astype(int)),tuple(np.rint(b).astype(int)),(30,230,170),1,cv2.LINE_AA)
        longest=sorted(seg,key=lambda x:np.linalg.norm(x[1]-x[0]),reverse=True)[:12]
        for a,b in longest:cv2.line(key,tuple(np.rint(a).astype(int)),tuple(np.rint(b).astype(int)),(255,175,20),2,cv2.LINE_AA)
        Image.fromarray(overlay).save(out/f'{i:02d}_lines.png');Image.fromarray(key).save(out/f'{i:02d}_key_edges.png')
        xy=np.c_[np.where(m)[1],np.where(m)[0]];axis=None
        if len(xy)>2:_,_,v=np.linalg.svd(xy[::max(1,len(xy)//5000)]-xy.mean(0),full_matrices=False);axis=v[0].tolist()
        records.append(dict(photo=i,method=method,lines=seg.tolist(),long_edge_candidates=np.asarray(longest).tolist(),
            mask_principal_axis_2d=axis,coordinate_size=list(im.size),original_size=list(original_size),
            all_line_samples_inside_eroded_mask=True,limitation='Texture grain and cracks can also create lines; not verified physical edges. No inferred line completion used as observation.'))
    save(out/'lines.json',dict(method=method,fallback_reason=reason,images=records,constrains_3d_geometry=False))

def main():
    job=read(sys.argv[1]);out=Path(job['output']);out.mkdir(parents=True,exist_ok=True)
    if job['stage']=='sam2':
        from src.sam2_worker import sam2
        sam2(job['config'],Path(job['prepared']),out)
    elif job['stage']=='vggt':vggt(job,out)
    elif job['stage']=='lines':lines(job,out)
    elif job['stage']=='surface':
        from src.surfaces import build
        build(job,out)
    else:raise ValueError('Unknown stage')

if __name__=='__main__':main()
