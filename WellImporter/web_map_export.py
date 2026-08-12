# -*- coding: utf-8 -*-

import html
import json
from pathlib import Path

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsProject

from .well_number_field import feature_well_number


class WebMapExporter:
    """Экспортирует рабочие слои в автономную HTML-карту без QGIS runtime."""

    WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

    def __init__(self, project=None):
        self.project = project or QgsProject.instance()

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
            "title": self.project.title() or "Well Importer — карта скважин",
        }
        output = Path(html_path)
        if output.suffix.lower() != ".html":
            output = output.with_suffix(".html")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self._html(data), encoding="utf-8")
        return {
            "path": str(output),
            "points": len(data["points"]),
            "circles": len(data["circles"]),
        }

    def _features(self, layer, features):
        transform = QgsCoordinateTransform(layer.crs(), self.WGS84, self.project)
        field_names = layer.fields().names()
        result = []
        for feature in features:
            if not feature.hasGeometry() or feature.geometry().isEmpty():
                continue
            geometry = QgsGeometry(feature.geometry())
            geometry.transform(transform)
            try:
                geojson = json.loads(geometry.asJson(8))
            except TypeError:
                geojson = json.loads(geometry.asJson())
            attrs = {
                name: self._value(feature[name])
                for name in field_names
            }
            attrs["Номер скважины"] = feature_well_number(feature, layer, "")
            result.append({
                "id": int(feature.id()),
                "geometry": geojson,
                "properties": attrs,
            })
        return result

    def _style(self, layer, fill_default, stroke_default):
        fill = fill_default
        stroke = stroke_default
        try:
            renderer = layer.renderer()
            symbol = renderer.symbol() if renderer is not None else None
            if symbol is not None:
                color = symbol.color()
                if color.isValid():
                    fill = color.name()
                layers = symbol.symbolLayers()
                if layers:
                    try:
                        stroke_color = layers[0].strokeColor()
                        if stroke_color.isValid():
                            stroke = stroke_color.name()
                    except Exception:
                        pass
        except Exception:
            pass
        return {"fill": fill, "stroke": stroke}

    def _value(self, value):
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def _html(self, data):
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        title = html.escape(str(data.get("title") or "Well Importer — карта скважин"))
        return f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
html,body{{height:100%;margin:0;font-family:Arial,sans-serif;background:#14161a;color:#eee}}
#app{{height:100%;display:grid;grid-template-columns:320px 1fr}}
#side{{padding:14px;background:#1d2026;overflow:auto;box-shadow:2px 0 12px #0008;z-index:3}}
h1{{font-size:18px;margin:0 0 12px}} input,select,button{{box-sizing:border-box;width:100%;padding:9px;margin:4px 0;border:1px solid #444;border-radius:7px;background:#272b33;color:#eee}}
button{{cursor:pointer}} .row{{display:flex;gap:8px}} .row>*{{flex:1}} label{{display:block;margin:8px 0}} #mapWrap{{position:relative;overflow:hidden;background:#0f1318}}
#map{{width:100%;height:100%;touch-action:none;cursor:grab}} #map:active{{cursor:grabbing}}
#popup{{position:absolute;display:none;min-width:230px;max-width:340px;background:#20242c;border:1px solid #555;border-radius:9px;padding:10px;box-shadow:0 5px 25px #000b;pointer-events:none;z-index:5}}
.badge{{display:inline-block;padding:3px 7px;border-radius:10px;background:#343943;margin:2px;font-size:12px}}
.small{{font-size:12px;color:#aaa}} #result{{max-height:220px;overflow:auto;margin-top:8px}} .item{{padding:7px;border-bottom:1px solid #333;cursor:pointer}} .item:hover{{background:#292e37}}
@media(max-width:760px){{#app{{grid-template-columns:1fr;grid-template-rows:auto 1fr}}#side{{max-height:42vh}}}}
@media print{{#side{{display:none}}#app{{display:block}}#mapWrap{{height:100vh}}}}
</style>
</head>
<body>
<div id="app">
<aside id="side">
<h1>{title}</h1>
<input id="search" placeholder="Поиск скважины по номеру">
<div class="row"><button id="find">Найти</button><button id="home">Вся карта</button></div>
<label><input id="showPoints" type="checkbox" checked style="width:auto"> Скважины</label>
<label><input id="showCircles" type="checkbox" checked style="width:auto"> Площадные круги</label>
<div class="small">Колесо мыши — масштаб; перетаскивание — перемещение; клик по скважине — карточка.</div>
<div id="result"></div>
<hr style="border-color:#333">
<button onclick="window.print()">Печать текущей карты</button>
<div class="small">Экспорт Well Importer. Для просмотра QGIS не требуется.</div>
</aside>
<main id="mapWrap"><canvas id="map"></canvas><div id="popup"></div></main>
</div>
<script>
const DATA={payload};
const canvas=document.getElementById('map'), ctx=canvas.getContext('2d'), wrap=document.getElementById('mapWrap'), popup=document.getElementById('popup');
let view={{scale:1,dx:0,dy:0}}, drag=null, bounds=null;
const pointStyle=DATA.styles.points, circleStyle=DATA.styles.circles;
function coords(g){{let out=[]; (function walk(v){{if(Array.isArray(v)&&v.length>=2&&typeof v[0]==='number'&&typeof v[1]==='number')out.push(v);else if(Array.isArray(v))v.forEach(walk)}})(g.coordinates);return out}}
function calcBounds(){{let xs=[],ys=[]; [...DATA.points,...DATA.circles].forEach(f=>coords(f.geometry).forEach(p=>{{xs.push(p[0]);ys.push(p[1])}})); if(!xs.length)return [-1,-1,1,1]; return [Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)]}}
function resize(){{canvas.width=wrap.clientWidth*devicePixelRatio;canvas.height=wrap.clientHeight*devicePixelRatio;canvas.style.width=wrap.clientWidth+'px';canvas.style.height=wrap.clientHeight+'px';ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);draw()}}
function baseTransform(){{let b=bounds, w=wrap.clientWidth,h=wrap.clientHeight,pad=35, bw=Math.max(1e-9,b[2]-b[0]),bh=Math.max(1e-9,b[3]-b[1]),s=Math.min((w-2*pad)/bw,(h-2*pad)/bh);return {{s,x:pad-b[0]*s,y:h-pad+b[1]*s}}}}
function screen(p){{let t=baseTransform();return [(p[0]*t.s+t.x)*view.scale+view.dx,( -p[1]*t.s+t.y)*view.scale+view.dy]}}
function drawGeom(g,style){{let type=g.type,c=g.coordinates;ctx.strokeStyle=style.stroke;ctx.fillStyle=style.fill+'44';ctx.lineWidth=1.5;
function ring(r){{ctx.beginPath();r.forEach((p,i)=>{{let q=screen(p);i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1])}});ctx.closePath();ctx.fill();ctx.stroke()}}
if(type==='Polygon')c.forEach(ring);else if(type==='MultiPolygon')c.forEach(poly=>poly.forEach(ring));}}
function pointCoord(g){{if(g.type==='Point')return g.coordinates;if(g.type==='MultiPoint')return g.coordinates[0];return null}}
function draw(){{ctx.clearRect(0,0,wrap.clientWidth,wrap.clientHeight);if(document.getElementById('showCircles').checked)DATA.circles.forEach(f=>drawGeom(f.geometry,circleStyle));if(document.getElementById('showPoints').checked)DATA.points.forEach(f=>{{let p=pointCoord(f.geometry);if(!p)return;let q=screen(p);ctx.beginPath();ctx.arc(q[0],q[1],6,0,Math.PI*2);ctx.fillStyle=pointStyle.fill;ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.stroke()}})}}
function reset(){{view={{scale:1,dx:0,dy:0}};popup.style.display='none';draw()}}
function zoomToFeature(f){{let p=pointCoord(f.geometry);if(!p)return;let q=screen(p),cx=wrap.clientWidth/2,cy=wrap.clientHeight/2;view.dx+=cx-q[0];view.dy+=cy-q[1];view.scale=Math.max(view.scale,3);popup.style.display='none';draw()}}
function nearest(x,y){{let best=null,d=16;DATA.points.forEach(f=>{{let p=pointCoord(f.geometry);if(!p)return;let q=screen(p),dd=Math.hypot(q[0]-x,q[1]-y);if(dd<d){{d=dd;best={{f,q}}}}}});return best}}
function showPopup(hit){{let p=hit.f.properties,n=p['Номер скважины']||'';popup.innerHTML='<b>Скважина №'+esc(n)+'</b><br>'+['Год','WI_PARCEL','WI_CAD','Состояние'].map(k=>p[k]!==undefined&&p[k]!==''?'<span class="badge">'+esc(k)+': '+esc(p[k])+'</span>':'').join('');popup.style.left=Math.min(hit.q[0]+12,wrap.clientWidth-350)+'px';popup.style.top=Math.max(10,hit.q[1]-20)+'px';popup.style.display='block'}}
function esc(v){{return String(v??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]))}}
canvas.addEventListener('pointerdown',e=>{{drag={{x:e.clientX,y:e.clientY,dx:view.dx,dy:view.dy}};canvas.setPointerCapture(e.pointerId)}});canvas.addEventListener('pointermove',e=>{{if(drag){{view.dx=drag.dx+e.clientX-drag.x;view.dy=drag.dy+e.clientY-drag.y;draw()}}}});canvas.addEventListener('pointerup',e=>{{if(drag&&Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<5){{let r=canvas.getBoundingClientRect(),hit=nearest(e.clientX-r.left,e.clientY-r.top);hit?showPopup(hit):popup.style.display='none'}}drag=null}});
canvas.addEventListener('wheel',e=>{{e.preventDefault();let r=canvas.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top,f=e.deltaY<0?1.2:1/1.2,old=view.scale;view.scale=Math.min(30,Math.max(.3,old*f));let ratio=view.scale/old;view.dx=mx-(mx-view.dx)*ratio;view.dy=my-(my-view.dy)*ratio;draw()}},{{passive:false}});
function search(){{let q=document.getElementById('search').value.trim().toLowerCase(),res=DATA.points.filter(f=>String(f.properties['Номер скважины']||'').toLowerCase().includes(q));let box=document.getElementById('result');box.innerHTML=res.slice(0,50).map((f,i)=>'<div class="item" data-i="'+i+'">№'+esc(f.properties['Номер скважины']||'')+' — '+esc(f.properties['Год']||'')+'</div>').join('');[...box.children].forEach((el,i)=>el.onclick=()=>zoomToFeature(res[i]));if(res.length===1)zoomToFeature(res[0])}}
document.getElementById('find').onclick=search;document.getElementById('search').addEventListener('keydown',e=>{{if(e.key==='Enter')search()}});document.getElementById('home').onclick=reset;document.getElementById('showPoints').onchange=draw;document.getElementById('showCircles').onchange=draw;
bounds=calcBounds();window.addEventListener('resize',resize);resize();
</script>
</body></html>'''
