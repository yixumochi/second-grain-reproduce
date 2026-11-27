from pathlib import Path
import html,json,shutil
from src.io_utils import ROOT,read,save

def esc(x):return html.escape(str(x))
CSS='''*{box-sizing:border-box}body{margin:0;background:#f3f2ec;color:#233e39;font:15px/1.6 system-ui}main{max-width:1380px;margin:auto;padding:30px}h1{font-size:38px;line-height:1.2}h2{margin-top:32px}a{color:#22705c}section,.card{background:white;border:1px solid #cad5ca;border-radius:12px;padding:22px;margin:20px 0}.notice{background:#fff0cf;padding:16px;border-radius:8px}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:15px}.gallery img{width:100%;height:200px;object-fit:contain;background:#e8ede7}table{width:100%;border-collapse:collapse}td,th{padding:9px;text-align:left;border-bottom:1px solid #d7ded3}code{word-break:break-word}button,input,select{font:inherit;padding:8px}details{margin:15px 0}.status{font-size:12px;letter-spacing:.08em}.wide{max-width:100%}@media(max-width:700px){main{padding:15px}h1{font-size:27px}table{font-size:12px}td,th{padding:6px}}'''

def grade_html(g):
    candidates=g['conditional_candidates']
    names=' / '.join(c['species_design_assumption']+' · '+c['grade'] for c in candidates) or 'No named fallback supported by current size/product scope'
    return '<section id="grade"><span class="status">RESEARCH GRADE HYPOTHESIS · NOT APPLIED</span><h2>'+esc(names)+'</h2><p>'+esc(g['status'])+'</p><p class="notice">This is a conditional code design-basis scenario, not a grade predicted from photographs. Formal grade: UNKNOWN. Visual grade: UNRESOLVED. Structural verification: NOT RUN.</p>'+''.join('<p>Candidate '+esc(c['grade'])+' · nominal section scenario '+esc(c['nominal_section_scenario_in'])+' inches · '+esc(c['size_basis'])+'</p>' for c in candidates)+'<table><tr><th>Condition</th><th>Evidence</th></tr>'+''.join('<tr><td>'+esc(k)+'</td><td>'+esc(v)+'</td></tr>' for k,v in g['premises'].items())+'</table><p>Photo quality, unseen faces, decay absence and physical-piece identity remain unresolved. No defect detector or probability calibration is claimed.</p><a href="grade_hypothesis.json">Evidence and hypothesis JSON</a> · <a href="'+esc(g['source'])+'">Official used-lumber provision</a></section>'

def listing(record,folder,run):
    grade=read(folder/'grade_hypothesis.json');assets=folder/'assets';assets.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'assets/surface_viewer.js',assets/'surface_viewer.js')
    text='<header><a href="../../../index.html">← All materials</a><h1>'+esc(record['listing_id'])+' · '+esc(record['title'])+'</h1><p class="status">'+esc(run['status'])+'</p><p>Full available gallery · '+str(record['image_count'])+' images · same physical piece: '+esc(record.get('same_physical_piece_confirmed','unknown'))+'</p><a href="'+esc(record['source_url'])+'">Seller source</a> · <a href="run.json">Run status</a></header>'
    text+='<section><h2>01 / Seller photographs and automatic masks</h2><div class="gallery">'
    for i in range(1,record['image_count']+1):
        text+=f'<figure><a href="previews/{i:02d}.jpg"><img src="previews/{i:02d}.jpg" alt="Seller photo {i}"></a><figcaption>Photo {i} · original hash retained in input.json</figcaption>'
        mask=folder/f'sam2/{i:02d}_overlay.png'
        if mask.is_file():
            from PIL import Image
            preview=Image.open(folder/f'previews/{i:02d}.jpg').convert('RGBA')
            binary=Image.open(folder/f'sam2/{i:02d}_mask.png').convert('L').resize(preview.size,Image.Resampling.NEAREST)
            preview.putalpha(binary);preview.save(folder/f'previews/{i:02d}_timber.png')
            text+=f'<img src="sam2/{i:02d}_overlay.png" alt="Automatic SAM2 candidate {i}"><a href="previews/{i:02d}_timber.png">Transparent timber preview</a>'
        text+='</figure>'
    text+='</div></section><section><h2>02 / Processing record</h2><table><tr><th>Stage</th><th>Status</th><th>Details</th></tr>'
    for name,value in run.get('stages',{}).items():text+='<tr><td>'+esc(name)+'</td><td>'+esc(value['status'])+'</td><td>'+esc(value.get('detail',''))+'</td></tr>'
    text+='</table><p>Successful execution is not proof of coherent multi-view geometry. Low quality or mismatched gallery views stay explicit.</p></section>'
    surface=folder/'surface/surface_fit.json'
    if surface.is_file():
        f=read(surface);panel=(ROOT/'assets/surface_panel.html').read_text(encoding='utf-8')
        panel=panel.replace('data-asset-base="frame_preview/"','data-asset-base="surface/"').replace('href="frame_preview/','href="surface/')
        panel=panel.replace('117692 · CURRENT OFFICIAL RUN',esc(record['listing_id'])+' · THIS BATCH RUN')
        panel=panel.replace('Three estimated plane patches follow the returned timber points. The old dimension box no longer drives this view.',f'{f["estimated_patches"]} estimated surface patches. No seller-size box is imposed on the points.')
        panel=panel.replace('2562 × 356 × 340 mm',esc(f['seller_dimensions_mm'])+' mm')
        panel=panel.replace('Partial photo projection uses the 518px model images, existing SAM2 masks and sparse point support. Seams and alignment errors may remain; dense occlusion checks are pending.','Partial photo projection uses original seller pixels, 518px cameras, SAM2 masks, nearby same-view support and an estimated-depth consistency gate. This is not independently validated visibility.')
        panel=panel.replace('surface_comparison.jpg','surface_render.jpg').replace('SURFACE_README.md','surface_fit.json')
        text+=panel+'<p><a href="vggt/timber_cloud.ply">Timber cloud</a> · <a href="vggt/scene_cloud.ply">Scene cloud</a> · <a href="vggt/cameras.json">Cameras</a> · <a href="surface/surface.obj">Open UV mesh</a> · <a href="surface/textures/atlas.png">Atlas</a></p>'
        text+='<img class="wide" src="surface/surface_render.jpg" alt="Scientific render of photo-projected surfaces"><p>Depth/point-head disagreement median: '+f'{f["head_disagreement_median_fraction"]*100:.2f}% of estimated long extent. Internal consistency only, not accuracy.</p>'
    else:text+='<section><h2>03 / Object surfaces</h2><p>No supported surface output for this run. Review available photographs, masks and the failure record. No replacement geometry is fabricated.</p></section>'
    linefile=folder/'lines/lines.json'
    if linefile.is_file():
        l=read(linefile);text+='<section><h2>04 / Timber-only line cues</h2><p>'+esc(l['method'])+' · '+esc(l.get('fallback_reason') or 'Pretrained inference')+'</p><div class="gallery">'
        for i in range(1,record['image_count']+1):text+=f'<figure><img src="lines/{i:02d}_key_edges.png" alt="Key line candidates {i}"><figcaption>View {i} · candidates, not verified edges</figcaption></figure>'
        text+='</div><a href="lines/lines.json">Line coordinates and mask axis</a></section>'
    text+=grade_html(grade)+'<section><h2>What remains unknown</h2><p>Unobserved faces, verified nominal size, condition/decay, original grade route, species and material strength. No allocation acceptance or Karamba result is changed by this report. Single-image and product-scope exclusions apply only to the relevant method, not to the inventory.</p></section>'
    if surface.is_file():text+='<script src="surface/surface_data.js"></script><script src="assets/surface_viewer.js"></script>'
    (folder/'review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(record['listing_id'])+' · material evidence</title><style>'+CSS+'</style><main>'+text+'</main></html>',encoding='utf-8')

def index(out,records,results):
    rows=[];counts={}
    for r in records:
        item=results.get(r['listing_id'],{});status=item.get('status','NOT_RUN');counts[status]=counts.get(status,0)+1
        names=item.get('hypotheses',[]);label=' / '.join(names) or item.get('grade_status','NOT_EVALUATED')
        link='<a href="'+esc(item['report'])+'">'+esc(r['listing_id'])+'</a>' if item.get('report') else esc(r['listing_id'])
        rows.append('<tr><td>'+link+'</td><td>'+esc(r['title'])+'</td><td>'+str(r['image_count'])+'</td><td>'+esc(status)+'</td><td>'+esc(label)+'</td></tr>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>All timber material evidence</title><style>'+CSS+'</style><main><h1>Form Follows Availability</h1><p>'+str(len(records))+' listings · '+str(sum(r['image_count'] for r in records))+' verified source images</p><p class="notice">Research hypotheses only. Named Stud / No. 2 scenarios remain conditional, NOT applied grades. Geometry success never means strength verification.</p><p>'+esc(counts)+'</p><label>Search <input id="search" type="search" placeholder="ID, title, status, Stud…"></label><table><thead><tr><th>Listing</th><th>Title</th><th>Images</th><th>Run</th><th>Conditional hypothesis</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></main><script>document.getElementById("search").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))})</script></html>'
    (out/'index.html').write_text(page,encoding='utf-8');save(out/'batch_summary.json',dict(counts=counts,records=results))
