from PIL import Image
import numpy as np

def transform_masks(images, masks, mode, output_hw):
    """Map existing masks through the pinned loader's exact resize/crop/pad recipe.

    RGB inference itself ALWAYS uses upstream load_and_preprocess_images.
    This adapter affects only visualization masks after prediction.
    """
    out_h, out_w = output_hw
    mapped, valid, transforms = [], [], []
    for photo, maskfile in zip(images, masks):
        with Image.open(photo) as image:
            if image.getexif().get(274, 1) != 1:
                raise ValueError('EXIF orientation needs a separate explicit baseline; source images untouched')
            w, h = image.size
        if mode == 'pad' and h > w:
            nh=518; nw=round(w*(nh/h)/14)*14
        else:
            nw=518; nh=round(h*(nw/w)/14)*14
        crop_y=(nh-518)//2 if mode=='crop' and nh>518 else 0
        kept_h=min(nh,518) if mode=='crop' else nh
        left=(out_w-nw)//2; top=(out_h-kept_h)//2
        source=Image.open(maskfile).convert('L')
        if source.size != (w,h):raise ValueError('SAM2 mask/source dimensions disagree')
        resized=source.resize((nw,nh),Image.Resampling.NEAREST)
        resized=resized.crop((0,crop_y,nw,crop_y+kept_h))
        canvas=np.zeros((out_h,out_w),dtype='uint8');canvas[top:top+kept_h,left:left+nw]=np.asarray(resized)>0
        supported=np.zeros_like(canvas);supported[top:top+kept_h,left:left+nw]=1
        matrix=np.array([[nw/w,0,left+(nw/w-1)/2],[0,nh/h,top-crop_y+(nh/h-1)/2],[0,0,1.]])
        mapped.append(canvas);valid.append(supported)
        transforms.append(dict(original_size=[w,h],resized_size=[nw,nh],crop_y=crop_y,padding_left_top=[left,top],original_to_input=matrix.tolist(),input_to_original=np.linalg.inv(matrix).tolist()))
    return np.stack(mapped),np.stack(valid),transforms

