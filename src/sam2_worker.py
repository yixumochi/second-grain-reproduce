"""Isolated pretrained SAM2 / VGGT calls, preserving the frozen inference recipes."""
from pathlib import Path
import sys,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.io_utils import *
from src.gpu_policy import policy,ensure_cuda,attention_context,autocast_context
import numpy as np
from PIL import Image,ImageOps,ImageDraw

def sam2(cfg,prepared,out):
 import torch,cv2
 sys.path.insert(0,str(ROOT/'vendor/sam2'))
 from sam2.build_sam import build_sam2
 from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
 from src.methods.sam2_logic import clean,score_candidate,select_best
 spec=policy(cfg,'sam2');ensure_cuda(torch,spec);print('SAM2 precision policy:',spec,flush=True)
 weight,model_info=checked_model(cfg,'SAM2.1 Hiera Tiny');settings=cfg['sam2'];meta=read(prepared/'inputs.json')
 cv2.setNumThreads(2);torch.set_num_threads(4)
 # Original program creates a fresh model per image. Keep this behavior.
 for index,item in enumerate(meta['images'],1):
  started=time.monotonic();original=ImageOps.exif_transpose(Image.open(prepared/item['copy_path'])).convert('RGB');im=original.copy()
  im.thumbnail((settings['max_image_side'],)*2,Image.Resampling.LANCZOS);rgb=np.asarray(im)
  model=build_sam2(settings['model_config'],str(weight),device='cuda',apply_postprocessing=settings['apply_postprocessing'])
  generator=SAM2AutomaticMaskGenerator(model,**{k:settings[k] for k in ['points_per_side','points_per_batch','pred_iou_thresh','stability_score_thresh','crop_n_layers','min_mask_region_area','use_m2m']})
  with torch.inference_mode(),attention_context(torch,spec),autocast_context(torch,spec):anns=generator.generate(rgb)
  candidates=[]
  for i,ann in enumerate(anns):
   mask=clean(ann['segmentation']);score=score_candidate(mask,rgb,ann,meta['nominal_dimensions'])
   if score:candidates.append(dict(index=i,mask=mask,**score))
  candidates.sort(key=lambda c:c['score'],reverse=True)
  if not candidates:raise RuntimeError('FAILED_MODEL: no eligible automatic timber candidate in view '+str(index))
  best=select_best(candidates);interior=clean(best['mask'],settings['erosion'])
  if not interior.any():raise RuntimeError('FAILED_MODEL: empty cleaned mask')
  stem=f'{index:02d}';Image.fromarray(interior*255).save(out/f'{stem}_mask_work.png')
  fullmask=Image.fromarray(interior*255).resize(original.size,Image.Resampling.NEAREST);fullmask.save(out/f'{stem}_mask.png')
  over=rgb.copy();inside=interior.astype(bool);over[inside]=(over[inside]*.6+np.array([30,220,140])*.4).astype('uint8')
  contours,_=cv2.findContours(interior,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);cv2.drawContours(over,contours,-1,(255,230,60),2);Image.fromarray(over).save(out/f'{stem}_overlay.png')
  save(out/f'{stem}_selection.json',dict(listing_id=cfg['listing_id'],image_index=index,source_sha256=item['sha256'],method='SAM2.1 Hiera Tiny automatic mask generator',manual_mask_used=False,manual_points_used=False,manual_boxes_used=False,text_prompts_used=False,all_sam_candidates=len(anns),eligible_candidates=len(candidates),selected={k:v for k,v in best.items() if k!='mask'},candidates=[{k:v for k,v in c.items() if k!='mask'} for c in candidates],original_size=list(original.size),work_size=list(im.size),elapsed_seconds=time.monotonic()-started,selection_rule='score ranking with quality/color-consistent enclosing-region preference',model=model_info))
  del model,generator,anns;torch.cuda.empty_cache();print('SAM2 view',stem,'complete',flush=True)
 save(out/'execution.json',dict(status='COMPLETE',image_count=len(meta['images']),new_gpu_inference=True,environment=environment(),precision_policy=spec,peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2))
