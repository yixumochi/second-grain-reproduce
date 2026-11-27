# 方法、来源与边界

| 部分 | 实际入口 | 来源 / 状态 |
|---|---|---|
| SAM2自动分割 | `src/sam2_worker.py` | [facebookresearch/sam2](https://github.com/facebookresearch/sam2/tree/2b90b9f5ceec907a1c18123530e92e794ad901a4)，Tiny，既有项目自动候选评分/清理，不是 Grounded-SAM2 |
| VGGT | `src/worker.py::vggt` | [facebookresearch/vggt](https://github.com/facebookresearch/vggt/tree/a288dd0f14786c93483e45524328726ab7b1b4ce)，官方 loader 和 `model.forward`，518 crop、FP32权重、BF16 autocast，原图完整图库 |
| Mask变换 | `src/mask_transform.py` | 从已经运行的官方 reference wrapper 复用；变换仅筛选预测，不遮背景输入模型 |
| 线检测 | `src/worker.py::lines` | [cvg/DeepLSD](https://github.com/cvg/DeepLSD/tree/f7d9d6258c0cd25d4f6eea882853565403d289be)，MegaDepth权重；`pytlsd==0.0.2`可选依赖；不可用则 OpenCV LSD并明示 |
| 木材面/纹理 | `src/surfaces.py` | 当前项目 CPU 推导：共享坐标PCA、同视图法线、RANSAC、有限距离支持、相机/估计深度/遮罩核对、原图像素投影，不是独立测量 |
| grade假设 | `src/grade.py` | WAC条件式旧材设计依据；不是CV classifier，不自动赋强度，不代表现场等级判定 |
| 批处理 | `scripts/run_batch.py` | 顺序子进程、有限超时、输入/源码/配置标识、原图哈希、失败续行、状态报告 |

SAM2 权重身份、字节数及SHA见 `configs/models.json`。VGGT 源码许可证是所复制 snapshot 中的 **VGGT License v1, July 29 2025**；不能把源码许可与权重许可混为一谈。模型下载前查看固定 Hugging Face model card 条款。权重不包含在本上传包。SAM2 Apache-2.0、DeepLSD MIT 及其他来源许可保留于 `licenses/`。历史 DiffCheck 许可作为来源资料保留，但本包没有运行其算法。

卖家图片来自用户已下载并校验的 Earthwise 数据集。包不授予公开重新分发这些图片的新许可。仅用户手动上传到其计算环境进行本项目实验。

纹理不由点云颜色插值生成；像素来自真实照片。原始照片分辨率大不代表有足够清晰度。模型估计的相机/深度可能错，纹理缝和几何偏移要保留供观察。每个纹理PNG透明处为无支撑；旁边的 `_source.png` 编码0未知、1..N图库视角。点投影仅改变派生显示坐标，原始世界坐标保存。

关于“中间漂浮”：旧 nominal box 是卖家完整尺寸先验，旧点云只反映局部估计且未和盒面验证对齐。不能用强行贴合盒面消除误差。新包不用卖家盒面约束平面位置；卖家长度只另列一个 `PRIOR_CONSTRAINED` 尺度场景及截面差异。无真实测量，不声明毫米精度。
