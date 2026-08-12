# -*- coding: utf-8 -*-

import html
import json
from pathlib import Path

from .web_map_export import WebMapExporter
from .well_number_field import feature_well_number


class ManagementWebMapExporter(WebMapExporter):
    """Создаёт автономную HTML-карту для передачи руководству.

    В HTML встраиваются данные и собственный canvas-renderer на чистом JavaScript:
    QGIS, Leaflet, OpenLayers и другие библиотеки на компьютере получателя не
    требуются. Карта поддерживает поиск, фильтры, карточки и печать выбранной
    пользователем области.
    """

    def export(self, point_layer, polygon_layer, html_path, selected_only=False):
        points = (
            list(point_layer.getSelectedFeatures())
            if selected_only else list(point_layer.getFeatures())
        )
        numbers = {
            feature_well_number(feature, point_layer, "").strip()
            for feature in points
            if feature_well_number(feature, point_layer, "").strip()
        }
        circles = [
            feature for feature in polygon_layer.getFeatures()
            if not selected_only
            or feature_well_number(feature, polygon_layer, "").strip() in numbers
        ]
        data = {
            "points": self._features(point_layer, points),
            "circles": self._features(polygon_layer, circles),
            "styles": {
                "points": self._style(point_layer, "#7b3fe4", "#ffffff"),
                "circles": self._style(polygon_layer, "#5c8fd8", "#24518c"),
            },
            "title": self.project.title() or "Карта скважин",
        }
        output = Path(html_path)
        if output.suffix.lower() != ".html":
            output = output.with_suffix(".html")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self._management_html(data), encoding="utf-8")
        return {
            "path": str(output),
            "points": len(data["points"]),
            "circles": len(data["circles"]),
        }

    def _management_html(self, data):
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        title = html.escape(str(data.get("title") or "Карта скважин"))
        return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box}}html,body{{height:100%;margin:0;font-family:Arial,sans-serif;background:#11151b;color:#edf0f5}}
#app{{height:100%;display:grid;grid-template-columns:330px 1fr}}#side{{background:#1c222b;padding:14px;overflow:auto;box-shadow:2px 0 14px #0008;z-index:5}}
h1{{font-size:19px;margin:0 0 12px}}label{{font-size:13px;color:#cbd1da}}input,select,button{{width:100%;padding:9px;margin:4px 0 9px;border-radius:7px;border:1px solid #46505e;background:#272f3a;color:#fff}}
button{{cursor:pointer}}button:hover{{background:#333e4d}}.row{{display:flex;gap:7px}}.row>*{{flex:1}}.small{{font-size:12px;color:#9ea8b6;line-height:1.4}}
#mapWrap{{position:relative;overflow:hidden;background:#0c1117}}#map{{width:100%;height:100%;touch-action:none;cursor:grab}}#map:active{{cursor:grabbing}}
#popup{{display:none;position:absolute;z-index:8;max-width:360px;background:#202833;border:1px solid #667384;padding:11px;border-radius:9px;box-shadow:0 8px 30px #000c;pointer-events:none}}
.badge{{display:inline-block;background:#343f4e;padding:3px 7px;border-radius:10px;margin:2px;font-size:12px}}#results{{max-height:190px;overflow:auto}}.result{{padding:6px;border-bottom:1px solid #37404b;cursor:pointer}}.result:hover{{background:#2b3440}}
#selectionInfo{{font-size:12px;color:#d5b96e;margin:4px 0 8px}}@media(max-width:800px){{#app{{grid-template-columns:1fr;grid-template-rows:auto 1fr}}#side{{max-height:46vh}}}}
@media print{{#side{{display:none}}#app{{display:block}}#mapWrap{{height:100vh}}}}
</style></head><body>
<div id="app"><aside id="side">
<h1>{title}</h1>
<label>Поиск скважины по номеру</label><input id="search" placeholder="Например: 15"><div class="row"><button id="find">Найти</button><button id="home">Вся карта</button></div><div id="results"></div>
<label>Год</label><select id="year"><option value="">Все годы</option></select>
<label>Земельный участок</label><select id="parcel"><option value="">Все участки</option></select>
<label><input id="pointsOn" type="checkbox" checked style="width:auto;margin-right:6px">Скважины</label>
<label><input id="circlesOn" type="checkbox" checked style="width:auto;margin-right:6px">Площадные круги</label>
<hr style="border-color:#3a424d">
<button id="selectPrint">Выбрать область для печати</button><div id="selectionInfo">Область печати не выбрана.</div><button id="printArea" disabled>Печать выбранной области</button><button id="printView">Печать текущего вида</button>
<p class="small">Масштаб: колесо мыши. Перемещение: перетаскивание. Клик по скважине: карточка. Для печати части карты нажмите «Выбрать область», затем протяните прямоугольник.</p>
<p class="small">Автономная карта Well Importer: для просмотра не требуется установленный QGIS.</p>
</aside><main id="mapWrap"><canvas id="map"></canvas><div id="popup"></div></main></div>
<script>
const DATA={payload};const wrap=document.getElementById('mapWrap'),canvas=document.getElementById('map'),ctx=canvas.getContext('2d'),popup=document.getElementById('popup');
let view={{scale:1,dx:0,dy:0}},bounds,drag=null,printMode=false,printStart=null,printRect=null;
const $=id=>document.getElementById(id), props=f=>f.properties||{{}}, num=f=>String(props(f)['Номер скважины']||'');
function esc(v){{return String(v??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]))}}
function allCoords(g){{let a=[];(function w(x){{if(Array.isArray(x)&&x.length>=2&&typeof x[0]==='number')a.push(x);else if(Array.isArray(x))x.forEach(w)}})(g.coordinates);return a}}
function extent(fs){{let xs=[],ys=[];fs.forEach(f=>allCoords(f.geometry).forEach(p=>{{xs.push(p[0]);ys.push(p[1])}}));return xs.length?[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)]:[-1,-1,1,1]}}
function visiblePoints(){{let y=$('year').value,p=$('parcel').value;return DATA.points.filter(f=>(!y||String(props(f)['Год']||'')===y)&&(!p||String(props(f)['WI_PARCEL']||'')===p))}}
function visibleNumbers(){{return new Set(visiblePoints().map(num))}}function visibleCircles(){{let ns=visibleNumbers();return DATA.circles.filter(f=>ns.has(num(f)))}}
function fillSelect(id,values,label){{let s=$(id);[...new Set(values.filter(Boolean).map(String))].sort((a,b)=>a.localeCompare(b,'ru',{{numeric:true}})).forEach(v=>{{let o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)}})}}
fillSelect('year',DATA.points.map(f=>props(f)['Год']),'Все годы');fillSelect('parcel',DATA.points.map(f=>props(f)['WI_PARCEL']),'Все участки');
function resize(){{let d=devicePixelRatio||1;canvas.width=wrap.clientWidth*d;canvas.height=wrap.clientHeight*d;canvas.style.width=wrap.clientWidth+'px';canvas.style.height=wrap.clientHeight+'px';ctx.setTransform(d,0,0,d,0,0);draw()}}
function base(){{let b=bounds,w=wrap.clientWidth,h=wrap.clientHeight,p=35,bw=Math.max(1e-9,b[2]-b[0]),bh=Math.max(1e-9,b[3]-b[1]),s=Math.min((w-2*p)/bw,(h-2*p)/bh);return{{s,x:p-b[0]*s,y:h-p+b[1]*s}}}}
function screen(p){{let t=base();return[(p[0]*t.s+t.x)*view.scale+view.dx,(-p[1]*t.s+t.y)*view.scale+view.dy]}}
function drawPolygon(g){{let polys=g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[];ctx.fillStyle=DATA.styles.circles.fill+'38';ctx.strokeStyle=DATA.styles.circles.stroke;ctx.lineWidth=1.4;polys.forEach(poly=>poly.forEach(r=>{{ctx.beginPath();r.forEach((p,i)=>{{let q=screen(p);i?ctx.lineTo(...q):ctx.moveTo(...q)}});ctx.closePath();ctx.fill();ctx.stroke()}}))}}
function pcoord(g){{return g.type==='Point'?g.coordinates:(g.type==='MultiPoint'?g.coordinates[0]:null)}}
function draw(){{ctx.clearRect(0,0,wrap.clientWidth,wrap.clientHeight);if($('circlesOn').checked)visibleCircles().forEach(f=>drawPolygon(f.geometry));if($('pointsOn').checked)visiblePoints().forEach(f=>{{let p=pcoord(f.geometry);if(!p)return;let q=screen(p);ctx.beginPath();ctx.arc(q[0],q[1],6,0,Math.PI*2);ctx.fillStyle=DATA.styles.points.fill;ctx.fill();ctx.strokeStyle='#fff';ctx.stroke()}});if(printRect){{ctx.save();ctx.setLineDash([7,5]);ctx.strokeStyle='#ffd75e';ctx.lineWidth=2;ctx.strokeRect(printRect.x,printRect.y,printRect.w,printRect.h);ctx.restore()}}}}
function reset(){{view={{scale:1,dx:0,dy:0}};bounds=extent(visiblePoints().length?[...visiblePoints(),...visibleCircles()]:[...DATA.points,...DATA.circles]);popup.style.display='none';draw()}}
function nearest(x,y){{let best=null,d=15;visiblePoints().forEach(f=>{{let p=pcoord(f.geometry);if(!p)return;let q=screen(p),dd=Math.hypot(q[0]-x,q[1]-y);if(dd<d){{d=dd;best={{f,q}}}}}});return best}}
function card(hit){{let p=props(hit.f);let rows=[['Номер скважины',p['Номер скважины']],['Год',p['Год']],['Участок',p['WI_PARCEL']],['Кадастровый номер',p['WI_CAD']],['Состояние',p['Состояние']]].filter(r=>r[1]!==undefined&&r[1]!==null&&String(r[1])!=='');popup.innerHTML='<b>Скважина №'+esc(p['Номер скважины']||'')+'</b><br>'+rows.slice(1).map(r=>'<span class="badge">'+esc(r[0])+': '+esc(r[1])+'</span>').join('');popup.style.left=Math.min(hit.q[0]+12,wrap.clientWidth-370)+'px';popup.style.top=Math.max(8,hit.q[1]-25)+'px';popup.style.display='block'}}
function zoomFeature(f){{let p=pcoord(f.geometry);if(!p)return;let q=screen(p),cx=wrap.clientWidth/2,cy=wrap.clientHeight/2;view.dx+=cx-q[0];view.dy+=cy-q[1];view.scale=Math.max(3,view.scale);draw()}}
function search(){{let q=$('search').value.trim().toLowerCase(),r=visiblePoints().filter(f=>num(f).toLowerCase().includes(q));$('results').innerHTML=r.slice(0,50).map((f,i)=>'<div class="result" data-i="'+i+'">№'+esc(num(f))+' — '+esc(props(f)['Год']||'')+'</div>').join('');[...$('results').children].forEach((e,i)=>e.onclick=()=>zoomFeature(r[i]));if(r.length===1)zoomFeature(r[0])}}
canvas.addEventListener('pointerdown',e=>{{let r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;if(printMode){{printStart={{x,y}};printRect={{x,y,w:0,h:0}};draw();return}}drag={{x:e.clientX,y:e.clientY,dx:view.dx,dy:view.dy}};canvas.setPointerCapture(e.pointerId)}});
canvas.addEventListener('pointermove',e=>{{let r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;if(printMode&&printStart){{printRect={{x:Math.min(printStart.x,x),y:Math.min(printStart.y,y),w:Math.abs(x-printStart.x),h:Math.abs(y-printStart.y)}};draw();return}}if(drag){{view.dx=drag.dx+e.clientX-drag.x;view.dy=drag.dy+e.clientY-drag.y;draw()}}}});
canvas.addEventListener('pointerup',e=>{{if(printMode&&printStart){{printStart=null;printMode=false;$('selectPrint').textContent='Выбрать область для печати';let ok=printRect&&printRect.w>20&&printRect.h>20;$('printArea').disabled=!ok;$('selectionInfo').textContent=ok?'Область печати выбрана.':'Область слишком мала — выберите заново.';draw();return}}if(drag&&Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<5){{let r=canvas.getBoundingClientRect(),h=nearest(e.clientX-r.left,e.clientY-r.top);h?card(h):popup.style.display='none'}}drag=null}});
canvas.addEventListener('wheel',e=>{{e.preventDefault();let r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,f=e.deltaY<0?1.2:1/1.2,old=view.scale;view.scale=Math.max(.3,Math.min(35,old*f));let k=view.scale/old;view.dx=x-(x-view.dx)*k;view.dy=y-(y-view.dy)*k;draw()}},{{passive:false}});
$('find').onclick=search;$('search').onkeydown=e=>{{if(e.key==='Enter')search()}};$('home').onclick=reset;['year','parcel','pointsOn','circlesOn'].forEach(id=>$(id).onchange=()=>{{popup.style.display='none';reset()}});$('printView').onclick=()=>window.print();
$('selectPrint').onclick=()=>{{printMode=!printMode;printRect=null;$('printArea').disabled=true;$('selectionInfo').textContent=printMode?'Протяните прямоугольник по карте...':'Область печати не выбрана.';$('selectPrint').textContent=printMode?'Отменить выбор области':'Выбрать область для печати';draw()}};
$('printArea').onclick=()=>{{if(!printRect)return;let d=devicePixelRatio||1,tmp=document.createElement('canvas');tmp.width=Math.max(1,Math.round(printRect.w*d));tmp.height=Math.max(1,Math.round(printRect.h*d));let tc=tmp.getContext('2d');tc.drawImage(canvas,printRect.x*d,printRect.y*d,printRect.w*d,printRect.h*d,0,0,tmp.width,tmp.height);let w=window.open('','_blank');if(!w){{alert('Браузер заблокировал окно печати. Разрешите всплывающие окна для этого HTML-файла.');return}}w.document.write('<!doctype html><html><head><meta charset="utf-8"><title>Печать выбранной области</title><style>body{{margin:0;text-align:center}}img{{max-width:100%;max-height:100vh}}</style></head><body><img src="'+tmp.toDataURL('image/png')+'"><script>window.onload=()=>window.print()<\/script></body></html>');w.document.close()}};
bounds=extent([...DATA.points,...DATA.circles]);window.addEventListener('resize',resize);resize();
</script></body></html>'''
