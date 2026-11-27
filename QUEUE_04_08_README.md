# 连续五批：04–08

用户已确认第三批完成，并明确授权连续运行 04–08。固定 250 条商品、695 张图片，08 结束即停，不启动 09。
这是现有 run_batch_v31.sh 的外层队列；不修改模型、算法、阈值、旧结果、环境或权重，不训练、不连接远程机器。

## 上传和启动

把 timber-queue-04-08.zip 和 timber-batch-04-v3.zip 至 timber-batch-08-v3.zip 上传到 /home/waas/。
如果某批原图已经正确解压，不必重复上传该批 ZIP。队列会校验已有原图，仅从 ZIP 解压缺少的、与计划 SHA-256 对应的图片。

```bash
cd /home/waas &&
python -m zipfile -e timber-queue-04-08.zip /home/waas &&
cd /home/waas/timber-full-batch-4090d &&
bash start_queue_04_08.sh
```

预检查先核对五批原图与已有结果。有缺包、损坏、正在进行的批任务时，不会启动 GPU。
通过后输出 Background queue PID 和 LOG 路径。在该日志看到 START batch 04 后，可以断开网页终端；实例本身须保持运行，不能关机或释放。
预检查可能需要一段时间读取几个 GB 的原图；没有重新下载素材。

## 查看状态

```bash
cd /home/waas/timber-full-batch-4090d
cat batch-evidence-v3/state/queue_04_08_status.json
```

current_log 是当前单批日志位置，可用 tail -n 30 加该路径查看。
全部完成时 status 为 FINISHED_04_08_REVIEW_REQUIRED。失败时为 STOPPED_ERROR，error 与 current_log 给出原因。
若后台进程在预检查阶段退出，详细原因在启动器输出的 LOG 文件中。

## 行为与停止条件

- 顺序执行，不并行占 GPU；每批继续沿用 SAM2 每图 120 秒、VGGT 每商品 480 秒、后处理每商品 180 秒的原有限时。
- 批内仍由原脚本跳过失败项并继续；整批结束如有失败项，外层队列停止后续批次，不自动重复失败任务。
- 纹理稀疏、对象歧义等质量标记不被当成计算失败，也不会自动变成质量通过。
- 已完成且记录齐全的同编号批次会跳过。先前部分失败或中断记录要求查看，不自动重跑。
- 解压时为原图额外预留空间；每批开始要求至少 20 GiB 可用。原模型阶段继续保留其自身 12 GiB 停止线，不删除任何缓存腾空间。
- 通过独立队列锁防止重复五批队列；不删除锁文件或结束未知进程。
- 每批原脚本照常生成小型报告包 timber_batch_XX_light_*.tar.gz。结果与原始缓存保留在 batch-evidence-v3/；不自动生成庞大的全量备份。

本地验收是 CPU 模拟调度和 shell 语法检查，不是五批真实 GPU 验收。复用了已在同一云端使用的单批推理入口。预计耗时可参考之前第二批的约 32 分钟，但图片数量、缓存复用及 GPU 负载会改变时间。

本包仅三个新增文件，不含数据、凭证、模型权重或环境。已有数据包和现有云端项目仍然需要保留。
