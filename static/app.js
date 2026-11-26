/* ===== 科研项目管理平台 · 前端逻辑 ===== */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const main = $('#main');
const modalRoot = $('#modal-root');
const toastRoot = $('#toast-root');
let VIEW = {};

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
async function api(path, opts = {}) {
  const cfg = { ...opts };
  if (cfg.body && !(cfg.body instanceof FormData) && typeof cfg.body !== 'string') {
    cfg.headers = { 'Content-Type': 'application/json' };
    cfg.body = JSON.stringify(cfg.body);
  }
  const res = await fetch(path, cfg);
  let data;
  try { data = await res.json(); } catch { data = { ok: false, error: '服务器返回异常' }; }
  if (!data.ok) throw new Error(data.error || '请求失败');
  return data.data;
}
function toast(msg, err = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  toastRoot.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}
function fmtNum(n) { return Number(n || 0).toLocaleString('zh-CN'); }
function tagColor(status) {
  return ({ '已交付':'green','授权':'green','录用':'blue','受理':'amber','在投':'gray' })[status] || 'gray';
}
function warnTag(level, text) {
  const c = { ok:'green', warn:'amber', danger:'red' }[level] || 'gray';
  return `<span class="tag tag-${c}">${esc(text)}</span>`;
}
function openModal(title, bodyHtml, footHtml, wide = false) {
  modalRoot.innerHTML = `<div class="mask"><div class="modal ${wide ? 'wide' : ''}">
    <div class="modal-head"><div class="modal-title">${title}</div><button class="modal-x" data-act="close-modal">×</button></div>
    <div class="modal-body">${bodyHtml}</div>
    ${footHtml ? `<div class="modal-foot">${footHtml}</div>` : ''}
  </div></div>`;
}
function closeModal() { modalRoot.innerHTML = ''; }
function confirmBox(msg, onYes) {
  openModal('请确认', `<div style="font-size:14px;line-height:1.8">${msg}</div>`,
    `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-danger" id="confirmYes">确定</button>`);
  $('#confirmYes').onclick = () => { closeModal(); onYes(); };
}
function val(id) { const el = $('#' + id); return el ? el.value.trim() : ''; }
function checked(id) { const el = $('#' + id); return el ? el.checked : false; }

/* ============ 路由 ============ */
function navigate(hash) { location.hash = hash; }
window.addEventListener('hashchange', route);
async function route() {
  const h = location.hash || '#/dashboard';
  const parts = h.replace(/^#\//, '').split('/');
  const page = parts[0];
  $$('#nav a').forEach(a => a.classList.toggle('active', a.dataset.nav === page));
  try {
    if (page === 'dashboard') await renderDashboard();
    else if (page === 'projects') await renderProjects();
    else if (page === 'project') await renderProject(parts[1], parts[2] || 'info');
    else if (page === 'achievements') await renderAchievements();
    else await renderDashboard();
  } catch (e) {
    main.innerHTML = `<div class="card"><div class="empty"><div class="e-ico">⚠</div><div class="e-t">加载失败：${esc(e.message)}</div></div></div>`;
  }
}

/* ============ 总览看板 ============ */
async function renderDashboard() {
  const d = await api('/api/dashboard');
  VIEW.dash = d;
  const warnHtml = d.warnings.length ? d.warnings.slice(0, 10).map(w => `
    <div class="warn-item ${w.warning}">
      <span class="tag tag-${w.warning === 'danger' ? 'red' : 'amber'}">${w.warning === 'danger' ? '红' : '黄'}</span>
      <span class="wt"><b>${esc(w.project)}</b> · ${esc(w.indicator)} — ${esc(w.reason)}，完成 ${w.progress}%</span>
      <a class="link" href="#/project/${w.project_id}/indicators">查看</a>
    </div>`).join('') : '<div class="empty" style="padding:16px">暂无预警</div>';
  const projRows = d.projects.map(p => `
    <tr>
      <td><a class="link" href="#/project/${p.id}/info"><b>${esc(p.name)}</b></a><div class="muted">${esc(p.code || '—')}</div></td>
      <td><span class="tag tag-blue">${esc(p.source || '未填写')}</span></td>
      <td>${esc(p.leader || '—')}</td>
      <td>${esc(p.start_date || '—')} ~ ${esc(p.end_date || '—')}</td>
      <td><div class="progress-cell"><div class="pbar ${p.progress >= 100 ? 'green' : p.progress >= 50 ? '' : 'amber'}"><i style="width:${p.progress}%"></i></div><b>${p.progress}%</b></div></td>
      <td class="num">${p.ach_count}</td>
      <td><button class="btn btn-sm" data-act="goto-project" data-id="${p.id}">进入</button></td>
    </tr>`).join('');
  main.innerHTML = `
    <div class="page-head"><div><div class="page-title">总览看板</div><div class="page-sub">项目进度、指标预警与成果归集全局视图</div></div>
      <div class="row"><button class="btn" data-act="goto-ach">成果库</button><button class="btn btn-primary" data-act="new-project">＋ 新建项目</button></div></div>
    <div class="stats">
      <div class="stat"><div class="stat-label">在管项目</div><div class="stat-val">${d.projects.length}<small> 个</small></div></div>
      <div class="stat green"><div class="stat-label">归集成果</div><div class="stat-val">${d.total_achievements}<small> 条</small></div></div>
      <div class="stat amber"><div class="stat-label">未标注资助号</div><div class="stat-val">${d.no_funding_count}<small> 条</small></div></div>
      <div class="stat red"><div class="stat-label">指标预警</div><div class="stat-val">${d.warnings.length}<small> 条</small></div></div>
    </div>
    <div class="card"><div class="card-head"><div class="card-title">项目进度</div><a class="link" href="#/projects">全部项目 →</a></div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>项目名称</th><th>来源</th><th>负责人</th><th>起止时间</th><th>整体完成度</th><th class="num">成果数</th><th></th></tr></thead>
      <tbody>${projRows || '<tr><td colspan="7" class="empty">暂无项目，点击右上角新建</td></tr>'}</tbody></table></div></div>
    <div class="card"><div class="card-head"><div class="card-title">指标预警</div><span class="muted">红色＝已超期/严重滞后，黄色＝临近截止/进度偏慢</span></div>${warnHtml}</div>`;
}

/* ============ 项目库 ============ */
async function renderProjects() {
  const list = await api('/api/projects');
  const cards = list.map(p => `
    <div class="proj-card" data-act="goto-project" data-id="${p.id}">
      <div class="proj-top"><div><div class="proj-name">${esc(p.name)}</div><div class="proj-code">立项编号：${esc(p.code || '—')}</div></div>
        <span class="tag tag-${p.status === '在研' ? 'blue' : p.status === '结题' ? 'green' : 'gray'}">${esc(p.status || '在研')}</span></div>
      <div class="proj-meta"><span class="tag tag-outline">${esc(p.source || '未分类')}</span><span class="tag tag-outline">负责人 ${esc(p.leader || '—')}</span><span class="tag tag-outline">经费 ${fmtNum(p.budget)} 万</span></div>
      <div style="display:flex;align-items:center;gap:9px"><div class="pbar" style="flex:1"><i style="width:${p.progress}%"></i></div><b style="font-size:12px">${p.progress}%</b></div>
      <div class="proj-foot"><span>${esc(p.start_date || '—')} ~ ${esc(p.end_date || '—')}</span><span>${p.ach_count || 0} 项成果</span></div>
    </div>`).join('');
  main.innerHTML = `
    <div class="page-head"><div><div class="page-title">项目档案</div><div class="page-sub">管理项目元信息、任务基准快照与变更版本</div></div>
      <button class="btn btn-primary" data-act="new-project">＋ 新建项目</button></div>
    <div class="project-grid">${cards || '<div class="empty" style="grid-column:1/-1"><div class="e-ico">▤</div><div class="e-t">还没有项目，点击「新建项目」开始</div></div>'}</div>`;
}

/* ============ 项目详情 ============ */
async function renderProject(pid, tab) {
  const p = await api('/api/projects/' + pid);
  VIEW.pid = pid; VIEW.tab = tab;
  const tabs = [
    ['info','项目档案'], ['indicators','指标看板'], ['achievements','关联成果'],
    ['finance','经费管理'], ['export','结题导出']
  ];
  const tabHtml = tabs.map(([k, t]) => `<div class="tab ${tab === k ? 'active' : ''}" data-act="ptab" data-tab="${k}">${t}</div>`).join('');
  let body = '';
  if (tab === 'info') body = await projectInfo(pid, p);
  else if (tab === 'indicators') body = await projectIndicators(pid, p);
  else if (tab === 'achievements') body = await projectAchievements(pid, p);
  else if (tab === 'finance') body = await projectFinance(pid, p);
  else body = projectExport(pid, p);
  main.innerHTML = `
    <div class="page-head"><div><div class="page-sub"><a class="link" href="#/projects">项目档案</a> / 项目详情</div>
      <div class="page-title">${esc(p.name)}</div>
      <div class="page-sub">${esc(p.code || '无编号')} · ${esc(p.source || '未分类')} · 负责人 ${esc(p.leader || '—')} · 整体完成度 <b style="color:var(--blue)">${p.progress.progress}%</b></div></div>
      <div class="row"><button class="btn btn-sm" data-act="edit-project" data-id="${pid}">编辑信息</button></div></div>
    <div class="tabs">${tabHtml}</div>${body}`;
}
/* ---- 项目档案子页 ---- */
async function projectInfo(pid, p) {
  const docs = await api(`/api/projects/${pid}/docs`);
  VIEW.docs = docs;
  const meta = [
    ['立项编号', p.code], ['项目来源', p.source], ['负责人', p.leader],
    ['起止时间', `${p.start_date || '—'} ~ ${p.end_date || '—'}`],
    ['经费总额', `${fmtNum(p.budget)} 万元`], ['合作单位', p.partners],
    ['项目状态', p.status], ['备注', p.note]
  ];
  const metaHtml = meta.map(([k, v]) => `<div class="kv-list" style="display:contents"><div class="k">${k}</div><div>${esc(v || '—')}</div></div>`).join('');
  const docTypes = ['申报书','任务书','年度报告','经费预算','变更批复','任务调整单','其他'];
  const docRows = docs.map(d => `
    <div class="doc-item">
      <div class="doc-ico">${d.is_baseline ? '🔒' : '📄'}</div>
      <div class="doc-body">
        <div class="doc-title">${esc(d.title || d.doc_type)}
          ${d.is_baseline ? '<span class="tag tag-red">原始任务基准</span>' : '<span class="tag tag-gray">变更版本</span>'}
          <span class="tag tag-blue">${esc(d.doc_type)}</span>
          ${d.version_tag ? `<span class="tag tag-outline">${esc(d.version_tag)}</span>` : ''}</div>
        <div class="doc-meta">${d.change_date ? `变更日期 ${esc(d.change_date)} · ` : ''}上传于 ${esc(d.uploaded_at)} ${d.file_name ? `· ${esc(d.file_name)}` : ''}</div>
        ${d.summary ? `<div class="doc-summary">${esc(d.summary)}</div>` : ''}
      </div>
      <div class="row" style="align-self:center">
        ${d.file_path ? `<a class="btn btn-sm" href="/api/files/${encodeURI(d.file_path)}" target="_blank">打开</a>` : ''}
        <button class="btn btn-sm btn-danger" data-act="del-doc" data-id="${d.id}">删</button>
      </div>
    </div>`).join('');
  return `
    <div class="hint-box">🔒 <b>基准快照锁定</b>：先把申报书/任务书标记为「原始任务基准」并上传原件；后续指标调整、延期等用「变更版本」单独上传并记录差异。结题时以最新批复版本为准，历史版本全部留痕可追溯。</div>
    <div class="card"><div class="card-head"><div class="card-title">项目元信息</div><button class="btn btn-sm" data-act="edit-project" data-id="${pid}">编辑</button></div>
      <div class="kv-list" style="grid-template-columns:110px 1fr;row-gap:9px">${metaHtml}</div></div>
    <div class="card"><div class="card-head"><div class="card-title">任务基准与版本留痕 <span class="tag tag-gray">${docs.length}</span></div>
      <button class="btn btn-sm btn-primary" data-act="new-doc" data-id="${pid}">＋ 上传文档/变更批复</button></div>
      ${docRows || '<div class="empty">尚未上传任何任务文档</div>'}
      ${docs.length > 1 ? `<div class="divider"></div><button class="btn btn-sm" data-act="diff-docs">查看版本对比说明</button><div id="diffBox"></div>` : ''}
    </div>`;
}

/* ---- 指标看板子页 ---- */
async function projectIndicators(pid, p) {
  const [inds, contents] = await Promise.all([
    api(`/api/projects/${pid}/indicators`), api(`/api/projects/${pid}/contents`)
  ]);
  VIEW.inds = inds; VIEW.contents = contents;
  const modeWeight = inds.length && inds.some(i => i.weight > 0);
  const grouped = {};
  inds.forEach(i => { const k = i.content_id || 0; (grouped[k] = grouped[k] || []).push(i); });
  const cntMap = {}; contents.forEach((c, idx) => cntMap[c.id] = idx + 1);
  let rcHtml = '';
  if (contents.length) {
    rcHtml = contents.map((c, idx) => {
      const list = grouped[c.id] || [];
      return `<div class="rc-block"><div class="rc-head"><div><div class="rc-title"><span class="rc-num">${idx + 1}</span>${esc(c.title)}</div>
          ${c.description ? `<div class="rc-desc">${esc(c.description)}</div>` : ''}</div>
          <div class="row"><span class="muted">${list.length} 项指标</span>
            <button class="btn btn-sm btn-ghost" data-act="edit-content" data-id="${c.id}">编辑</button>
            <button class="btn btn-sm btn-ghost" data-act="del-content" data-id="${c.id}">删</button></div></div>
        ${list.map(indRow).join('') || '<div class="muted" style="padding:10px 15px">该研究内容下暂无考核指标</div>'}</div>`;
    }).join('');
  }
  const ungrouped = grouped[0] || [];
  if (ungrouped.length) rcHtml += `<div class="rc-block"><div class="rc-head"><div class="rc-title"><span class="rc-num" style="background:#9ca3af">·</span>未归属研究内容的指标</div></div>${ungrouped.map(indRow).join('')}</div>`;
  const warnCount = inds.filter(i => i.warning !== 'ok').length;
  return `
    <div class="hint-box">📊 <b>两层指标结构</b>：第一层是研究内容（大纲级，来自申报书）；第二层是考核指标（来自任务书，可定量/定性）。点击指标名右侧「查支撑成果」可反查该指标由哪些成果支撑，直接用于写「指标完成情况」。完成度由关联成果自动计数，也可手动标记定性指标完成。</div>
    <div class="stats" style="grid-template-columns:repeat(4,1fr)">
      <div class="stat"><div class="stat-label">研究内容</div><div class="stat-val">${contents.length}</div></div>
      <div class="stat green"><div class="stat-label">考核指标</div><div class="stat-val">${inds.length}</div></div>
      <div class="stat amber"><div class="stat-label">预警指标</div><div class="stat-val">${warnCount}</div></div>
      <div class="stat"><div class="stat-label">计算模式</div><div class="stat-val" style="font-size:17px;padding-top:10px">${modeWeight ? '权重模式' : '计数模式'}</div></div>
    </div>
    <div class="card"><div class="card-head"><div class="card-title">研究内容（第一层）</div><button class="btn btn-sm" data-act="new-content" data-id="${pid}">＋ 研究内容</button></div>
      ${rcHtml || '<div class="empty">先添加研究内容，再为其添加考核指标</div>'}</div>
    <div class="card"><div class="card-head"><div class="card-title">独立考核指标（不归属任何研究内容）</div><button class="btn btn-sm btn-primary" data-act="new-indicator" data-id="${pid}">＋ 考核指标</button></div>
      ${ungrouped.length ? ungrouped.map(indRow).join('') : '<div class="muted">如需添加指标，请点击上方或研究内容块内的按钮</div>'}</div>`;
}
function indRow(i) {
  const pct = Math.min(i.progress, 100);
  const barCls = i.warning === 'danger' ? 'red' : i.warning === 'warn' ? 'amber' : pct >= 100 ? 'green' : '';
  return `<div class="ind-row">
    <div class="ind-main"><div class="ind-name">
      <span class="tag tag-${i.ind_type === 'quantitative' ? 'blue' : 'violet'}">${i.ind_type === 'quantitative' ? '定量' : '定性'}</span>
      ${esc(i.title)}
      ${i.warning !== 'ok' ? warnTag(i.warning, i.warning_reason) : (i.progress >= 100 ? '<span class="tag tag-green">已完成</span>' : '')}
      </div>
      <div class="ind-sub">${i.deadline ? `截止 ${esc(i.deadline)} · ` : ''}权重 ${i.weight || 0}% · ${i.achievements.length} 条支撑成果
        ${i.manual_done ? '· 已手动标记完成' : ''}</div></div>
    <div class="ind-metric"><b>${i.completed}</b> / ${i.target_value}${esc(i.unit || '')}<div class="muted" style="font-size:11px">${i.progress}%</div></div>
    <div class="progress-cell"><div class="pbar ${barCls}"><i style="width:${pct}%"></i></div></div>
    <div class="row">
      <button class="btn btn-sm" data-act="link-ach" data-id="${i.id}">查支撑成果</button>
      <button class="btn btn-sm btn-ghost" data-act="edit-indicator" data-id="${i.id}">编辑</button>
      <button class="btn btn-sm btn-ghost" data-act="toggle-done" data-id="${i.id}" data-done="${i.manual_done}">${i.manual_done ? '撤销完成' : '标记完成'}</button>
      <button class="btn btn-sm btn-ghost" data-act="del-indicator" data-id="${i.id}">删</button>
    </div></div>`;
}

/* ---- 关联成果子页 ---- */
async function projectAchievements(pid, p) {
  const list = await api('/api/achievements?project_id=' + pid);
  VIEW.projAchs = list;
  const rows = list.map(a => achRow(a)).join('');
  return `<div class="hint-box">🔗 成果库是全局独立的。一篇论文可以同时支撑多个项目；通过成果编辑里的「关联项目/指标」勾选即可复用。结题时按「考核指标 → 支撑成果」反查即可。</div>
    <div class="card"><div class="card-head"><div class="card-title">本项目关联成果 <span class="tag tag-gray">${list.length}</span></div>
      <div class="row"><button class="btn btn-sm" data-act="goto-ach">去成果库</button><button class="btn btn-sm btn-primary" data-act="new-ach" data-pid="${pid}">＋ 录入成果</button></div></div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>成果名称</th><th>类型</th><th>状态</th><th>等级</th><th>资助号标注</th><th>支撑指标</th><th>附件</th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="8" class="empty">尚无关联成果</td></tr>'}</tbody></table></div></div>`;
}
function achRow(a) {
  const inds = (a.indicators || []).map(x => esc(x.indicator_title || x.indicator_id)).join('、') || '—';
  return `<tr>
    <td><b>${esc(a.title)}</b><div class="muted">${esc(a.authors || '')} ${a.pub_date ? '· ' + esc(a.pub_date) : ''}</div></td>
    <td><span class="tag tag-outline">${esc(a.ach_type)}</span></td>
    <td><span class="tag tag-${tagColor(a.status)}">${esc(a.status)}</span></td>
    <td>${esc(a.level || '—')}</td>
    <td>${a.funding_ack ? '<span class="tag tag-green">已标注</span>' : '<span class="tag tag-red">未标注</span>'}</td>
    <td style="max-width:220px;font-size:12px">${inds}</td>
    <td>${a.file_path ? `<a class="link" href="/api/files/${encodeURI(a.file_path)}" target="_blank">打开</a>` : '—'}</td>
    <td><button class="btn btn-sm btn-ghost" data-act="edit-ach" data-id="${a.id}">编辑</button></td></tr>`;
}

/* ---- 经费管理子页 ---- */
async function projectFinance(pid, p) {
  const f = await api('/api/projects/' + pid + '/finance');
  VIEW.finance = f;
  const budgetRows = f.budget.map(b => `<tr>
    <td>${esc(b.category)}</td><td class="num">${fmtNum(b.budget)}</td><td class="num">${fmtNum(b.spent)}</td>
    <td><div class="progress-cell"><div class="pbar ${b.rate > 100 ? 'red' : b.rate >= 80 ? 'amber' : 'green'}"><i style="width:${Math.min(b.rate,100)}%"></i></div><b>${b.rate}%</b></div></td>
    <td class="muted">${esc(b.note || '')}</td>
    <td><button class="btn btn-sm btn-ghost" data-act="edit-budget" data-id="${b.id}">编辑</button>
        <button class="btn btn-sm btn-ghost" data-act="del-budget" data-id="${b.id}">删</button></td></tr>`).join('');
  const expRows = f.expenses.map(e => `<tr>
    <td>${esc(e.expense_date || '—')}</td><td class="num">${fmtNum(e.amount)}</td>
    <td>${esc(e.description || '—')}</td><td class="mono">${esc(e.voucher || '—')}</td>
    <td><button class="btn btn-sm btn-ghost" data-act="del-expense" data-id="${e.id}">删</button></td></tr>`).join('');
  const syncTip = f.in_sync
    ? `<div class="hint-box" style="background:var(--green-l);border-color:#bbf7d0;color:#166534">✓ 元信息经费总额与预算科目合计一致（${fmtNum(f.meta_budget)} 万）。修改项目元信息经费或预算科目时，两者会自动同步。</div>`
    : `<div class="warn-item warn"><span class="wt">⚠ 数据不一致：项目元信息经费 <b>${fmtNum(f.meta_budget)} 万</b>，预算科目合计 <b>${fmtNum(f.budget_total)} 万</b>。修改任一处即可自动同步，或</span><button class="btn btn-sm btn-primary" data-act="sync-budget" data-id="${pid}">以元信息为准同步</button></div>`;
  const chartMax = Math.max(1, ...f.budget.map(b => b.rate || 0));
  const chartHtml = f.budget.length ? `<div class="card"><div class="card-head"><div class="card-title">经费执行率横向柱状图</div><span class="muted">按各科目预算执行率（支出/预算）</span></div>
      ${f.budget.map(b => {
        const w = Math.max(2, (b.rate || 0) / chartMax * 100);
        const cls = b.rate > 100 ? 'red' : b.rate >= 80 ? 'green' : 'amber';
        return `<div style="display:grid;grid-template-columns:130px 1fr 92px;align-items:center;gap:10px;margin-bottom:9px">
          <div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(b.category)}</div>
          <div class="pbar ${cls}" style="height:14px"><i style="width:${w}%"></i></div>
          <div class="muted" style="text-align:right;font-size:12px">${b.rate}% · ${fmtNum(b.spent)}万</div>
        </div>`;
      }).join('')}</div>` : '';
  return `${syncTip}
    <div class="stats" style="grid-template-columns:repeat(4,1fr)">
      <div class="stat"><div class="stat-label">预算总额</div><div class="stat-val">${fmtNum(f.total_budget)}<small> 万</small></div></div>
      <div class="stat"><div class="stat-label">实际拨付金额 <button class="btn btn-sm btn-ghost" data-act="edit-disbursed" data-id="${pid}" style="margin-left:6px;padding:0 6px;vertical-align:middle">✎ 录入</button></div><div class="stat-val">${fmtNum(f.total_disbursed)}<small> 万</small></div><div class="muted" style="font-size:11px;margin-top:4px">项目级单值，与预算科目无关</div></div>
      <div class="stat green"><div class="stat-label">累计支出</div><div class="stat-val">${fmtNum(f.total_spent)}<small> 万</small></div></div>
      <div class="stat amber"><div class="stat-label">执行率</div><div class="stat-val">${f.total_rate}<small> %</small></div></div></div>
    <div class="card"><div class="card-head"><div class="card-title">预算科目与执行进度</div>
      <div class="row"><button class="btn btn-sm" data-act="import-excel" data-id="${pid}">📊 导入Excel（预算/支出）</button><button class="btn btn-sm btn-primary" data-act="new-budget" data-id="${pid}">＋ 预算科目</button></div></div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>科目</th><th class="num">预算(万)</th><th class="num">支出(万)</th><th>执行率</th><th>备注</th><th></th></tr></thead>
      <tbody>${budgetRows || '<tr><td colspan="6" class="empty">尚未设置预算科目</td></tr>'}</tbody></table></div></div>
    <div class="card"><div class="card-head"><div class="card-title">支出流水（Excel 导入）</div><span class="muted">支出通过上方 Excel 导入，不再逐笔手工录入；导入错误可删除单条</span></div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>日期</th><th class="num">金额(万)</th><th>说明</th><th>凭证号</th><th></th></tr></thead>
      <tbody>${expRows || '<tr><td colspan="5" class="empty">暂无支出记录，请导入 Excel</td></tr>'}</tbody></table></div></div>
    ${chartHtml}`;
}

/* ---- 结题导出子页 ---- */
function projectExport(pid, p) {
  return `<div class="hint-box">📦 <b>素材汇编导出</b>：不直接生成完整结题报告（各项目模板不同），而是导出 5 类核心素材——基本信息汇总表、考核指标完成情况对照表、成果清单、研究内容进展、经费汇总。复制到官方模板里微调即可。字段「资助号标注」已单独列出，方便结题审查自查。</div>
    <div class="card"><div class="card-head"><div class="card-title">导出格式</div></div>
      <div class="row" style="gap:14px">
        <a class="btn btn-primary" href="/api/export/${pid}/docx">⬇ 导出 Word（.docx）</a>
        <a class="btn" href="/api/export/${pid}/md">⬇ 导出 Markdown（.md）</a>
      </div>
      <div class="divider"></div>
      <div class="muted">Word 版含可直接粘贴的表格；Markdown 版适合复制到支持 MD 的编辑器或兼容系统。两份素材内容一致。</div>
    </div>
    <div class="card"><div class="card-title" style="margin-bottom:10px">导出内容包含</div>
      <div class="row" style="gap:10px;flex-wrap:wrap">
        <span class="tag tag-outline">① 项目基本信息汇总表</span>
        <span class="tag tag-red">② 考核指标完成情况对照表（核心）</span>
        <span class="tag tag-outline">③ 成果清单（含附件索引）</span>
        <span class="tag tag-outline">④ 研究内容进展简述</span>
        <span class="tag tag-outline">⑤ 经费执行汇总</span>
      </div></div>`;
}

/* ============ 成果库（全局） ============ */
async function renderAchievements() {
  const projects = await api('/api/projects');
  const kw = VIEW.achKw || '';
  const list = await api('/api/achievements' + (kw ? '?kw=' + encodeURIComponent(kw) : ''));
  VIEW.achAll = list; VIEW.projects = projects;
  const typeGroups = {};
  list.forEach(a => (typeGroups[a.ach_type] = typeGroups[a.ach_type] || []).push(a));
  const types = Object.keys(typeGroups).sort();
  let body;
  if (!list.length) body = '<div class="empty"><div class="e-ico">◆</div><div class="e-t">暂无成果，点击「＋ 手动录入」或用拖拽扫描导入</div></div>';
  else body = types.map(t => `<div class="card"><div class="card-head"><div class="card-title">${esc(t)} <span class="tag tag-gray">${typeGroups[t].length}</span></div></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>成果名称</th><th>作者</th><th>状态</th><th>等级</th><th>资助号</th><th>关联项目</th><th>附件</th><th></th></tr></thead>
    <tbody>${typeGroups[t].map(a => achRow(a)).join('')}</tbody></table></div></div>`).join('');
  main.innerHTML = `
    <div class="page-head"><div><div class="page-title">成果库</div><div class="page-sub">全局成果台账 · 一篇成果可支撑多个项目 · 文件路径只存相对索引</div></div>
      <div class="row"><button class="btn" data-act="open-scan">📥 拖拽扫描导入</button><button class="btn btn-primary" data-act="new-ach">＋ 手动录入</button></div></div>
    <div class="card" style="padding:12px 16px"><div class="row">
      <input id="achKw" placeholder="搜索成果名称 / 作者 / DOI / 专利号" value="${esc(kw)}" style="max-width:340px">
      <button class="btn btn-sm btn-primary" data-act="search-ach">搜索</button>
      ${kw ? '<button class="btn btn-sm" data-act="clear-ach-kw">清除</button>' : ''}
      <div class="spacer"></div><span class="muted">共 ${list.length} 条成果</span></div></div>
    ${body}`;
}
/* ============ 表单弹窗 ============ */
function modalProject(pid) {
  const p = pid ? VIEW.dash?.projects?.find(x => x.id == pid) : null;
  (async () => {
    const data = p || (pid ? await api('/api/projects/' + pid) : {});
    const opts = ['国自科','省自科','国家重点研发','横向','教改','其他'];
    openModal(pid ? '编辑项目' : '新建项目', `<div class="form-grid">
      <div class="fld full"><label>项目名称 <span class="req">*</span></label><input id="f_name" value="${esc(data.name)}"></div>
      <div class="fld"><label>立项编号</label><input id="f_code" value="${esc(data.code)}"></div>
      <div class="fld"><label>项目来源</label><select id="f_source">${opts.map(o => `<option ${data.source === o ? 'selected' : ''}>${o}</option>`).join('')}</select></div>
      <div class="fld"><label>负责人</label><input id="f_leader" value="${esc(data.leader)}"></div>
      <div class="fld"><label>经费总额（万元）</label><input id="f_budget" type="number" step="0.01" value="${data.budget || 0}"></div>
      <div class="fld"><label>开始时间</label><input id="f_start" type="date" value="${esc(data.start_date)}"></div>
      <div class="fld"><label>结束时间</label><input id="f_end" type="date" value="${esc(data.end_date)}"></div>
      <div class="fld full"><label>合作单位</label><input id="f_partners" value="${esc(data.partners)}" placeholder="多个单位用、分隔"></div>
      <div class="fld"><label>项目状态</label><select id="f_status">${['在研','结题','延期','终止'].map(s => `<option ${data.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="fld full"><label>备注</label><textarea id="f_note">${esc(data.note)}</textarea></div>
    </div>`, `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="saveProject">保存</button>`);
    $('#saveProject').onclick = async () => {
      if (!val('f_name')) return toast('项目名称必填', true);
      const payload = { name: val('f_name'), code: val('f_code'), source: val('f_source'), leader: val('f_leader'),
        budget: val('f_budget'), start_date: val('f_start'), end_date: val('f_end'), partners: val('f_partners'),
        status: val('f_status'), note: val('f_note') };
      try {
        if (pid) await api('/api/projects/' + pid, { method: 'PUT', body: payload });
        else { const r = await api('/api/projects', { method: 'POST', body: payload }); closeModal(); return navigate('#/project/' + r.id + '/info'); }
        closeModal(); toast('已保存'); route();
      } catch (e) { toast(e.message, true); }
    };
  })();
}
function modalDoc(pid) {
  const types = ['申报书','任务书','年度报告','经费预算','变更批复','任务调整单','其他'];
  openModal('上传任务文档', `<div class="hint-box">选择「原始任务基准」会作为结题对照的基准版本；变更批复/任务调整单请作为变更版本上传，并在「变更说明」里写清调整了什么指标。</div>
    <div class="form-grid">
      <div class="fld"><label>文档类型 <span class="req">*</span></label><select id="f_dtype">${types.map(t => `<option>${t}</option>`).join('')}</select></div>
      <div class="fld"><label>版本标签</label><input id="f_dver" placeholder="如 V1.0 / 2025调整版"></div>
      <div class="fld"><label>标题</label><input id="f_dtitle" placeholder="留空则用文档类型"></div>
      <div class="fld"><label>变更日期</label><input id="f_ddate" type="date"></div>
      <div class="fld full"><label>文件（PDF/DOC/XLS 等）</label><input id="f_dfile" type="file"></div>
      <div class="fld full"><label class="checkline"><input type="checkbox" id="f_dbase"><label for="f_dbase">标记为【原始任务基准版本】</label></label></div>
      <div class="fld full"><label>变更说明 / 摘要</label><textarea id="f_dsummary" placeholder="如：将论文指标由 5 篇调整为 4 篇，增加一个样机指标；结题时间延期至 2026-12"></textarea></div>
    </div>`, `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="saveDoc">上传</button>`);
  $('#saveDoc').onclick = async () => {
    const fd = new FormData();
    fd.append('doc_type', val('f_dtype')); fd.append('title', val('f_dtitle'));
    fd.append('version_tag', val('f_dver')); fd.append('change_date', val('f_ddate'));
    fd.append('summary', val('f_dsummary')); fd.append('is_baseline', checked('f_dbase') ? '1' : '0');
    const file = $('#f_dfile').files[0]; if (file) fd.append('file', file);
    try { await api(`/api/projects/${pid}/docs`, { method: 'POST', body: fd }); closeModal(); toast('文档已上传'); route(); }
    catch (e) { toast(e.message, true); }
  };
}
function modalContent(pid, cid) {
  const c = cid ? VIEW.contents.find(x => x.id == cid) : {};
  openModal(cid ? '编辑研究内容' : '新增研究内容', `<div class="form-grid">
    <div class="fld full"><label>研究内容名称 <span class="req">*</span></label><input id="f_ctitle" value="${esc(c.title)}" placeholder="如：研究内容 1　复杂环境可通行性建模"></div>
    <div class="fld"><label>排序号</label><input id="f_corder" type="number" value="${c.order_num || 0}"></div>
    <div class="fld full"><label>描述</label><textarea id="f_cdesc">${esc(c.description)}</textarea></div>
  </div>`, `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="saveContent">保存</button>`);
  $('#saveContent').onclick = async () => {
    if (!val('f_ctitle')) return toast('请填写名称', true);
    const payload = { title: val('f_ctitle'), order_num: val('f_corder'), description: val('f_cdesc') };
    try {
      await api(cid ? '/api/contents/' + cid : `/api/projects/${pid}/contents`, { method: cid ? 'PUT' : 'POST', body: payload });
      closeModal(); toast('已保存'); route();
    } catch (e) { toast(e.message, true); }
  };
}
function modalIndicator(pid, iid) {
  const i = iid ? VIEW.inds.find(x => x.id == iid) : {};
  const contents = VIEW.contents || [];
  openModal(iid ? '编辑考核指标' : '新增考核指标', `<div class="form-grid">
    <div class="fld full"><label>指标名称 <span class="req">*</span></label><input id="f_ititle" value="${esc(i.title)}" placeholder="如：发表 SCI 论文"></div>
    <div class="fld"><label>所属研究内容</label><select id="f_icontent"><option value="">（不归属）</option>${contents.map(c => `<option value="${c.id}" ${i.content_id == c.id ? 'selected' : ''}>${esc(c.title)}</option>`).join('')}</select></div>
    <div class="fld"><label>指标类型</label><select id="f_itype"><option value="quantitative" ${i.ind_type === 'quantitative' ? 'selected' : ''}>定量（可计数）</option><option value="qualitative" ${i.ind_type === 'qualitative' ? 'selected' : ''}>定性（完成/未完成）</option></select></div>
    <div class="fld"><label>目标值</label><input id="f_itarget" type="number" step="0.01" value="${i.target_value || 1}"></div>
    <div class="fld"><label>单位</label><input id="f_iunit" value="${esc(i.unit)}" placeholder="篇 / 项 / 套 / 份 / 名"></div>
    <div class="fld"><label>截止时间</label><input id="f_ideadline" type="date" value="${esc(i.deadline)}"></div>
    <div class="fld"><label>权重（%）</label><input id="f_iweight" type="number" step="0.01" value="${i.weight || 0}" placeholder="0 表示不参与加权"></div>
    <div class="fld"><label>排序号</label><input id="f_iorder" type="number" value="${i.order_num || 0}"></div>
    <div class="fld full"><label>说明</label><textarea id="f_idesc">${esc(i.description)}</textarea></div>
  </div>
  <div class="hint-box" style="margin-top:12px;margin-bottom:0">计数模式：完成度 = 关联成果数 / 目标值。权重模式：为各指标填权重后，项目整体完成度按加权平均计算。定性指标有关联成果或手动标记完成即为 100%。</div>`,
    `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="saveIndicator">保存</button>`);
  $('#saveIndicator').onclick = async () => {
    if (!val('f_ititle')) return toast('请填写指标名称', true);
    const payload = { title: val('f_ititle'), content_id: val('f_icontent') || null, ind_type: val('f_itype'),
      target_value: val('f_itarget'), unit: val('f_iunit'), deadline: val('f_ideadline'),
      weight: val('f_iweight'), order_num: val('f_iorder'), description: val('f_idesc') };
    try {
      await api(iid ? '/api/indicators/' + iid : `/api/projects/${pid}/indicators`, { method: iid ? 'PUT' : 'POST', body: payload });
      closeModal(); toast('已保存'); route();
    } catch (e) { toast(e.message, true); }
  };
}
async function modalAch(aid, presetPid, presetIid) {
  const a = aid ? await api('/api/achievements/' + aid) : {};
  const projects = VIEW.projects || await api('/api/projects');
  const linkedP = new Set((a.projects || []).map(x => x.project_id));
  if (presetPid) linkedP.add(presetPid);
  const linkedI = new Set((a.indicators || []).map(x => x.indicator_id));
  if (presetIid) linkedI.add(presetIid);
  // 拉全部指标与研究内容用于勾选
  const allInds = [], allContents = [];
  for (const p of projects) {
    const [list, clist] = await Promise.all([api(`/api/projects/${p.id}/indicators`), api(`/api/projects/${p.id}/contents`)]);
    list.forEach(x => allInds.push({ ...x, pname: p.name }));
    clist.forEach(c => allContents.push({ ...c, project_id: p.id }));
  }
  VIEW.contentsFor = allContents;
  const types = ['期刊论文','会议论文','发明专利','实用新型','软件著作权','竞赛奖项','样机','试验报告','标准','专著','研究生学位论文','咨询报告','科普文章','科普宣讲','国际会议参会','科普成果','其他'];
  const statuses = ['在投','受理','录用','授权','已交付'];
  const levels = ['TOP期刊','核心','普通'];
  const indHtml = allInds.length ? allInds.map(x => `<div class="checkline" style="padding:3px 0">
      <input type="checkbox" class="ach-ind" id="ind_${x.id}" value="${x.id}" ${linkedI.has(x.id) ? 'checked' : ''}>
      <label for="ind_${x.id}" style="flex:1">${esc(x.pname)} · ${esc(x.title)} <span class="muted">(${esc(x.ind_type === 'quantitative' ? '定量' : '定性')})</span></label>
      <select class="ind-content" data-ind="${x.id}" style="width:150px;font-size:11px;padding:3px 6px">
        <option value="">支撑的研究内容（可选）</option>
        ${(VIEW.contentsFor || []).filter(c => c.project_id == x.project_id).map(c => `<option value="${c.id}" ${x.content_id == c.id ? 'selected' : ''}>${esc(c.title)}</option>`).join('')}
      </select></div>`).join('') : '<div class="muted">暂无指标，请先到项目里创建</div>';
  openModal(aid ? '编辑成果' : '手动录入成果', `
    <div class="form-grid">
      <div class="fld full"><label>成果名称 <span class="req">*</span></label><input id="f_atitle" value="${esc(a.title)}"></div>
      <div class="fld"><label>成果类型</label><select id="f_atype">${types.map(t => `<option ${a.ach_type === t ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      <div class="fld"><label>状态</label><select id="f_astatus">${statuses.map(s => `<option ${a.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="fld"><label>级别</label><select id="f_alevel">${levels.map(s => `<option ${a.level === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="fld"><label>发表时间</label><input id="f_apub" value="${esc(a.pub_date)}" placeholder="2026-03 或 2026"></div>
      <div class="fld full"><label>作者</label><input id="f_aauthors" value="${esc(a.authors)}"></div>
      <div class="fld"><label>期刊/会议/出版社</label><input id="f_ajournal" value="${esc(a.journal)}"></div>
      <div class="fld"><label>DOI / 专利号 / 标准号</label><input id="f_aid" value="${esc(a.identifier)}"></div>
      <div class="fld"><label class="checkline"><input type="checkbox" id="f_afund" ${a.funding_ack ? 'checked' : ''}><label for="f_afund">已标注本项目资助号</label></label></div>
      <div class="fld"><label>标注的资助号</label><input id="f_afcode" value="${esc(a.funding_code)}" placeholder="如 622XXX00"></div>
      <div class="fld"><label class="checkline"><input type="checkbox" id="f_apublic" ${a.is_public !== 0 ? 'checked' : ''}><label for="f_apublic">对外公开</label></label></div>
      <div class="fld full"><label>备注</label><textarea id="f_anote">${esc(a.note)}</textarea></div>
    </div>
    <div class="divider"></div>
    <div style="font-weight:600;margin-bottom:8px">关联项目（可多选，一篇成果可支撑多个项目）</div>
    <div class="row" style="gap:12px">${projects.map(p => `<label class="checkline"><input type="checkbox" class="ach-proj" value="${p.id}" ${linkedP.has(p.id) ? 'checked' : ''}><label>${esc(p.name)}</label></label>`).join('')}</div>
    <div class="divider"></div>
    <div style="font-weight:600;margin-bottom:8px">支撑考核指标（可多选；勾选后可在「指标看板 → 查支撑成果」反查）</div>
    <div style="max-height:230px;overflow-y:auto;border:1px solid var(--line);border-radius:8px;padding:8px">${indHtml}</div>
    <div class="divider"></div>
    <div style="font-weight:600;margin-bottom:8px">附件文件 <span class="muted" style="font-weight:400">（保存成果后选择文件上传；文件存本地，仅记录相对路径索引）</span></div>
    ${a.file_path ? `<div class="row" style="margin-bottom:8px;padding:8px 10px;background:#f9fafb;border-radius:8px">
        <span>📎 ${esc(a.file_name || a.file_path)}</span>
        <a class="btn btn-sm" href="/api/files/${encodeURI(a.file_path)}" target="_blank">打开查看</a>
        ${a.file_path.toLowerCase().endsWith('.pdf') ? `<a class="btn btn-sm" href="/api/files/${encodeURI(a.file_path)}?inline=1" target="_blank">新窗口预览</a>` : ''}
        <button class="btn btn-sm" data-act="archive-ach" data-id="${a.id}">归档到根目录</button>
        <button class="btn btn-sm" id="recognizeAttach">🔍 自动识别填入</button>
        <button class="btn btn-sm btn-danger" id="removeAttach">移除索引</button></div>` : '<div class="muted" style="margin-bottom:8px">暂无附件</div>'}
    <input type="file" id="f_afile" style="max-width:100%">`,
    `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="saveAch">保存成果</button>`, true);
  const removeBtn = $('#removeAttach');
  if (removeBtn) removeBtn.onclick = async () => {
    try { await api('/api/achievements/' + aid + '/attachment', { method: 'DELETE' }); toast('附件索引已移除'); closeModal(); route(); }
    catch (e) { toast(e.message, true); }
  };
  const recBtn = $('#recognizeAttach');
  if (recBtn) recBtn.onclick = async () => {
    recBtn.disabled = true; recBtn.textContent = '识别中…';
    try {
      const r = await api('/api/achievements/' + aid + '/attachment/recognize', { method: 'POST' });
      const s = r.suggestion || {};
      const lines = [];
      if (s.title) { $('#f_atitle').value = s.title; lines.push('名称'); }
      if (s.authors) { $('#f_aauthors').value = s.authors; lines.push('作者'); }
      if (s.journal) { $('#f_ajournal').value = s.journal; lines.push('期刊/来源'); }
      if (s.pub_date) { $('#f_apub').value = s.pub_date; lines.push('年份'); }
      if (s.identifier) { $('#f_aid').value = s.identifier; lines.push('编号/DOI'); }
      if (s.ach_type) { $('#f_atype').value = s.ach_type; lines.push('类型'); }
      toast(lines.length ? `已填入：${lines.join('、')}（请核对后保存）` : '未识别到可填字段，请手动填写');
    } catch (e) { toast(e.message, true); }
    recBtn.disabled = false; recBtn.textContent = '🔍 自动识别填入';
  };
  $('#saveAch').onclick = async () => {
    if (!val('f_atitle')) return toast('请填写成果名称', true);
    const payload = { title: val('f_atitle'), ach_type: val('f_atype'), status: val('f_astatus'), level: val('f_alevel'),
      pub_date: val('f_apub'), authors: val('f_aauthors'), journal: val('f_ajournal'), identifier: val('f_aid'),
      funding_ack: checked('f_afund') ? 1 : 0, funding_code: val('f_afcode'),
      is_public: checked('f_apublic') ? 1 : 0, note: val('f_anote'),
      project_ids: $$('.ach-proj:checked').map(x => x.value),
      indicator_ids: $$('.ach-ind:checked').map(x => x.value),
      content_map: {} };
    $$('.ind-content').forEach(s => { if (s.value) payload.content_map[s.dataset.ind] = s.value; });
    try {
      let savedId = aid;
      if (!savedId) {
        const r = await api('/api/achievements', { method: 'POST', body: payload });
        savedId = r.id;
      } else {
        await api('/api/achievements/' + savedId, { method: 'PUT', body: payload });
      }
      // 附件上传：成果保存后再传文件（文件流），只在用户选择了新文件时执行
      const fileEl = $('#f_afile');
      if (fileEl && fileEl.files && fileEl.files[0]) {
        const fd = new FormData();
        fd.append('file', fileEl.files[0]);
        await api('/api/achievements/' + savedId + '/attachment', { method: 'POST', body: fd });
        toast('成果与附件均已保存');
      } else {
        toast('成果已保存');
      }
      closeModal(); route();
    } catch (e) { toast(e.message, true); }
  };
}
function modalDisbursed(pid) {
  openModal('录入实际拨付金额（万元）', `
    <div class="hint-box">直接填写本项目累计实际到账/拨付总额即可，<b>不需要按预算科目拆分</b>；与预算、支出、执行率完全独立，不影响原有数据。留空或 0 表示尚未拨付。</div>
    <div class="form-grid">
      <div class="fld full"><label>实际拨付金额（万元） <span class="req">*</span></label>
        <input id="f_disb_total" type="number" step="0.01" min="0" value="${VIEW.finance.total_disbursed || 0}"></div>
    </div>`,
    `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="saveDisbursed">保存</button>`);
  $('#saveDisbursed').onclick = async () => {
    try {
      await api(`/api/projects/${pid}/finance/disbursed`, { method: 'PUT', body: { amount: val('f_disb_total') } });
      closeModal(); toast('实际拨付金额已录入'); route();
    } catch (e) { toast(e.message, true); }
  };
}
function modalBudget(pid, bid) {
  const b = bid ? VIEW.finance.budget.find(x => x.id == bid) : {};
  openModal(bid ? '编辑预算科目' : '新增预算科目', `<div class="form-grid">
    <div class="fld"><label>预算科目 <span class="req">*</span></label><input id="f_bcat" value="${esc(b.category)}" placeholder="设备费 / 材料费 / 差旅费…"></div>
    <div class="fld"><label>预算金额（万元）</label><input id="f_bamt" type="number" step="0.01" value="${b.budget || 0}"></div>
    <div class="fld full"><label>备注</label><input id="f_bnote" value="${esc(b.note)}"></div></div>`,
    `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="saveBudget">保存</button>`);
  $('#saveBudget').onclick = async () => {
    if (!val('f_bcat')) return toast('科目必填', true);
    try {
      await api(bid ? '/api/budget/' + bid : `/api/projects/${pid}/budget`,
        { method: bid ? 'PUT' : 'POST', body: { category: val('f_bcat'), budget: val('f_bamt'), note: val('f_bnote') } });
      closeModal(); toast('已保存'); route();
    } catch (e) { toast(e.message, true); }
  };
}
function modalImportExcel(pid) {
  openModal('上传 Excel 经费表', `
    <div class="hint-box">上传 .xlsx 经费表，系统自动识别科目、预算、支出并生成横向柱状图；支出无需逐笔手工录入。表头可包含：<b>科目/类别</b>、<b>预算</b>、<b>支出/已用/执行</b>、日期、说明、凭证；无表头时按列顺序识别（科目、预算、支出、日期、说明、凭证）。只有支出列时按科目名匹配已有预算科目。<b>实际拨付金额不从 Excel 导入</b>，请在看板卡片单独录入。导入后元信息经费总额自动同步为科目合计。</div>
    <div class="form-grid">
      <div class="fld full"><label>选择 Excel 文件（.xlsx） <span class="req">*</span></label><input id="f_excel" type="file" accept=".xlsx,.xlsm"></div>
    </div>
    <div class="muted" style="margin-top:10px">示例表头：科目 | 预算 | 支出 | 日期 | 说明；或纯支出表：科目 | 支出 | 日期 | 说明</div>`,
    `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="doImportExcel">导入</button>`);
  $('#doImportExcel').onclick = async () => {
    const el = $('#f_excel');
    if (!el.files || !el.files[0]) return toast('请选择 Excel 文件', true);
    const fd = new FormData();
    fd.append('file', el.files[0]);
    try {
      const r = await api(`/api/projects/${pid}/finance/import-excel`, { method: 'POST', body: fd });
      closeModal(); toast(r && r.added_expense !== undefined ? `已导入 ${r.added_budget} 个科目、${r.added_expense} 条支出` : '导入完成'); route();
    } catch (e) { toast(e.message, true); }
  };
}
function modalLinkAch(iid) {
  const i = VIEW.inds.find(x => x.id == iid);
  (async () => {
    const st = await api('/api/indicators/' + iid + '/achievements');
    const rows = st.achievements.map(a => `<tr><td>${esc(a.title)}</td><td>${esc(a.ach_type)}</td>
      <td><span class="tag tag-${tagColor(a.status)}">${esc(a.status)}</span></td><td>${a.funding_ack ? '是' : '否'}</td>
      <td>${a.file_path ? `<a class="link" href="/api/files/${encodeURI(a.file_path)}" target="_blank">打开</a>` : '—'}</td>
      <td><button class="btn btn-sm btn-ghost" data-act="edit-ach" data-id="${a.id}">编辑</button></td></tr>`).join('');
    openModal(`「${esc(i.title)}」的支撑成果`, `<div class="hint-box" style="margin-bottom:12px">目标 ${i.target_value}${esc(i.unit || '')} · 已归集 ${st.completed} · 完成度 ${st.progress}%${
      i.warning !== 'ok' ? ` · ${esc(i.warning_reason)}` : ''}</div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>成果名称</th><th>类型</th><th>状态</th><th>标注资助号</th><th>附件</th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6" class="empty">尚无支撑成果</td></tr>'}</tbody></table></div>`,
      `<button class="btn" data-act="close-modal">关闭</button><button class="btn btn-primary" id="linkNewAch">＋ 录入并关联此指标</button>`, true);
    $('#linkNewAch').onclick = () => { closeModal(); modalAch(null, VIEW.pid, Number(iid)); };
  })();
}
/* ---- 扫描导入 ---- */
async function modalScan() {
  const cfg = await api('/api/config');
  VIEW.scanItems = [];
  openModal('拖拽文件夹扫描导入', `
    <div class="hint-box">扫描后自动解析 PDF 元数据与首页，预填成果表单。<b>所有识别结果都需要人工核对确认后才会入库</b>，系统不会自动判定成果完成指标。原始文件保留在原文件夹，系统只存相对路径索引。</div>
    <div class="dropzone" id="dz"><div class="dz-ico">📂</div><div class="dz-t">拖入成果文件夹，或点击选择</div>
      <div class="dz-s">支持 PDF / DOC / DOCX / 图片 · 支持递归子目录</div></div>
    <input type="file" id="folderInput" webkitdirectory directory multiple style="display:none">
    <div class="row" style="margin-top:12px"><input id="f_folder" placeholder="或手动输入文件夹绝对路径" style="flex:1">
      <label class="checkline"><input type="checkbox" id="f_recursive" checked><label>递归子目录</label></label>
      <button class="btn btn-primary" id="doScan">扫描</button></div>
    <div class="muted" style="margin-top:8px">文件根目录：<span class="mono">${esc(cfg.files_root)}</span><br>扫描到根目录外的文件时，可在入库后点「归档到根目录」复制进索引根目录。</div>
    <div id="scanResult" style="margin-top:16px"></div>`,
    `<button class="btn" data-act="close-modal">取消</button><button class="btn btn-primary" id="commitScan" style="display:none">确认入库选中成果</button>`, true);
  const dz = $('#dz'), fi = $('#folderInput');
  dz.onclick = () => fi.click();
  dz.ondragover = e => { e.preventDefault(); dz.style.borderColor = '#2563eb'; };
  dz.ondragleave = () => dz.style.borderColor = '';
  dz.ondrop = e => { e.preventDefault(); dz.style.borderColor = ''; pickFiles(e.dataTransfer.files); };
  fi.onchange = () => pickFiles(fi.files);
  function pickFiles(files) {
    if (!files || !files.length) return;
    const p = files[0].webkitRelativePath || files[0].name;
    const folder = p.includes('/') ? p.split('/')[0] : '';
    if (folder) { $('#f_folder').value = folder; toast('已填入文件夹名，如扫描失败请改用绝对路径'); }
    else toast('浏览器未返回文件夹路径，请在输入框填写绝对路径', true);
  }
  $('#doScan').onclick = async () => {
    const folder = val('f_folder');
    if (!folder) return toast('请选择或输入文件夹路径', true);
    try {
      const r = await api('/api/scan', { method: 'POST', body: { folder, recursive: checked('f_recursive') } });
      VIEW.scanItems = r.items.map(x => ({ ...x, _pick: true }));
      renderScanResult();
    } catch (e) { toast(e.message, true); $('#scanResult').innerHTML = `<div class="warn-item danger">${esc(e.message)}</div>`; }
  };
  $('#commitScan').onclick = async () => {
    const items = VIEW.scanItems.filter(x => x._pick);
    if (!items.length) return toast('请至少选择一条成果', true);
    try {
      const r = await api('/api/scan/commit', { method: 'POST', body: { items } });
      closeModal(); toast(`已入库 ${r.ids.length} 条成果（待人工核对字段）`); route();
    } catch (e) { toast(e.message, true); }
  };
}
function renderScanResult() {
  const items = VIEW.scanItems;
  const box = $('#scanResult');
  $('#commitScan').style.display = items.length ? '' : 'none';
  const types = ['期刊论文','会议论文','发明专利','实用新型','软件著作权','竞赛奖项','样机','试验报告','标准','专著','研究生学位论文','咨询报告','科普文章','科普宣讲','国际会议参会','科普成果','其他'];
  box.innerHTML = `<div class="row" style="margin-bottom:10px"><b>识别到 ${items.length} 个文件</b>
    <button class="btn btn-sm" id="pickAll">全选</button><button class="btn btn-sm" id="pickNone">全不选</button>
    <span class="muted">紫色标记为自动识别来源，请重点核对</span></div>` +
    items.map((x, idx) => `<div class="scan-item">
      <div class="scan-file"><span>📄 ${esc(x.file_name)} ${x.duplicate ? '<span class="tag tag-amber">可能重复</span>' : ''} ${!x.in_root ? '<span class="tag tag-outline">根目录外</span>' : ''}</span>
        <label class="checkline"><input type="checkbox" class="scan-pick" data-i="${idx}" ${x._pick ? 'checked' : ''}><label>入库</label></label></div>
      ${x.error ? `<div class="warn-item danger">${esc(x.error)}</div>` : ''}
      <div class="scan-grid">
        <div class="fld"><label>成果名称 <span class="confidence-hint">${esc(x.confidence?.title || '')}</span></label><input class="sf" data-i="${idx}" data-k="title" value="${esc(x.title)}"></div>
        <div class="fld"><label>类型</label><select class="sf" data-i="${idx}" data-k="ach_type">${types.map(t => `<option ${x.ach_type === t ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
        <div class="fld"><label>作者 <span class="confidence-hint">${esc(x.confidence?.authors || '')}</span></label><input class="sf" data-i="${idx}" data-k="authors" value="${esc(x.authors)}"></div>
        <div class="fld"><label>期刊/来源 <span class="confidence-hint">${esc(x.confidence?.journal || '')}</span></label><input class="sf" data-i="${idx}" data-k="journal" value="${esc(x.journal)}"></div>
        <div class="fld"><label>发表年份</label><input class="sf" data-i="${idx}" data-k="pub_date" value="${esc(x.pub_date)}"></div>
        <div class="fld"><label>DOI/专利号 <span class="confidence-hint">${esc(x.confidence?.identifier || '')}</span></label><input class="sf" data-i="${idx}" data-k="identifier" value="${esc(x.identifier)}"></div>
      </div>
      ${x.text_preview ? `<div class="muted" style="margin-top:7px">首页文本预览：${esc(x.text_preview.slice(0, 160))}…</div>` : ''}
      <div class="row" style="margin-top:8px">
        <label class="checkline"><input type="checkbox" class="sf" data-i="${idx}" data-k="funding_ack" ${x.funding_ack ? 'checked' : ''} data-check="1"><label>已标注资助号</label></label>
        <label class="checkline"><input type="checkbox" class="sf" data-i="${idx}" data-k="is_public" ${x.is_public !== 0 ? 'checked' : ''} data-check="1"><label>对外公开</label></label>
      </div></div>`).join('');
  $$('.sf', box).forEach(el => el.onchange = () => {
    const i = +el.dataset.i, k = el.dataset.k;
    VIEW.scanItems[i][k] = el.dataset.check ? (el.checked ? 1 : 0) : el.value;
  });
  $$('.scan-pick', box).forEach(el => el.onchange = () => VIEW.scanItems[+el.dataset.i]._pick = el.checked);
  $('#pickAll').onclick = () => { VIEW.scanItems.forEach(x => x._pick = true); renderScanResult(); };
  $('#pickNone').onclick = () => { VIEW.scanItems.forEach(x => x._pick = false); renderScanResult(); };
}

/* ============ 全局事件委托 ============ */
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-act]');
  if (!t) return;
  const act = t.dataset.act, id = t.dataset.id;
  if (act === 'close-modal') return closeModal();
  if (act === 'new-project') return modalProject();
  if (act === 'edit-project') return modalProject(Number(id));
  if (act === 'goto-project') return navigate('#/project/' + id + '/info');
  if (act === 'goto-ach') return navigate('#/achievements');
  if (act === 'ptab') return navigate('#/project/' + VIEW.pid + '/' + t.dataset.tab);
  if (act === 'new-doc') return modalDoc(Number(id));
  if (act === 'del-doc') return confirmBox('确定删除该文档记录？', async () => { await api('/api/docs/' + id, { method: 'DELETE' }); toast('已删除'); route(); });
  if (act === 'diff-docs') {
    const docs = VIEW.docs || [];
    const base = docs.find(d => d.is_baseline);
    const changes = docs.filter(d => !d.is_baseline);
    $('#diffBox').innerHTML = `<div class="divider"></div><div class="muted" style="margin-bottom:8px">版本对比说明（结题时以最新批复为准）：</div>
      <div class="kv-list" style="grid-template-columns:110px 1fr"><div class="k">原始基准</div><div>${base ? esc(base.version_tag || base.title || base.doc_type) + ' · ' + esc(base.uploaded_at) : '未设置'}</div>
      ${changes.map(c => `<div class="k">变更版本</div><div>${esc(c.version_tag || c.doc_type)} · ${esc(c.change_date || c.uploaded_at)}<div class="muted">${esc(c.summary || '未填写变更说明')}</div></div>`).join('')}</div>`;
    return;
  }
  if (act === 'new-content') return modalContent(Number(id));
  if (act === 'edit-content') return modalContent(VIEW.pid, Number(id));
  if (act === 'del-content') return confirmBox('删除研究内容？其下指标将变为「未归属」，不会删除指标。', async () => { await api('/api/contents/' + id, { method: 'DELETE' }); toast('已删除'); route(); });
  if (act === 'new-indicator') return modalIndicator(Number(id));
  if (act === 'edit-indicator') return modalIndicator(VIEW.pid, Number(id));
  if (act === 'del-indicator') return confirmBox('删除该考核指标？关联成果不会被删除。', async () => { await api('/api/indicators/' + id, { method: 'DELETE' }); toast('已删除'); route(); });
  if (act === 'toggle-done') { await api('/api/indicators/' + id, { method: 'PUT', body: { manual_done: t.dataset.done === '1' ? 0 : 1 } }); toast('已更新'); route(); return; }
  if (act === 'link-ach') return modalLinkAch(Number(id));
  if (act === 'new-ach') return modalAch(null, Number(t.dataset.pid || VIEW.pid || 0));
  if (act === 'edit-ach') return modalAch(Number(id));
  if (act === 'archive-ach') { await api('/api/achievements/' + id + '/archive', { method: 'POST' }); toast('已归档'); route(); return; }
  if (act === 'sync-budget') {
    try { await api('/api/projects/' + id + '/finance/sync-from-meta', { method: 'POST' }); toast('已按元信息经费同步预算科目'); }
    catch (e) { toast(e.message, true); }
    return route();
  }
  if (act === 'import-excel') return modalImportExcel(Number(id));
  if (act === 'edit-disbursed') return modalDisbursed(Number(id));
  if (act === 'new-budget') return modalBudget(Number(id));
  if (act === 'edit-budget') return modalBudget(VIEW.pid, Number(id));
  if (act === 'del-budget') return confirmBox('删除该预算科目？', async () => { await api('/api/budget/' + id, { method: 'DELETE' }); toast('已删除'); route(); });
  if (act === 'del-expense') return confirmBox('删除该条导入的支出记录？', async () => { await api('/api/expenses/' + id, { method: 'DELETE' }); toast('已删除'); route(); });
  if (act === 'open-scan') return modalScan();
  if (act === 'search-ach') { VIEW.achKw = val('achKw'); return renderAchievements(); }
  if (act === 'clear-ach-kw') { VIEW.achKw = ''; return renderAchievements(); }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
window.addEventListener('DOMContentLoaded', async () => {
  try { const c = await api('/api/config'); $('#cfgLine').textContent = c.files_root; } catch {}
  route();
});

