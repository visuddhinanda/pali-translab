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
  return job.tasks || [];
}
function tally(ns){
  const t = {pending:0,running:0,done:0,failed:0,skipped:0};
  ns.forEach(n => t[n.status||'pending']++);
  return t;
}
function bar(ns, chars){
  const tot = ns.reduce((a,n)=>a+(chars?(n.chars||0):1),0) || 1;
  const seg = ss => ns.filter(n=>ss.includes(n.status||'pending'))
                      .reduce((a,n)=>a+(chars?(n.chars||0):1),0)/tot*100;
  return `<span class="bar mini"><i class="done" style="width:${seg(['done','skipped'])}%"></i>
    <i class="running" style="width:${seg(['running'])}%"></i>
    <i class="failed" style="width:${seg(['failed'])}%"></i></span>`;
}
const pill = s => `<span class="pill s-${s||'pending'}">${CN[s||'pending']}</span>`;

const STEP_CN = {translate:'翻译', review:'复核', revise:'修订',
                 copy:'照搬', harmonize:'统稿', evaluate:'评估', export:'导出'};
const LAYER_CN = {mula:'本文', atthakatha:'义注', tika:'复注',
                  mulatika:'根本复注', anutika:'随复注'};

function rng(t){
  if (t.layers) return Object.entries(t.layers).map(([b,r]) => `${b}:${r[0]}–${r[1]}`).join('　');
  return t.book ? `${t.book}:${t.start}–${t.end}` : '';
}
function taskLeaf(t){
  const lay = LAYER_CN[t.layer] || t.layer || '';
  return `<div class="leaf" data-status="${t.status||'pending'}">
    <span class="n">${t.id||''}</span>
    <span class="t">${STEP_CN[t.step]||t.step}　${lay}　${rng(t)}</span>
    <span class="n">${t.chars?num(t.chars)+' 字符':''}</span>${pill(t.status)}</div>`;
}

// 按步骤分组显示：一条流水线动辄上百个 task，平铺没法看。组内仍是计划顺序。
function stepGroup(step, ts){
  return `<details><summary><span class="t">${STEP_CN[step]||step}</span>
    <span class="n">${tally(ts).done}/${ts.length} 个任务</span>${bar(ts)}</summary>
    <div class="kids">${ts.map(taskLeaf).join('')}</div></details>`;
}

function jobNode(job){
  const us = unitsOf(job), t = tally(us);
  const order = ['translate','review','revise','copy','harmonize','evaluate','export'];
  const groups = order.filter(s => us.some(x => x.step===s))
    .map(s => stepGroup(s, us.filter(x => x.step===s))).join('');
  return `<details data-status="${job.status||'pending'}" data-name="${(job.title||'').toLowerCase()}">
    <summary><span class="n">#${job.id}</span><span class="t">${job.title||'（无本文）'}</span>
      <span class="n">${job.cs?`cs ${job.cs[0]}–${job.cs[1]} · `:''}${num(job.chars)} 字符 · ${t.done+t.skipped}/${us.length} 任务</span>
      ${bar(us)}${pill(job.status)}</summary>
    <div class="kids">${groups}</div></details>`;
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
  const jobs = (P.pipelines||[]).filter(j =>
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


def _as_view(proj):
    """schema 3 的项目**按阶段分组**，套进 schema 2 的视图结构——只为显示，不落盘。

    页面的折叠树本来是「流水线 → task」两层；schema 3 没有流水线，但有阶段表，
    一个阶段正好是一组同类 task，层级与读法都对得上，所以视图不必另写一套。
    """
    if proj.get("schema") != 3:
        return proj
    SETTLED = ("done", "skipped")
    by = {}
    for t in proj.get("tasks") or []:
        by.setdefault(t.get("stage", ""), []).append(t)
    pipes = []
    for st in proj.get("stages") or []:
        ts = by.get(st["id"], [])
        c = {}
        for t in ts:
            c[t.get("status", "pending")] = c.get(t.get("status", "pending"), 0) + 1
        nset = sum(c.get(k, 0) for k in SETTLED)
        status = ("done" if ts and nset == len(ts) else
                  "running" if c.get("running") else
                  "failed" if c.get("failed") else "pending")
        began = min((t.get("began") or "9" for t in ts), default="")
        ended = max((t.get("ended") or "" for t in ts), default="")
        pipes.append({"id": st["id"], "title": f'{st["id"]}（{len(ts)} 个 task）',
                      "status": status, "tasks": ts, "tries": 0,
                      "began": "" if began == "9" else began, "ended": ended,
                      "chars": sum(t.get("chars", 0) for t in ts),
                      "note": st.get("layer", "")})
    v = dict(proj)
    v["pipelines"] = pipes
    v.pop("tasks", None)              # 已经挂到各阶段下，别在页面里存两份
    return v


def render_project(proj):
    proj = _as_view(proj)
    jobs = proj.get("pipelines") or []
    us = [t for j in jobs for t in (j.get("tasks") or [])]
    SETTLED = ("done", "skipped")
    done_jobs = sum(1 for j in jobs if j.get("status") == "done")
    chunks = [t for t in us if t.get("step") == "translate"]
    chars = sum(c.get("chars", 0) for c in chunks)
    done_chars = sum(c.get("chars", 0) for c in chunks if c.get("status") in SETTLED)
    hs = [t for t in us if t.get("step") == "harmonize"]
    hs_done = sum(1 for c in hs if c.get("status") in SETTLED)
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
  <div class="stat"><b>{done_jobs} / {len(jobs)}</b><span>{'阶段' if proj.get('schema') == 3 else '流水线'}</span></div>
  <div class="stat"><b>{100.0 * done_chars / (chars or 1):.1f}%</b><span>翻译（按巴利字符）</span></div>
  <div class="stat"><b>{hs_done} / {len(hs)}</b><span>统稿单元</span></div>
  <div class="stat"><b>{chars:,}</b><span>巴利字符 · {len(us)} 个任务</span></div>
  <div class="stat"><b>{_esc(proj.get('method', 'default'))}</b><span>method</span></div>
</div>
<div class="toolbar">
  <input id="q" placeholder="搜章名或作业号" size="22">
  <select id="f">
    <option value="all">全部状态</option><option value="pending">未开始</option>
    <option value="running">进行中</option><option value="done">已完成</option>
    <option value="failed">失败</option><option value="skipped">跳过</option>
  </select>
  <button id="expand">全部展开</button><button id="collapse">全部收起</button>
  <span class="sub">显示 <b id="shown">0</b> 条流水线</span>
</div>
<div id="tree"></div>
<footer>数据内嵌在本文件里（<code>#data</code>），源头是
<code>workspace/projects/{_esc(proj['name'])}/project.json</code>；进度可由同目录的
<code>audit.log</code> 完全重建。重新导出：<code>python3 scripts/project.py export</code></footer>
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
