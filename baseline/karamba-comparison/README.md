# 原方案与替换候选：Karamba 实时求解准备

`inputs/` 是独立快照，`vendor/karamba_connected_builder.py` 是用户原项目的原样副本。
`input-manifest.json` 记录其来源与 SHA-256。脚本不修改 Grasshopper 文档、不切换原项目活动指针、不覆盖历史求解结果。

当前输入已经准备完毕；是否实际求解成功，应查看 `latest-run.json` 指向的当次 `run-status.json`，不能从本说明推断已完成求解。

本机已经完成两套实际求解，结论与限制见 `RESULTS.md`。在普通 Python 下运行 `python compare_results.py` 可重新核对结果文件、请求绑定、原方案存档一致性和独立力平衡，再生成报告，不需要重新调用 Rhino。

当前桥接使用 IronPython 2.7。输入绑定采用实际解析的 JSON 文件字节 SHA-256，避免不同 Python 版本的浮点序列化差异；CPython 语义摘要仍保留在请求中作为上游标识。材料显示文本中的非 ASCII 单位符号作转义记录，数值求解不受影响。

## 比较条件

- 使用固定案例的 A 方案，64 个物理构件（含支撑）、275 个节点、34 个支座。
- 两个工况分别为 `DL_STRUCTURAL_TIMBER` 与 `LL_FLOOR_ASSEMBLY_100PSF`，不代表设计规范荷载组合。
- 面板荷载、楼面活载、支座、数值连接和构件中心线保持一致。重力荷载定义相同，截面改变会改变构件自重。
- 候选只改动 `SECONDARY_BACKING__A__RAIL_01` 的来源及截面：95.25 × 146.05 mm → 19.05 × 88.9 mm。
- 所有物理木构件沿用相同的研究刚度材料行。当前不根据卖家树种记录推断弹性模量或强度等级。

## 执行

在已加载 Karamba 的 Rhino Python 环境执行 `run_in_rhino.py`，也可导入该模块并调用 `main(本目录绝对路径)`。
普通系统 Python 仅能做语法和输入检查，不能替代 Rhino 内部的 Karamba 求解。

每次运行建立新的 `runs/<UTC运行编号>/`，记录环境、输入绑定、组装截面/节点单位检查、板荷载投影、新求解结果或错误。若求解失败或返回需要审查的信息，不生成估计值，也不沿用存档值。

成功后报告构件上 21 个采样点的位移、内力和反力。采样最大值不等同于精确解析极值。最终承载力、连接承载力、基础和规范组合仍待验证；`approved_for_construction` 保持 false。

## 准备输入的复现方式

在 timber-baseline 目录运行：

```powershell
python tools/prepare_karamba_comparison.py --builder-source "原项目/grasshopper/karamba_connected_builder.py"
```

该命令重新生成本目录的请求快照。既有运行结果按独立运行编号保留，使用其绑定摘要核对对应的输入版本。

当前 Rhino-GH 桥接的基础技能已用于检查画布；通过 Rhino 执行工具运行前，需要 Rhino 的 MCP 服务可连接。
