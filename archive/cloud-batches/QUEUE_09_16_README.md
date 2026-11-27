# 09–16 后台队列

上传本补丁和 timber-batch-09-v3.zip 至 timber-batch-16-v3.zip 到 /home/waas。
已有正确原图无需重复上传。继续复用现有云端项目、run_batch_v31.sh、环境和模型。

```bash
cd /home/waas &&
python -m zipfile -e timber-queue-09-16.zip /home/waas &&
cd /home/waas/timber-full-batch-4090d &&
bash start_queue_09_16.sh
```

会自动解压缺少的计划内原图并验证 SHA-256，然后后台顺序运行09–16。
没有模型下载、环境安装或原始推理代码改动。共387条商品、1108张图片。
已完成且记录完整的同编号批次跳过；有运行失败或空间不足则停止后续批次并保留记录。
不自动重复失败项。旧04–08队列若仍活动，拒绝并行启动，不杀进程或删除锁文件。
原有每阶段超时继续有效，每批开始要求至少20GiB可用空间。

查看当前进度（自动切换日志）：

```bash
cd /home/waas/timber-full-batch-4090d
bash watch_queue_09_16.sh
```

Ctrl+C仅退出查看器，不影响后台任务。GPU实例须保持开机。
状态文件为 batch-evidence-v3/state/queue_09_16_status.json。
FINISHED_09_16_REVIEW_REQUIRED表示八批执行完成，STOPPED_ERROR含失败原因。
队列每5秒更新心跳；心跳不是模型有进展的证明，另显示日志更新时间及工作记录。
若刚启动尚无状态文件，前置校验可能仍在进行，请查看启动器给出的LOG，稍后重开查看器。
每批继续生成 timber_batch_XX_light_*.tar.gz；完整数值缓存仍须另行备份。
不把执行完成当作模型质量或材料等级通过。

本地验收：6项CPU模拟调度/查看器测试、两个shell语法检查通过。
真实Linux GPU队列尚未由助手运行；助手未连接远程机器。
