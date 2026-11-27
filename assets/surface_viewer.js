/* Partial planar surfaces and reversible DISPLAY projection. No evidence mutation. */
(() => {
  'use strict';
  const D=window.TIMBER_SURFACE, root=document.getElementById('surface-workspace');
  if(!D||!root)return;
  const $=id=>document.getElementById(id), canvas=$('sf-canvas'), ctx=canvas.getContext('2d');
  const range=$('sf-projection'), color=$('sf-color'), outline=$('sf-boundaries'), ghost=$('sf-ghost'), unassigned=$('sf-unassigned');
  const buttons=root.querySelectorAll('[data-sf-mode]');
  const base=root.dataset.assetBase||'frame_preview/';
  root.querySelectorAll('[data-sf-file]').forEach(a=>a.href=base+a.dataset.sfFile);
  let yaw=-.52,pitch=.52,zoom=1,drag=null,mode=D.planes.length?'texture':'raw',amount=0,loaded=0,failed=0;
  const textures=D.planes.map(p=>{const image=new Image();image.onload=()=>{loaded++;draw();};image.onerror=()=>{failed++;draw();};image.src=base+p.texture_path;return image;});
  const fitIndices=D.assignment.map((v,i)=>v>=0?i:-1).filter(i=>i>=0);
  const residuals=fitIndices.map(i=>D.residual[i]).sort((a,b)=>a-b);
  const median=residuals.length?residuals[Math.floor(residuals.length/2)]:0;
  function point(i,t){return D.points[i].map((v,j)=>v+(D.projected[i][j]-v)*t);}
  function setMode(next){mode=next;buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.sfMode===mode)));draw();}
  function draw(){
    const r=canvas.getBoundingClientRect(),ratio=Math.min(window.devicePixelRatio||1,2);
    if(!r.width||!r.height)return;
    canvas.width=Math.round(r.width*ratio);canvas.height=Math.round(r.height*ratio);
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.fillStyle='#eef1e9';ctx.fillRect(0,0,r.width,r.height);
    const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
    const scale=Math.min(r.width*.79,r.height*1.35)*zoom;
    function project(p){const x=cy*p[0]+sy*p[2],z=-sy*p[0]+cy*p[2];return[r.width/2+x*scale,r.height/2-(cp*p[1]-sp*z)*scale,sp*p[1]+cp*z];}
    const planes=D.planes.map((p,i)=>({p,i,poly:p.polygon_display.map(project),quad:p.texture_quad_display.map(project)}));
    planes.sort((a,b)=>a.quad.reduce((s,v)=>s+v[2],0)-b.quad.reduce((s,v)=>s+v[2],0));
    for(const {p,i,poly,quad} of planes){
      if(mode==='texture'){
        const img=textures[i];
        if(img&&img.complete&&img.naturalWidth>0){
          const a=quad[0],b=quad[1],d=quad[3];
          ctx.save();ctx.beginPath();poly.forEach((v,j)=>j?ctx.lineTo(v[0],v[1]):ctx.moveTo(v[0],v[1]));ctx.closePath();ctx.clip();
          ctx.transform((b[0]-a[0])/img.naturalWidth,(b[1]-a[1])/img.naturalWidth,(d[0]-a[0])/img.naturalHeight,(d[1]-a[1])/img.naturalHeight,a[0],a[1]);
          ctx.drawImage(img,0,0);ctx.restore();
        }
      }else if(mode==='projected'){
        ctx.save();ctx.fillStyle='rgba(140,174,151,.10)';ctx.beginPath();poly.forEach((v,j)=>j?ctx.lineTo(v[0],v[1]):ctx.moveTo(v[0],v[1]));ctx.closePath();ctx.fill();ctx.restore();
      }
      if(outline.checked){ctx.strokeStyle='#aa823b';ctx.lineWidth=1.2;ctx.setLineDash([5,4]);ctx.beginPath();poly.forEach((v,j)=>j?ctx.lineTo(v[0],v[1]):ctx.moveTo(v[0],v[1]));ctx.closePath();ctx.stroke();ctx.setLineDash([]);}
    }
    const t=mode==='projected'?amount:0;
    if(mode!=='texture'){
      if(mode==='projected'&&ghost.checked&&amount>0){
        ctx.fillStyle='rgba(70,90,79,.16)';for(const p of D.points){const v=project(p);ctx.fillRect(v[0],v[1],1.5,1.5);}
        ctx.strokeStyle='rgba(110,95,54,.35)';ctx.lineWidth=1;
        for(let j=0;j<fitIndices.length;j+=18){const i=fitIndices[j],a=project(D.points[i]),b=project(point(i,t));ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();}
      }
      const pts=D.points.map((p,i)=>({i,v:project(point(i,t))})).sort((a,b)=>a.v[2]-b.v[2]);
      for(const {i,v} of pts){
        if(D.assignment[i]<0&&!unassigned.checked)continue;
        let c;
        if(D.assignment[i]<0)c='#a1aaa5';
        else if(mode==='residual'||color.value==='residual'){const f=Math.min(1,D.residual[i]/D.tolerance);c=`rgb(${Math.round(43+185*f)},${Math.round(141-63*f)},${Math.round(136-79*f)})`;}
        else if(color.value==='source')c=D.palette[D.views[i]];
        else c=`rgb(${D.rgb[i].join(',')})`;
        ctx.fillStyle=c;ctx.fillRect(v[0],v[1],1.9,1.9);
      }
    }
    const descriptions={texture:failed?'A texture failed to load. Inspect the linked files.':`${loaded} / ${D.planes.length} photographed patches loaded. Transparent holes remain unobserved; no complete timber solid.`,raw:'Unchanged source coordinates. Gold outlines show the fitted support envelopes.',projected:`${Math.round(amount*100)}% display projection. Only supported points move; unassigned points remain unchanged.`,residual:'Original positions, colored by point-to-plane distance: teal = near, orange = farther. Grey points have no accepted plane.'};
    $('sf-status').textContent=descriptions[mode];
    $('sf-supported').textContent=D.summary.supported_points.toLocaleString();
    $('sf-unfitted').textContent=D.summary.unassigned_points.toLocaleString();
    $('sf-movement').textContent=((mode==='projected'?amount:0)*median*100).toFixed(3)+'%';
    $('sf-projection-value').textContent=Math.round(amount*100)+'%';
    ctx.fillStyle='#597163';ctx.font='12px system-ui';ctx.fillText(mode==='texture'?'Photo-projected planar patches · estimated geometry':'Shared scene frame · original coordinates retained',15,r.height-17);
  }
  range.addEventListener('input',()=>{amount=Math.max(0,Math.min(1,Number(range.value)/100));setMode('projected');});
  buttons.forEach(b=>b.addEventListener('click',()=>{if(b.dataset.sfMode==='projected'&&amount===0){amount=1;range.value='100';}setMode(b.dataset.sfMode);}));
  [color,outline,ghost,unassigned].forEach(e=>e.addEventListener('change',draw));
  $('sf-reset').addEventListener('click',()=>{yaw=-.52;pitch=.52;zoom=1;draw();});
  canvas.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.009;pitch=Math.max(-1.5,Math.min(1.5,pitch+(e.clientY-drag[1])*.009));drag=[e.clientX,e.clientY];draw();});
  canvas.addEventListener('pointerup',()=>drag=null);canvas.addEventListener('pointercancel',()=>drag=null);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.4,Math.min(4,zoom*Math.exp(-e.deltaY*.001)));draw();},{passive:false});
  canvas.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')yaw-=.08;else if(e.key==='ArrowRight')yaw+=.08;else if(e.key==='ArrowUp')pitch-=.08;else if(e.key==='ArrowDown')pitch+=.08;else if(e.key==='+'||e.key==='=')zoom=Math.min(4,zoom*1.1);else if(e.key==='-')zoom=Math.max(.4,zoom/1.1);else return;e.preventDefault();draw();});
  if(typeof ResizeObserver!=='undefined')new ResizeObserver(draw).observe(canvas);else window.addEventListener('resize',draw);
  window.timberSurfaceView={snapshot:()=>({mode,amount,inputPoints:D.points.length,supported:D.summary.supported_points,unassigned:D.summary.unassigned_points,texturesLoaded:loaded,grade:'UNKNOWN',rawModified:false}),displayPoint:i=>point(i,mode==='projected'?amount:0)};
  draw();
})();
