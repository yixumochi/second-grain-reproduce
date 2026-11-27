"""Explicit precision/backend profiles. Never silently changes precision or models."""
from contextlib import nullcontext

def policy(cfg,stage):
 settings=cfg['sam2' if stage=='sam2' else 'vggt']
 dtype=settings.get('inference_dtype','bfloat16') if stage=='sam2' else settings['aggregator_dtype']
 backend=settings.get('attention_backend','auto')
 if dtype not in ['float32','float16','bfloat16']:raise ValueError('FAILED_INPUT: unsupported precision '+dtype)
 if backend not in ['auto','math']:raise ValueError('FAILED_INPUT: unsupported attention backend '+backend)
 if stage=='vggt' and settings['heads_dtype']!='float32':raise ValueError('FAILED_INPUT: VGGT heads must remain float32')
 return dict(dtype=dtype,attention_backend=backend,precision_fallback=False)

def check_hardware(spec,capability,cuda_version,arch_list=None):
 major,minor=capability
 if major<7:raise RuntimeError('FAILED_MODEL: this package requires compute capability >=7.0')
 if spec['dtype']=='bfloat16' and major<8:raise RuntimeError('FAILED_MODEL: native BF16 unavailable; select the explicit V100S profile')
 if major<8 and (not cuda_version or int(cuda_version.split('.')[0])>=13):raise RuntimeError('FAILED_MODEL: Volta requires a CUDA12-or-earlier PyTorch build; use setup_vision_v100s.sh')
 if major<8 and spec['attention_backend']!='math':raise RuntimeError('FAILED_MODEL: select explicit math attention on Volta')
 if major==7 and minor==0 and arch_list is not None and 'sm_70' not in arch_list:
  raise RuntimeError('FAILED_MODEL: this PyTorch wheel does not include sm_70; use the pinned V100S environment')

def ensure_cuda(torch,spec):
 if not torch.cuda.is_available():raise RuntimeError('FAILED_MODEL: CUDA is unavailable')
 check_hardware(spec,torch.cuda.get_device_capability(),torch.version.cuda,torch.cuda.get_arch_list())

def attention_context(torch,spec):
 if spec['attention_backend']=='auto':return nullcontext()
 # Torch2.5+ API also disables cuDNN attention; no optional flash/xformers build.
 try:
  from torch.nn.attention import sdpa_kernel,SDPBackend
  return sdpa_kernel(SDPBackend.MATH)
 except ImportError:return torch.backends.cuda.sdp_kernel(enable_flash=False,enable_math=True,enable_mem_efficient=False)

def autocast_context(torch,spec):
 return torch.autocast('cuda',enabled=False) if spec['dtype']=='float32' else torch.autocast('cuda',dtype=getattr(torch,spec['dtype']))

def smoke(torch,cfg):
 records={}
 for stage in ['sam2','vggt']:
  spec=policy(cfg,stage);ensure_cuda(torch,spec)
  with torch.inference_mode(),attention_context(torch,spec),autocast_context(torch,spec):
   q=torch.randn(1,4,128,64,device='cuda',dtype=getattr(torch,spec['dtype']))
   out=torch.nn.functional.scaled_dot_product_attention(q,q,q)
   torch.cuda.synchronize()
   if not torch.isfinite(out).all():raise RuntimeError('FAILED_MODEL: non-finite attention smoke output')
  records[stage]=dict(**spec,smoke='PASS')
 return records
