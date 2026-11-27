# 先五件测试，通过后再全库

先上传 `timber-pilot-5-4090d.zip`。它仍解压为 `timber-full-batch-4090d/`，保留同样源码、配置、完整商品索引，但只包含以下五件的 17 张原图，不会先下载或运行其他商品。

| 商品 | 图片 | 为什么测试 |
|---|---:|---|
| 117692 | 4 | 已有大截面木料对照；不能套 Stud |
| 120235 | 3 | 已有薄长板对照；检查照片投影 |
| 111575 | 3 | 已有分配关联木料、2×4 条件式 Stud 路径 |
| 117165 | 6 | 没有预带 SAM2 缓存；测试新自动分割和全库最大图库 |
| 115685 | 1 | 新自动分割、单图分支、层压产品范围；不能伪造多视图或实锯材等级 |

三件旧遮罩按哈希验证复用；后两件必须实际调用 SAM2。所有多图材料使用新官方 518 VGGT。历史示例只供对照。

## 运行

上传到 `/home/waas/` 后：

```bash
cd /home/waas
python -m zipfile -e timber-pilot-5-4090d.zip /home/waas
cd /home/waas/timber-full-batch-4090d
bash setup.sh
source /etc/waas-script/proxy.sh
bash download_models.sh
bash run_pilot.sh
```

若同版本完整包已解压并 setup / 模型准备成功，只需上传新增的 `run_pilot.sh` 与 `check_pilot.py` 到包根目录，或解压这个小包后直接执行最后一行；不要重复 setup / 下载。解压不会覆盖 `outputs/`、环境、权重或运行时文件。解压时不要让旧批处理同时运行。

`run_pilot.sh` 固定这五件、逐件执行，保留完整中间数组以便排错。最后运行只读检查，写 `outputs/pilot_acceptance.json`。结束后就停止，**没有自动全库启动**。

`READY_FOR_VISUAL_REVIEW` 仅表示程序与文件检查通过，还要查看 mask、几何和照片纹理是否有研究价值；不能因为进程退出码为0就判定重建正确。单图 `PARTIAL_RESEARCH_OUTPUT / SINGLE_VIEW_2D_ONLY` 是预期状态。

## 导出给我核查

```bash
bash export_results.sh --ids 117692 120235 111575 117165 115685
```

下载终端显示的 `exports/timber_review_…tar.gz`。也可把 `outputs/pilot_acceptance.json` 的内容发来。导出不包含 dense 数组，先看轻量结果；保留云端数组，确需诊断再取，避免重算。

需要核查：

1. 两个新材料确实完成自动 SAM2；未选中地面、标签等背景。
2. 6图 VGGT 能运行，四个多图样本有相机、木材点云、局部面和照片纹理；记录有用或失败的原因。
3. 原始/投影滑块可比较，原坐标和证据不因显示美化而改变。
4. Stud等仅为明确条件假设，117692/层压产品不错误套用。
5. 实测时间、显存和输出大小可接受，再确定全库执行窗口。

## 核查后才执行全库

还没有完整数据时，再上传 8.37 GB 的完整 `timber-full-batch-4090d.zip`，解压到**同一目录**。完整包不含 `outputs/`，不会抹掉测试结果；`run_pilot.sh` 和检查器在包根目录，不属于计算源码签名，不使原有测试缓存失效。

```bash
cd /home/waas
python -m zipfile -e timber-full-batch-4090d.zip /home/waas
cd /home/waas/timber-full-batch-4090d
bash run_all.sh
```

相同源码、输入和配置下，经过哈希校验的测试结果直接复用。若测试发现需要修正计算代码，改变源码会创建新的版本结果；不能无条件复用错误版本。
