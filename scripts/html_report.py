# -*- coding: utf-8 -*-
"""project.json → 单文件 HTML（模板 + 内嵌 json，前端渲染折叠树）。

内嵌而不是 fetch 外部 json：这样双击就能打开、能直接发给别人、不受 file:// 的
CORS 限制。数据变了重新 `project.py export` 即可。

折叠用原生 `<details>`，不依赖任何库；JS 只做渲染与筛选。
"""
import html
import json

CSS = """
:root{--paper:#F5F6F8;--surface:#fff;--sunk:#EDEFF3;--ink:#14161C;--muted:#5A6273;
--rule:#DDE1E9;--done:#2E6B4F;--run:#34457E;--fail:#A63228;--wait:#8A8F9C;--warn:#8A6A1F;
--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
--sans:"IBM Plex Sans",-apple-system,"Segoe UI",Roboto,"Noto Sans SC",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
--paper:#11131A;--surface:#181B23;--sunk:#1F232C;--ink:#E6E8EE;--muted:#959DAD;
--rule:#2A2F3A;--done:#5FA982;--run:#8FA0E6;--fail:#E0685D;--wait:#767E8E;--warn:#C7A24E}}
:root[data-theme=dark]{--paper:#11131A;--surface:#181B23;--sunk:#1F232C;--ink:#E6E8EE;
--muted:#959DAD;--rule:#2A2F3A;--done:#5FA982;--run:#8FA0E6;--fail:#E0685D;--wait:#767E8E;--warn:#C7A24E}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 var(--sans)}
.wrap{max-width:1180px;margin:0 auto;padding:36px 20px 80px;display:flex;flex-direction:column;gap:22px}
h1{font-size:26px;margin:0;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:14px;margin:0}
a{color:inherit}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;
background:var(--rule);border:1px solid var(--rule);border-radius:2px;overflow:hidden}
.stat{background:var(--surface);padding:12px 14px;display:flex;flex-direction:column;gap:1px}
.stat b{font:500 20px/1.2 var(--mono);font-variant-numeric:tabular-nums}
.stat span{font-size:12px;color:var(--muted)}
.bar{height:6px;border-radius:3px;background:var(--sunk);overflow:hidden;display:flex}
.bar i{display:block;height:100%}
.bar i.done{background:var(--done)}.bar i.running{background:var(--run)}
.bar i.failed{background:var(--fail)}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input,select,button{font:13px var(--sans);color:var(--ink);background:var(--surface);
border:1px solid var(--rule);border-radius:2px;padding:6px 9px}
button{cursor:pointer}
details{background:var(--surface);border:1px solid var(--rule);border-radius:3px}
details+details{margin-top:6px}
summary{cursor:pointer;padding:9px 12px;display:flex;gap:10px;align-items:center;
list-style:none;font-size:14px}
summary::-webkit-details-marker{display:none}
summary:before{content:"▸";color:var(--muted);font-size:11px;width:10px}
details[open]>summary:before{content:"▾"}
summary .t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
summary .n{font-family:var(--mono);font-size:11.5px;color:var(--muted);
font-variant-numeric:tabular-nums;white-space:nowrap}
.kids{padding:2px 12px 12px 32px;display:flex;flex-direction:column;gap:4px}
.leaf{display:flex;gap:10px;align-items:center;padding:5px 10px;background:var(--sunk);
border-radius:2px;font-size:13px}
.leaf .t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.leaf .n,.pill{font-family:var(--mono);font-size:11px}
.pill{padding:1px 7px;border-radius:2px;border:1px solid currentColor;white-space:nowrap}
.s-done{color:var(--done)}.s-running{color:var(--run)}.s-failed{color:var(--fail)}
.s-pending{color:var(--wait)}.s-skipped{color:var(--muted)}
.mini{width:88px}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--surface)}
th,td{text-align:left;padding:9px 11px;border-bottom:1px solid var(--rule)}
th{font:500 11px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
tr:last-child td{border-bottom:none}
.tbl{border:1px solid var(--rule);border-radius:3px;overflow:hidden}
footer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--rule);padding-top:14px}
code{font-family:var(--mono);font-size:12.5px}
"""

JS = r"""
const P = JSON.parse(document.getElementById('data').textContent);
const CN = {pending:'未开始',running:'进行中',done:'已完成',failed:'失败',skipped:'跳过'};
const num = n => (n||0).toLocaleString();

function unitsOf(job){
  const u = [];
  (job.layers||[]).forEach(l => (l.chunks||[]).forEach(c => u.push(c)));
  const h = job.harmonize || {};
  (h.cross||[]).concat(h.layer||[]).forEach(c => u.push(c));
  if (job.export) u.push(job.export);
  return u;
}
function tally(ns){
  const t = {pending:0,running:0,done:0,failed:0,skipped:0};
  ns.forEach(n => t[n.status||'pending']++);
  return t;
}
function bar(ns, chars){
  const tot = ns.reduce((a,n)=>a+(chars?(n.chars||0):1),0) || 1;
  const seg = s => ns.filter(n=>(n.status||'pending')===s)
                     .reduce((a,n)=>a+(chars?(n.chars||0):1),0)/tot*100;
  return `<span class="bar mini"><i class="done" style="width:${seg('done')}%"></i>
    <i class="running" style="width:${seg('running')}%"></i>
    <i class="failed" style="width:${seg('failed')}%"></i></span>`;
}
const pill = s => `<span class="pill s-${s||'pending'}">${CN[s||'pending']}</span>`;

function leaf(n, label){
  return `<div class="leaf" data-status="${n.status||'pending'}">
    <span class="n">${n.id||''}</span><span class="t">${label}</span>
    <span class="n">${n.chars?num(n.chars)+' 字符':''}</span>${pill(n.status)}</div>`;
}

function layerNode(l){
  const cs = l.chunks||[];
  const inner = cs.length
    ? cs.map(c => leaf(c, `${l.book}:${c.start}–${c.end}`)).join('')
    : `<div class="leaf"><span class="t">（分块在跑的时候才切）</span></div>`;
  return `<details><summary><span class="t">${l.layer_cn||l.layer} · ${l.book}:${l.start}–${l.end}</span>
    <span class="n">${num(l.chars)} 字符 · ${cs.length} 分块</span>${bar(cs)}</summary>
    <div class="kids">${inner}</div></details>`;
}

const rng = c => Object.entries(c.layers||{})
  .map(([b,r]) => `${b}:${r[0]}–${r[1]}`).join('　');
function crossLabel(c){
  // direct 模式的那一块没有 cs 字段（整章一次做完），不能无脑读 c.cs[0]
  if (c.kind === 'direct') return `整章三层一次 · ${rng(c)}`;
  const part = c.part ? ` 第 ${c.part[0]}/${c.part[1]} 份` : '';
  return `横向 cs ${c.cs[0]}${c.cs[1]!==c.cs[0]?'–'+c.cs[1]:''}${part} · ${rng(c)}`;
}
function harmonizeNode(job){
  const h = job.harmonize; if(!h) return '';
  const cross = (h.cross||[]).map(c => leaf(c, crossLabel(c))).join('');
  const lay = (h.layer||[]).map(c => leaf(c, `纵向 ${c.layer_cn||c.layer} ${c.book}:${c.start}–${c.end}`)).join('');
  const all = (h.cross||[]).concat(h.layer||[]);
  const MODE = {direct:'整章三层一次', 'cross+layer':`横向 ${(h.cross||[]).length} + 纵向 ${(h.layer||[]).length}`,
                'layer-only':`只纵向 ${(h.layer||[]).length}（无 cs 对应）`};
  const mode = MODE[h.mode] || h.mode;
  return `<details><summary><span class="t">统稿 harmonize · ${mode}</span>
    <span class="n">${num(job.chars)} 字符</span>${bar(all)}</summary>
    <div class="kids">${cross}${lay}</div></details>`;
}

function jobNode(job){
  const us = unitsOf(job), t = tally(us);
  const layers = (job.layers||[]).map(layerNode).join('');
  const ex = job.export ? leaf(job.export, '导出 markdown') : '';
  return `<details data-status="${job.status||'pending'}" data-name="${(job.title||'').toLowerCase()}">
    <summary><span class="n">#${job.id}</span><span class="t">${job.title||'（无本文）'}</span>
      <span class="n">${job.cs?`cs ${job.cs[0]}–${job.cs[1]} · `:''}${num(job.chars)} 字符 · ${t.done}/${us.length} 单元</span>
      ${bar(us)}${pill(job.status)}</summary>
    <div class="kids">${layers}${harmonizeNode(job)}${ex}</div></details>`;
}

// 渲染整棵树时任何一个字段对不上都会中断整页——曾经 direct 模式的统稿块没有 cs
// 字段，`c.cs[0]` 一抛错，页面就只剩头部，看起来像"没有任务表"。逐个作业兜住，
// 坏掉的那个显示成一行错误，其余照常。
function safeJob(job){
  try { return jobNode(job); }
  catch(e){ return `<div class="leaf s-failed"><span class="n">#${job.id}</span>
    <span class="t">这个作业渲染失败：${e.message}</span></div>`; }
}
function render(){
  const q = (document.getElementById('q').value||'').toLowerCase();
  const f = document.getElementById('f').value;
  const jobs = P.jobs.filter(j =>
    (!q || (j.title||'').toLowerCase().includes(q) || String(j.id)===q) &&
    (f==='all' || (j.status||'pending')===f));
  document.getElementById('tree').innerHTML = jobs.map(safeJob).join('')
    || '<p class="sub">没有符合条件的作业。</p>';
  document.getElementById('shown').textContent = jobs.length;
}
document.getElementById('q').addEventListener('input', render);
document.getElementById('f').addEventListener('change', render);
document.getElementById('expand').addEventListener('click', () =>
  document.querySelectorAll('#tree details').forEach(d => d.open = true));
document.getElementById('collapse').addEventListener('click', () =>
  document.querySelectorAll('#tree details').forEach(d => d.open = false));
render();
"""


def _esc(s):
    return html.escape(str(s), quote=False)


def render_project(proj):
    jobs = proj["jobs"]
    us = []
    for j in jobs:
        for lay in j.get("layers", []):
            us += lay.get("chunks", [])
        h = j.get("harmonize") or {}
        us += h.get("cross", []) + h.get("layer", [])
        if j.get("export"):
            us.append(j["export"])
    done_jobs = sum(1 for j in jobs if j.get("status") == "done")
    chars = sum(j.get("chars", 0) for j in jobs)
    done_chars = sum(j.get("chars", 0) for j in jobs if j.get("status") == "done")
    data = json.dumps(proj, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="zh-Hans"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(proj.get('title', proj['name']))} · 项目进度</title>
<style>{CSS}</style></head><body><div class="wrap">
<header>
  <p class="sub"><a href="index.html">← 全部项目</a></p>
  <h1>{_esc(proj.get('title', proj['name']))}</h1>
  <p class="sub">项目 <code>{_esc(proj['name'])}</code> · 状态 {_esc(proj.get('state', 'idle'))}
   · channel <code>{_esc(proj.get('channel', ''))}</code> · 更新于 {_esc(proj.get('updated', ''))}</p>
</header>
<div class="stats">
  <div class="stat"><b>{done_jobs} / {len(jobs)}</b><span>作业</span></div>
  <div class="stat"><b>{len(us)}</b><span>可执行单元</span></div>
  <div class="stat"><b>{100.0 * done_chars / (chars or 1):.1f}%</b><span>按巴利字符</span></div>
  <div class="stat"><b>{chars:,}</b><span>巴利字符</span></div>
  <div class="stat"><b>{_esc(proj.get('method', 'default'))}</b><span>method</span></div>
</div>
<div class="toolbar">
  <input id="q" placeholder="搜章名或作业号" size="22">
  <select id="f">
    <option value="all">全部状态</option><option value="pending">未开始</option>
    <option value="running">进行中</option><option value="done">已完成</option>
    <option value="failed">失败</option>
  </select>
  <button id="expand">全部展开</button><button id="collapse">全部收起</button>
  <span class="sub">显示 <b id="shown">0</b> 个作业</span>
</div>
<div id="tree"></div>
<footer>数据内嵌在本文件里（<code>#data</code>），源头是
<code>workspace/projects/{_esc(proj['name'])}.json</code>；进度可由
<code>workspace/audit.log</code> 完全重建。重新导出：<code>python3 scripts/project.py export</code></footer>
</div>
<script id="data" type="application/json">{data}</script>
<script>{JS}</script></body></html>
"""


def render_index(rows):
    def row(r):
        c = r["job_counts"]
        return f"""<tr><td><a href="{_esc(r['name'])}.html"><b>{_esc(r['title'])}</b></a><br>
        <code>{_esc(r['name'])}</code></td>
        <td><span class="pill">{_esc(r['state'])}</span></td>
        <td>{c.get('done', 0)} / {r['jobs']}</td>
        <td>{r['pct']:.1f}%<br><span class="bar mini"><i class="done" style="width:{r['pct']}%"></i></span></td>
        <td>{r['chars']:,}</td>
        <td>{c.get('failed', 0) or '—'}</td>
        <td><code>{_esc(r['updated'])}</code></td></tr>"""

    body = "".join(row(r) for r in rows) or '<tr><td colspan="7">还没有项目</td></tr>'
    return f"""<!doctype html>
<html lang="zh-Hans"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pali-TransLab 项目索引</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>项目索引</h1>
<p class="sub">{len(rows)} 个项目 · 点标题看该项目的作业树</p></header>
<div class="tbl"><table>
<thead><tr><th>项目</th><th>状态</th><th>作业</th><th>进度</th><th>巴利字符</th><th>失败</th><th>更新</th></tr></thead>
<tbody>{body}</tbody></table></div>
<footer>开始 / 暂停：<code>python3 scripts/project.py pause &lt;name&gt;</code> ·
重新导出：<code>python3 scripts/project.py export</code></footer>
</div></body></html>
"""
