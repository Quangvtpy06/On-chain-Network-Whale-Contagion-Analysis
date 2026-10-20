"""Biểu đồ khám phá snapshot T08. HTML chạy offline, không ghi lại dữ liệu đồ thị."""
from html import escape
import json
from pathlib import Path

import networkx as nx
import numpy as np
import plotly.graph_objects as go


ENTITY_COLORS = {
    'CEX': '#2563eb', 'DEX': '#7c3aed', 'DeFi': '#0d9488',
    'Bridge': '#ea580c', 'Custodian': '#be185d', 'Contract': '#0891b2',
    'Protocol': '#4f46e5', 'Issuer': '#a16207', 'Other': '#475569', 'Unknown': '#94a3b8',
}
PLOT_CONFIG = dict(scrollZoom=True, responsive=True, displaylogo=False,
    doubleClick='reset', modeBarButtonsToRemove=['lasso2d', 'select2d'],
    toImageButtonOptions=dict(format='png', filename='t08_usdt_network', scale=2))


def make_graph_figure(graph):
    """Tách dữ liệu Plotly để dễ kiểm tra cấu hình và các lớp tương tác."""
    nodes = sorted(graph)
    n = len(nodes)
    # Không dùng volume làm lực hút: transfer lớn không có nghĩa là khoảng cách nhỏ.
    pos = nx.spring_layout(graph, seed=8, weight=None, iterations=100,
                           k=1.7 / np.sqrt(max(n, 1))) if n else {}
    degree = np.array([graph.degree(node) for node in nodes], dtype=float)
    log_degree = np.log1p(degree)
    sizes = 7 + 18 * np.sqrt(log_degree / max(float(log_degree.max(initial=0)), 1))
    if n > 500:
        sizes *= 0.75  # Giảm chồng lấp khi xem toàn mạng; zoom để xem chi tiết.
    figure = go.Figure()
    edge_rows = sorted(graph.edges(data=True), key=lambda row: (row[0], row[1]))
    values = np.array([d['weight'] for _, _, d in edge_rows], dtype=float)
    log_values = np.log1p(values)
    cuts = np.quantile(log_values, [0.4, 0.75, 0.95]) if len(values) else []
    buckets = np.searchsorted(cuts, log_values)
    for bucket in range(4):
        x, y = [], []
        for i, (u, v, _) in enumerate(edge_rows):
            if buckets[i] == bucket:
                x.extend([float(pos[u][0]), float(pos[v][0]), None])
                y.extend([float(pos[u][1]), float(pos[v][1]), None])
        figure.add_trace(go.Scattergl(x=x, y=y, mode='lines', hoverinfo='skip',
            line=dict(width=[0.5, 0.8, 1.2, 1.8][bucket], color=['#cbd5e1', '#a5b4c8', '#7e99b9', '#5486b8'][bucket]),
            opacity=0.28 if n > 500 else 0.45, showlegend=False, name='Luồng chuyển tiền'))
    ex, ey, angles, edge_text = [], [], [], []
    for u, v, data in edge_rows:
        p, q = pos[u], pos[v]
        ex.append(float(p[0] + 0.62 * (q[0]-p[0])))
        ey.append(float(p[1] + 0.62 * (q[1]-p[1])))
        angles.append(float(np.degrees(np.arctan2(q[0]-p[0], q[1]-p[1]))))
        edge_text.append(
            '<b>LUỒNG TIỀN RÒNG · u → v</b><br><br>'
            f'Ví gửi: {escape(u)}<br>Ví nhận: {escape(v)}<br><br>'
            f'<b>{data["weight"]:,.2f} USDT</b><br>'
            f'Số giao dịch khác nhau: {data.get("transaction_count", 0):,}<br>'
            f'Giá trị trung bình: {data.get("mean_value", 0):,.2f} USDT<br>'
            f'Gross của cặp còn giữ: {data.get("gross_value", 0):,.2f} USDT<br>'
            f'Số sự kiện nguồn: {data.get("event_count", 0):,}')
    edge_index = len(figure.data)
    figure.add_trace(go.Scatter(x=ex, y=ey, mode='markers', name='Chiều chuyển tiền',
        marker=dict(symbol='triangle-up', angle=angles, size=6, color='#4387bc', opacity=0.65,
                    line=dict(width=0.4, color='white')),
        text=edge_text, hovertemplate='%{text}<extra></extra>', showlegend=False))
    tooltips, symbols, entity_colors = [], [], []
    for node in nodes:
        data = graph.nodes[node]
        contract = data.get('is_contract')
        kind = 'Contract' if contract is True else ('Chưa xác minh' if contract is None else 'Không có bản ghi contract')
        entity = str(data.get('entity_type', 'Unknown'))
        symbols.append('diamond' if contract is True else 'circle')
        entity_colors.append(ENTITY_COLORS.get(entity, ENTITY_COLORS['Unknown']))
        tooltips.append(f'<b>{escape(str(data.get("entity_name", "Unknown")))}</b> · {escape(entity)}<br>'
            f'{escape(node)}<br><br>{kind}<br>'
            f'Bậc vào / ra: {graph.in_degree(node):,} / {graph.out_degree(node):,}<br>'
            f'Volume vào: {graph.in_degree(node, weight="weight"):,.2f} USDT<br>'
            f'Volume ra: {graph.out_degree(node, weight="weight"):,.2f} USDT')
    ticks = [d for d in [0, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000] if d <= degree.max(initial=1)]
    node_index = len(figure.data)
    figure.add_trace(go.Scatter(x=[float(pos[v][0]) for v in nodes], y=[float(pos[v][1]) for v in nodes],
        mode='markers', text=tooltips, customdata=nodes, hovertemplate='%{text}<extra></extra>',
        marker=dict(size=sizes.tolist(), color=log_degree.tolist(), symbol=symbols,
            colorscale='Plasma', cmin=0, cmax=max(float(log_degree.max(initial=0)), 1),
            opacity=0.93, line=dict(width=0.8, color='#ffffff'), showscale=bool(n),
            colorbar=dict(title=dict(text='Bậc nút<br><sup>in + out · thang log</sup>'),
                          thickness=13, len=0.66, tickvals=np.log1p(ticks).tolist(),
                          ticktext=[str(t) for t in ticks], outlinewidth=0, x=1.015)),
        name='Ví / contract', showlegend=False))
    # Lớp highlight tách riêng, không sửa dữ liệu cạnh/nút thật.
    highlight_index = len(figure.data)
    figure.add_trace(go.Scatter(x=[], y=[], mode='markers', marker=dict(size=28,
        color='rgba(0,0,0,0)', line=dict(color='#f97316', width=3)), hoverinfo='skip', showlegend=False))
    figure.update_layout(template='plotly_white', autosize=True, dragmode='pan', hovermode='closest',
        paper_bgcolor='white', plot_bgcolor='#f8fafc', margin=dict(l=12, r=112, t=14, b=14),
        font=dict(family='Segoe UI, Arial, sans-serif', size=13, color='#334155'),
        hoverlabel=dict(bgcolor='#142238', font=dict(color='white', size=12), bordercolor='#334155', align='left'),
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False, scaleanchor='x', scaleratio=1),
        uirevision='t08-snapshot', showlegend=False)
    if not n:
        figure.add_annotation(text='Không có giao dịch trong cửa sổ này', x=0.5, y=0.5,
                              xref='paper', yref='paper', showarrow=False)
    metadata = dict(nodes=nodes, degrees=degree.tolist(), logDegree=log_degree.tolist(),
        entityColors=entity_colors, nodeIndex=node_index, edgeIndex=edge_index, highlightIndex=highlight_index)
    return figure, metadata


def write_graph_html(graph, path, time_window, total_edges, total_volume):
    figure, metadata = make_graph_figure(graph)
    shown_volume = sum(d['weight'] for _, _, d in graph.edges(data=True))
    total = graph.number_of_edges() == total_edges
    scope = 'Toàn bộ cạnh' if total else f'Top {graph.number_of_edges():,} / {total_edges:,} cạnh'
    if not total and total_volume:
        scope += f' · {shown_volume / total_volume:.1%} volume cửa sổ'
    plot = figure.to_html(full_html=False, include_plotlyjs=True, div_id='network',
                          config=PLOT_CONFIG, default_height='100%', default_width='100%')
    legend = ''.join(f'<span><i style="background:{color}"></i>{escape(name)}</span>' for name, color in ENTITY_COLORS.items())
    info = dict(metadata, snapshot=str(time_window))
    template = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>T08 · USDT Network · __DATE__</title>
<style>
:root{--ink:#142238;--muted:#52657b;--line:#e2e8f0;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;background:#eef3f9;color:var(--ink);font:14px 'Segoe UI',Arial,sans-serif}
header{padding:22px 30px 16px;display:flex;gap:24px;align-items:center;justify-content:space-between}
.eyebrow{font-size:11px;letter-spacing:1.5px;font-weight:700;color:#42658a;margin-bottom:5px}h1{font-size:24px;letter-spacing:-.6px;margin:0}
.sub{color:var(--muted);font-size:12px;margin-top:7px}.stats{display:flex;gap:28px}.stat small{display:block;color:var(--muted);font-size:11px;margin-bottom:5px}.stat strong{font-size:21px;font-weight:650}
main{margin:0 20px 18px;background:white;border:1px solid var(--line);border-radius:16px;box-shadow:0 6px 24px #18395708;overflow:hidden}
.tools{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line);flex-wrap:wrap}.date{background:#eff6ff;color:#1d4ed8;padding:9px 12px;border-radius:8px;font-weight:650;margin-right:auto}
button,select,input{font:inherit;border:1px solid #cbd5e1;background:white;color:var(--ink);border-radius:8px;min-height:38px;padding:8px 11px}
button{cursor:pointer}button:hover{background:#eff6ff;border-color:#93c5fd}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #93c5fd;outline-offset:2px}
input{width:210px}#graph-wrap{height:calc(100vh - 244px);min-height:440px;position:relative}#network{height:100%;width:100%}
.legend{padding:10px 18px;border-top:1px solid var(--line);display:flex;gap:14px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:11px}.legend span{display:inline-flex;align-items:center;gap:5px}.legend i{width:8px;height:8px;border-radius:50%;display:inline-block}.help{margin-left:auto}
#message{color:#9a3412;font-size:12px;min-height:16px;padding:0 18px}#entity-legend{display:none}
.modebar{background:#fff!important;border:1px solid #e2e8f0;border-radius:8px;padding:3px!important}
@media(max-width:800px){header{padding:16px;display:block}h1{font-size:21px}.stats{margin-top:14px;gap:22px}.stat strong{font-size:17px}main{margin:0 8px 10px}.tools{gap:7px}.date{width:100%;margin:0}input{width:180px}#graph-wrap{height:65vh;min-height:400px}.help{margin-left:0}}
</style></head><body>
<header><div><div class="eyebrow">T08 / NETTED WHALE FLOWS</div><h1>Mạng lưới dòng tiền USDT</h1><div class="sub">Ethereum · Snapshot UTC · __SCOPE__</div></div>
<div class="stats"><div class="stat"><small>VÍ HIỂN THỊ</small><strong>__NODES__</strong></div><div class="stat"><small>CẠNH CÓ HƯỚNG</small><strong>__EDGES__</strong></div><div class="stat"><small>VOLUME HIỂN THỊ</small><strong>__VOLUME__</strong></div></div></header>
<main><div class="tools"><div class="date">__DATE__ · UTC</div>
<label for="color-mode">Màu nút</label><select id="color-mode"><option value="degree">Độ kết nối</option><option value="entity">Nhãn T07</option></select>
<form id="search-form" style="display:flex;gap:6px"><input id="wallet" aria-label="Địa chỉ ví cần tìm" placeholder="Tìm địa chỉ ví 0x…" autocomplete="off"><button type="submit">Tìm ví</button></form>
<button id="reset" type="button">Đặt lại góc nhìn</button></div><div id="graph-wrap">__PLOT__</div><div id="message" role="status" aria-live="polite"></div>
<div id="entity-legend" class="legend">__LEGEND__</div>
<div class="legend"><span>● Địa chỉ khác</span><span>◆ Contract đã xác minh</span><span>▲ Chiều u → v · rê chuột để xem cạnh</span><span class="help">Con lăn: zoom · Kéo: di chuyển · Nhấp đúp: khôi phục</span></div></main>
<script>
const meta=__META__, gd=document.getElementById('network'), message=document.getElementById('message');
document.getElementById('color-mode').addEventListener('change',function(){
 const byEntity=this.value==='entity';
 Plotly.restyle(gd,{'marker.color':[byEntity?meta.entityColors:meta.logDegree],'marker.showscale':!byEntity},[meta.nodeIndex]);
 document.getElementById('entity-legend').style.display=byEntity?'flex':'none';
});
document.getElementById('reset').addEventListener('click',()=>{
 Plotly.relayout(gd,{'xaxis.autorange':true,'yaxis.autorange':true});
 Plotly.restyle(gd,{x:[[]],y:[[]]},[meta.highlightIndex]);message.textContent='';
});
function focusWallet(index){
 const nodes=gd.data[meta.nodeIndex], x=nodes.x[index], y=nodes.y[index];
 Plotly.relayout(gd,{'xaxis.range':[x-.18,x+.18],'yaxis.range':[y-.18,y+.18]});
 Plotly.restyle(gd,{x:[[x]],y:[[y]]},[meta.highlightIndex]);
 Plotly.Fx.hover(gd,[{curveNumber:meta.nodeIndex,pointNumber:index}]);
 message.textContent='Đang xem ví '+meta.nodes[index]+' · bậc '+meta.degrees[index];
}
document.getElementById('search-form').addEventListener('submit',event=>{
 event.preventDefault();const value=document.getElementById('wallet').value.trim().toLowerCase();
 const index=meta.nodes.indexOf(value);
 if(index<0){message.textContent='Không có địa chỉ này trong snapshot / tập cạnh đang hiển thị.';return;}focusWallet(index);
});
gd.on('plotly_click',event=>{const point=event.points[0];if(point.curveNumber===meta.nodeIndex){
 Plotly.restyle(gd,{x:[[point.x]],y:[[point.y]]},[meta.highlightIndex]);
 message.textContent=point.customdata+' · bậc '+meta.degrees[point.pointNumber];}});
gd.setAttribute('role','img');gd.setAttribute('aria-label','Đồ thị dòng tiền USDT có hướng. Dùng ô tìm ví và nút đặt lại để khám phá.');
</script></body></html>'''
    replacements = {'__DATE__': escape(str(time_window)), '__SCOPE__': escape(scope),
        '__NODES__': f'{len(graph):,}', '__EDGES__': f'{graph.number_of_edges():,}',
        '__VOLUME__': f'{shown_volume/1e9:,.2f} tỷ' if shown_volume >= 1e9 else f'{shown_volume/1e6:,.2f} triệu',
        '__LEGEND__': legend, '__META__': json.dumps(info).replace('<', '\\u003c'), '__PLOT__': plot}
    for key, value in replacements.items():
        template = template.replace(key, value)
    Path(path).write_text(template, encoding='utf-8')
