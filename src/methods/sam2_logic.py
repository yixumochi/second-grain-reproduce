import numpy as np
import cv2
from scipy.ndimage import binary_fill_holes

def clean(mask,erode=0):
    m=mask.astype('uint8');n,lab,stats,_=cv2.connectedComponentsWithStats(m)
    if n<2:return np.zeros_like(m)
    m=(lab==1+np.argmax(stats[1:,cv2.CC_STAT_AREA])).astype('uint8')
    m=binary_fill_holes(m).astype('uint8')
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    m=cv2.medianBlur(m,3)
    if erode:m=cv2.erode(m,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*erode+1,2*erode+1)))
    return m

def score_candidate(mask,rgb,ann,nominal):
    h,w=mask.shape;ys,xs=np.where(mask);area=len(xs)/(h*w)
    if area<.008 or area>.93:return None
    coords=np.c_[xs,ys].astype('float32');rect=cv2.minAreaRect(coords);dims=sorted(rect[1]);aspect=dims[1]/max(dims[0],1)
    compact=min(1,len(xs)/max(dims[0]*dims[1],1));cx,cy=xs.mean()/w,ys.mean()/h
    central=np.exp(-5*((cx-.5)**2+(cy-.5)**2))
    center_cover=float(mask[int(.44*h):int(.56*h),int(.44*w):int(.56*w)].mean())
    elongation=min(1,np.log(max(aspect,1))/np.log(6))
    border=(mask[0].mean()+mask[-1].mean()+mask[:,0].mean()+mask[:,-1].mean())/4
    lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB);colors=lab[mask.astype(bool)][::max(1,len(xs)//2000)]
    warmth=float(np.clip((np.median(colors[:,2])-127)/25,0,1))
    expected=nominal.get('length_mm',0)/(nominal.get('width_mm',0) or 1) if nominal.get('length_mm') else None
    dim_score=np.exp(-abs(np.log(aspect/max(expected,1)))/2) if expected else .5
    # Weak perspective-sensitive prior only; near views cannot follow full-stock aspect.
    weight=.15 if border>.05 else .3
    score=1.1*central+.8*center_cover+1.0*elongation+.8*compact+.7*min(area/.2,1)+.45*warmth+.6*float(ann['predicted_iou'])+.4*float(ann['stability_score'])+weight*dim_score-1.6*border-2*max(0,(area-.65)/.28)
    return dict(score=float(score),area_fraction=area,aspect=float(aspect),compactness=float(compact),center_cover=center_cover,
                centrality=float(central),border_contact=float(border),warmth=warmth,dimension_prior=float(dim_score),
                predicted_iou=float(ann['predicted_iou']),stability_score=float(ann['stability_score']))

def select_best(candidates):
    best=candidates[0]
    # Prefer a high-quality enclosing timber candidate over a single face when
    # their color and score agree. This rule is shared across all images.
    parents=[c for c in candidates if c['score']>=best['score']-.4
             and c['area_fraction']>best['area_fraction']*1.08 and c['area_fraction']<.72
             and c['predicted_iou']>.85 and abs(c['warmth']-best['warmth'])<.18
             and (c['mask']&best['mask']).sum()/max(1,best['mask'].sum())>.97]
    return max(parents,key=lambda c:c['area_fraction']) if parents else best
