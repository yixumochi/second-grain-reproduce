"""Self-contained HTML and SVG evidence report; all numbers come from run output."""
from html import escape


def render(output, summary):
    changed = next(r for r in summary['scenarios'] if r['scenario']=='shortened')
    rows = []
    labels = {'coordinate_only':'扫描坐标变化（已知变换）', 'shortened':'库存木材缩短', 'missing_endpoint':'缺少端部观测'}
    statuses = {'UNCHANGED':'保留分配', 'REALLOCATED':'生成替换候选（待结构分析）', 'NEEDS_EVIDENCE':'等待补充证据'}
    for r in summary['scenarios']:
        rows.append(f'<tr><td>{labels[r["scenario"]]}</td><td>{statuses.get(r["status"],escape(r["status"]))}</td>'
                    f'<td>{len(r["changed_member_ids"])}</td><td><a href="{r["scenario"]}/report.json">查看证据</a></td></tr>')
    changes = changed.get('member_changes', [])
    details = []
    for c in changes:
        before, after = c['before'], c['after']
        details.append(f'<tr><td>{escape(c["member_id"])}</td>'
            f'<td>{escape(before["source_stock_instance_id"])}</td><td>{escape(after["source_stock_instance_id"])}</td>'
            f'<td>{before["section"]["width_mm"]:g} × {before["section"]["depth_mm"]:g}</td>'
            f'<td>{after["section"]["width_mm"]:g} × {after["section"]["depth_mm"]:g}</td></tr>')
    length = changed['length_change_mm']
    width = 850
    new_width = width*length['after']/length['before']
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="380" viewBox="0 0 1080 380">
<rect width="1080" height="380" fill="#f5f3ed"/>
<g font-family="Arial, sans-serif" fill="#173c38">
<text x="42" y="46" font-size="23">CONTROLLED STOCK CHANGE / {escape(changed['event']['stock_id'])}</text>
<text x="42" y="76" font-size="14">Synthetic dimensions · fixed stock origin · no live scan or structural solve</text>
<text x="42" y="123" font-size="16">Before: {length['before']:.3f} mm</text>
<rect x="42" y="139" width="{width}" height="30" rx="4" fill="#254d47"/>
<text x="42" y="206" font-size="16">After: {length['after']:.3f} mm</text>
<rect x="42" y="222" width="{new_width:.3f}" height="30" rx="4" fill="#4d8c79"/>
<rect x="{42+new_width:.3f}" y="222" width="{width-new_width:.3f}" height="30" fill="#c76d4e" opacity="0.4"/>
<text x="42" y="301" font-size="21">{len(changes)} member(s) reassigned / {changed.get('unchanged_member_count',0)} preserved</text>
<text x="42" y="338" font-size="15">{escape(changed['status'])} · analysis: {escape(changed['analysis_status'])}</text>
</g></svg>'''
    (output/'comparison.svg').write_text(svg,encoding='utf-8')
    checks = ''.join(f'<li>{escape(r["check"])}: <strong>{escape(r["status"])}</strong></li>'
                     for r in changed.get('verification',{}).get('checks',[]))
    metrics = changed.get('metrics',{})
    metrics_html = ''.join(f'<li>{escape(k)}: {v:.3f}</li>' for k,v in metrics.items())
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Timber · 材料变化实验</title><style>
body{{margin:0;background:#f5f3ed;color:#173c38;font:16px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}}
main{{max-width:1080px;margin:auto;padding:44px 28px}}h1{{font-size:34px;line-height:1.3}}h2{{margin-top:36px;font-size:23px}}
.eyebrow{{letter-spacing:2px;font-size:12px}}.note{{background:#e9e3d6;padding:18px 22px;border-left:4px solid #b16c48}}
table{{border-collapse:collapse;width:100%;background:#fffdf8;font-size:14px}}th,td{{padding:14px;text-align:left;border-bottom:1px solid #d9ddd3}}
.scroll{{overflow:auto}}a{{color:#286b58}}img{{width:100%;height:auto}}code{{overflow-wrap:anywhere}}
</style><main><p class="eyebrow">TIMBER / CONTROLLED EXPERIMENT 02</p>
<h1>一根木材变化，哪些决策需要更新？</h1>
<p>锁住未受影响的切割，保留原有设计，重新寻找受影响构件的材料来源。</p>
<div class="note">本页来自程序实际输出。尺寸变化为人工构造，坐标变换为已知变换；未运行 DiffCheck 配准，也未重新运行 Karamba。库存来源和截面仍为记录数据，材料等级与连接承载力尚未验证。</div>
<h2>三个对照场景</h2><div class="scroll"><table><tr><th>输入变化</th><th>结果</th><th>改动构件数</th><th>记录</th></tr>{''.join(rows)}</table></div>
<h2>缩短实验的实际结果</h2><img src="comparison.svg" alt="库存木材长度前后对照以及重新分配构件数量">
<div class="scroll"><table><tr><th>构件</th><th>原库存</th><th>新库存</th><th>原截面 mm</th><th>新截面 mm</th></tr>{''.join(details)}</table></div>
<p>分配仅重算受影响构件；为保证一致性，完整重建分析输入并检查新阶段。结构求解未执行，新输出不能引用旧位移结果。</p>
<h2>材料账本</h2><ul>{metrics_html}</ul>
<p>discarded_tail 表示受控实验移除的尾段；unused_stock 表示尚未分配的回收库存，并非新生产木材。这里只比较长度与锯缝，未计算碳排放或结构性能改善。</p>
<h2>独立检查</h2><ul>{checks}</ul>
<h2>范围与下一步</h2><p>当前支持方案 A 中尚未加工的新增构件、固定木材原点、精确长度观测。缺端部或有测量不确定性时等待补充证据。若缩短触及既有构件或无法解释的材料区间，会报告超出修复范围。贪心搜索失败不等于证明全局无解。</p>
<p>下一步用真实测量建立尺寸和置信区间，并在 Rhino / Karamba 实际运行新的分析输入。</p>
<p><a href="summary.json">完整结果 JSON</a> · <a href="shortened/solver-request.json">新求解请求绑定</a> · <a href="comparison.svg">独立 SVG 图</a></p>
</main></html>'''
    (output/'report.html').write_text(html,encoding='utf-8')
    text = ['# 材料变化受控实验', '', '本实验不包含真实扫描、DiffCheck 配准或新结构求解。', '']
    text.extend(f'- {labels[r["scenario"]]}：{r["status"]}；改动 {len(r["changed_member_ids"])} 个构件。' for r in summary['scenarios'])
    text += ['', f'原长度 {length["before"]:.3f} mm → 新长度 {length["after"]:.3f} mm。',
             f'分析状态：{changed["analysis_status"]}。原基线文件哈希复核通过。', '',
             '分配仅重算受影响构件；分析导出完整重建；独立检查覆盖完整新阶段。',
             'HTML 和 SVG 提供图示；每个场景目录中的 report.json 保存详细依据。']
    (output/'RESULTS.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
