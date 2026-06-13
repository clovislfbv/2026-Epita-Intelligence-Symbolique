const API = '';
let appState = 'upload';
let lastSubgraphNodes = new Set();
let lastSubgraphEdges = new Set();
let simulation = null;
let graphData = null;

/**
 * Updates the app state and refreshes all dependent UI elements.
 * @param {string} s - New state: 'upload', 'building', or 'ready'.
 */
function setAppState(s) {
  appState = s;
  const steps = document.querySelectorAll('.nav-step');
  const stateMap = { upload: 0, building: 1, ready: 2 };
  steps.forEach((el, i) => {
    el.className = 'nav-step ' + (i < stateMap[s] ? 'done' : i === stateMap[s] ? 'active' : 'pending');
  });
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const badge = document.getElementById('input-badge');
  const buildBtn = document.getElementById('build-btn');
  const exportBtn = document.getElementById('export-btn');
  if (s === 'ready') {
    input.disabled = false; sendBtn.disabled = false;
    badge.classList.remove('visible'); buildBtn.textContent = '✓ Knowledge Graph construit';
    buildBtn.disabled = true; exportBtn.disabled = false;
    document.getElementById('progress-box').style.display = 'none';
    loadGraph();
  } else if (s === 'building') {
    input.disabled = true; sendBtn.disabled = true;
    badge.textContent = '⚙ Construction du KG en cours…'; badge.classList.add('visible');
    buildBtn.disabled = true; exportBtn.disabled = true;
  } else {
    input.disabled = true; sendBtn.disabled = true;
    badge.textContent = '⏳ Uploadez vos documents d\'abord'; badge.classList.add('visible');
    buildBtn.disabled = false; exportBtn.disabled = true;
  }
}

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.style.borderColor = '#6366f1'; });
dropZone.addEventListener('dragleave', () => { dropZone.style.borderColor = ''; });
dropZone.addEventListener('drop', e => { e.preventDefault(); dropZone.style.borderColor = ''; handleFiles(e.dataTransfer.files); });
fileInput.addEventListener('change', () => handleFiles(fileInput.files));

/**
 * Uploads selected files to the backend and adds them to the doc list.
 * @param {FileList} files - The files selected by the user.
 */
async function handleFiles(files) {
  const fd = new FormData();
  for (const f of files) fd.append('files', f);
  const r = await fetch(`${API}/upload`, { method: 'POST', body: fd });
  const { saved } = await r.json();
  saved.forEach(addDocItem);
  document.getElementById('build-btn').disabled = false;
}

/**
 * Adds a document entry row to the sidebar doc list.
 * @param {string} name - The filename to display.
 */
function addDocItem(name) {
  const list = document.getElementById('docs-list');
  const el = document.createElement('div');
  el.className = 'doc-item';
  el.innerHTML = `<span style="font-size:16px">📄</span><div style="flex:1"><div class="doc-name">${name}</div></div><span class="doc-status-ok">✓</span>`;
  list.appendChild(el);
}

document.querySelectorAll('.ds-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    document.querySelectorAll('.ds-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const ds = btn.dataset.ds;
    await fetch(`${API}/dataset/select`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset: ds }) });
    document.getElementById('reset-btn').classList.toggle('visible', ds === 'custom');
    const { datasets } = await (await fetch(`${API}/datasets`)).json();
    document.getElementById('docs-list').innerHTML = '';
    datasets[ds].files.forEach(addDocItem);
    if (datasets[ds].files.length > 0) document.getElementById('build-btn').disabled = false;
    setAppState('upload');
  });
});

document.getElementById('reset-btn').addEventListener('click', async () => {
  await fetch(`${API}/reset`, { method: 'POST' });
  document.getElementById('docs-list').innerHTML = '';
  document.getElementById('build-btn').disabled = true;
  setAppState('upload');
});

const STAGES = ['extraction', 'graph_build', 'community_detection', 'indexing'];
document.getElementById('build-btn').addEventListener('click', async () => {
  setAppState('building');
  document.getElementById('progress-box').style.display = 'block';
  const fill = document.getElementById('progress-fill');
  const pct = document.getElementById('progress-pct');
  const label = document.getElementById('progress-label-text');

  const es = new EventSource(`${API}/build`);
  es.onmessage = e => {
    const { stage, progress, message } = JSON.parse(e.data);
    fill.style.width = `${progress}%`;
    pct.textContent = `${progress}%`;
    label.textContent = message;
    STAGES.forEach(s => {
      const el = document.getElementById(`prog-${s}`);
      if (!el) return;
      const stageIdx = STAGES.indexOf(stage);
      const elIdx = STAGES.indexOf(s);
      el.className = 'prog-step ' + (elIdx < stageIdx ? 'done' : elIdx === stageIdx ? 'active-s' : '');
    });
    if (stage === 'done') { es.close(); setAppState('ready'); }
    if (stage === 'error') { es.close(); alert('Erreur: ' + message); setAppState('upload'); }
  };
});

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

document.getElementById('send-btn').addEventListener('click', sendMessage);
document.getElementById('chat-input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });

/**
 * Reads the chat input, sends a query to the backend, and renders the response.
 */
async function sendMessage() {
  const input = document.getElementById('chat-input');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  appendMessage('user', q);
  const typingId = appendMessage('bot', '…');
  try {
    const r = await fetch(`${API}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    });
    const data = await r.json();
    updateMessage(typingId, data);
    highlightSubgraph(data.subgraph_nodes, data.subgraph_edges);
  } catch (err) {
    updateMessage(typingId, null, 'Erreur lors de la requête.');
  }
}

let msgId = 0;

/**
 * Appends a chat message bubble to the chat area.
 * @param {string} type - 'user' or 'bot'.
 * @param {string} text - Initial text content.
 * @returns {string} The unique DOM id of the created message element.
 */
function appendMessage(type, text) {
  const area = document.getElementById('chat-area');
  const id = `msg-${++msgId}`;
  const div = document.createElement('div');
  div.id = id;
  div.className = `msg msg-${type === 'user' ? 'user' : 'bot'}`;
  if (type === 'bot') div.innerHTML = `<div class="msg-bot-hdr">✦ GraphRAG</div><span class="msg-text">${text}</span>`;
  else div.textContent = text;
  area.appendChild(div);
  area.scrollTop = area.scrollHeight;
  return id;
}

/**
 * Updates a bot message bubble with the full query response, adding a chip and drawer.
 * @param {string} id - The DOM id of the message element to update.
 * @param {Object|null} data - The query response object, or null on error.
 * @param {string} [errorText] - Error message to display if data is null.
 */
function updateMessage(id, data, errorText) {
  const el = document.getElementById(id);
  if (!el) return;
  if (errorText) { el.querySelector('.msg-text').textContent = errorText; return; }
  el.querySelector('.msg-text').textContent = data.answer;
  const hopCount = data.trace.length;
  const nodeCount = data.subgraph_nodes.length;
  const docCount = data.docs_used.length;
  const chipId = `chip-${id}`;
  const drawerId = `drawer-${id}`;
  const chip = document.createElement('div');
  chip.innerHTML = `
    <span class="chip" id="${chipId}" onclick="toggleDrawer('${chipId}','${drawerId}')">
      ⚡ ${hopCount}-hop · ${nodeCount} entités · ${docCount} docs — voir le détail ↓
    </span>
    <div class="drawer" id="${drawerId}">
      <div class="drawer-inner">
        <div class="drawer-label">🔍 Étapes de raisonnement</div>
        ${data.trace.map(s => `
          <div class="step-row">
            <div class="step-dot-n">${s.hop}</div>
            <div>
              <div class="step-title">Hop ${s.hop} — ${s.relation}</div>
              <div class="step-desc">Depuis : ${s.from_node}</div>
              <div class="etags">${s.to_nodes.map(n => `<span class="etag">${n}</span>`).join('')}</div>
            </div>
          </div>`).join('')}
        <div class="drawer-label" style="margin-top:10px">📄 Documents sources</div>
        <div class="docs-used-list">
          ${data.docs_used.length ? data.docs_used.map(d => `<div class="doc-used-item">📄 <strong>${d.filename}</strong></div>`).join('') : '<div style="font-size:11px;color:#94a3b8">Aucun document tracé</div>'}
        </div>
      </div>
    </div>`;
  el.appendChild(chip);
}

/**
 * Toggles the open/closed state of a trace detail drawer.
 * @param {string} chipId - DOM id of the chip toggle button.
 * @param {string} drawerId - DOM id of the drawer panel.
 */
function toggleDrawer(chipId, drawerId) {
  const chip = document.getElementById(chipId);
  const drawer = document.getElementById(drawerId);
  const isOpen = drawer.classList.contains('open');
  drawer.classList.toggle('open');
  chip.classList.toggle('open');
  const base = chip.textContent.replace(/[↑↓]/g, '').trim();
  chip.textContent = base + (isOpen ? ' ↓' : ' ↑');
}

/**
 * Fetches graph data from the backend and renders the D3 visualization.
 */
async function loadGraph() {
  try {
    const data = await (await fetch(`${API}/graph`)).json();
    graphData = data;
    renderGraph(data);
    renderCommunityFilters(data.communities);
    document.getElementById('stat-nodes').textContent = data.stats.node_count;
    document.getElementById('stat-edges').textContent = data.stats.edge_count;
    document.getElementById('stat-comms').textContent = data.stats.community_count;
  } catch (_) {}
}

/**
 * Renders a D3.js force-directed graph into the #graph-svg element.
 * @param {Object} data - Graph data with nodes, edges arrays and stats.
 */
function renderGraph(data) {
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();
  const W = document.getElementById('graph-svg').clientWidth;
  const H = document.getElementById('graph-svg').clientHeight;
  const g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', e => g.attr('transform', e.transform)));

  svg.append('defs').append('marker')
    .attr('id', 'arr').attr('markerWidth', 6).attr('markerHeight', 6).attr('refX', 14).attr('refY', 3).attr('orient', 'auto')
    .append('path').attr('d', 'M0,0 L0,6 L6,3 z').attr('fill', '#c7d2fe');

  const link = g.append('g').selectAll('line').data(data.edges).enter().append('line')
    .attr('stroke', '#ddd6fe').attr('stroke-width', 1.5).attr('marker-end', 'url(#arr)')
    .attr('class', d => `edge-${d.source}-${d.target}`);

  const node = g.append('g').selectAll('g').data(data.nodes).enter().append('g')
    .attr('class', 'node').call(d3.drag().on('start', dragstart).on('drag', dragged).on('end', dragend));

  node.append('circle').attr('r', d => 8 + Math.min(d.degree * 2, 14))
    .attr('fill', '#fff').attr('stroke', d => d.color).attr('stroke-width', 2.5)
    .style('filter', d => `drop-shadow(0 1px 6px ${d.color}55)`);

  node.append('text').text(d => d.id).attr('text-anchor', 'middle').attr('dy', 4)
    .attr('font-size', 9).attr('fill', d => d.color).attr('font-weight', '600')
    .style('pointer-events', 'none');

  const tooltip = document.getElementById('graph-tooltip');
  node.on('mouseover', (event, d) => {
    const rels = data.edges.filter(e => e.source === d.id || e.target === d.id)
      .map(e => `<div class="tt-rel">${e.source} →[${e.relation}]→ ${e.target}</div>`).join('');
    tooltip.innerHTML = `<div class="tt-name">${d.id}</div><div class="tt-type">Communauté ${d.community + 1}</div>${rels}`;
    tooltip.style.display = 'block';
    tooltip.style.left = (event.pageX + 12) + 'px';
    tooltip.style.top = (event.pageY - 20) + 'px';
  }).on('mousemove', event => {
    tooltip.style.left = (event.pageX + 12) + 'px';
    tooltip.style.top = (event.pageY - 20) + 'px';
  }).on('mouseout', () => { tooltip.style.display = 'none'; });

  simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
}

/**
 * Highlights nodes and edges in the graph that were part of the last query's subgraph.
 * Highlighted elements are shown in amber; others revert to their community color.
 * @param {string[]} nodes - Node ids to highlight.
 * @param {Array} edges - Edge tuples [source, relation, target] to highlight.
 */
function highlightSubgraph(nodes, edges) {
  if (!graphData) return;
  const nodeSet = new Set(nodes);
  const edgeSet = new Set(edges.map(e => `${e[0]}-${e[2]}`));
  d3.selectAll('.node circle').attr('stroke', d => nodeSet.has(d.id) ? '#f59e0b' : d.color)
    .attr('stroke-width', d => nodeSet.has(d.id) ? 3 : 2.5);
  d3.selectAll('line').attr('stroke', d => edgeSet.has(`${d.source.id || d.source}-${d.target.id || d.target}`) ? '#f59e0b' : '#ddd6fe')
    .attr('stroke-width', d => edgeSet.has(`${d.source.id || d.source}-${d.target.id || d.target}`) ? 2.5 : 1.5);
}

/**
 * Renders community filter badge buttons in the graph toolbar.
 * @param {Object[]} communities - Array of community objects with id and label.
 */
function renderCommunityFilters(communities) {
  const COLORS = ['#6366f1','#8b5cf6','#f59e0b','#10b981','#ef4444','#3b82f6'];
  const container = document.getElementById('comm-filters');
  container.innerHTML = '';
  communities.forEach((c, i) => {
    const btn = document.createElement('span');
    btn.className = 'comm-badge';
    btn.style.background = COLORS[i % COLORS.length] + '22';
    btn.style.color = COLORS[i % COLORS.length];
    btn.style.borderColor = COLORS[i % COLORS.length] + '44';
    btn.textContent = `● ${c.label}`;
    container.appendChild(btn);
  });
}

/**
 * D3 drag start handler — fixes node position to enable dragging.
 * @param {Object} event - D3 drag event.
 * @param {Object} d - Node datum.
 */
function dragstart(event, d) { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }

/**
 * D3 drag handler — updates fixed position while dragging.
 * @param {Object} event - D3 drag event.
 * @param {Object} d - Node datum.
 */
function dragged(event, d) { d.fx = event.x; d.fy = event.y; }

/**
 * D3 drag end handler — releases fixed position so simulation resumes.
 * @param {Object} event - D3 drag event.
 * @param {Object} d - Node datum.
 */
function dragend(event, d) { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }

/**
 * Restores the document list from the server on page load.
 * Fetches /datasets and populates the sidebar with existing files.
 */
async function initDocList() {
  const { active, datasets } = await (await fetch(`${API}/datasets`)).json();
  const files = datasets[active].files;
  files.forEach(addDocItem);
  if (files.length > 0) document.getElementById('build-btn').disabled = false;
}

/**
 * Downloads the current KG as a .graphrag ZIP snapshot via GET /export.
 * Triggers a browser download without navigating away from the page.
 */
async function exportKG() {
  const res = await fetch(`${API}/export`);
  if (!res.ok) { alert('Export impossible : le graphe n\'est pas encore construit.'); return; }
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'demo.graphrag';
  a.click();
  URL.revokeObjectURL(a.href);
}

/**
 * Handles a .graphrag file selection and imports it via POST /import.
 * Rebuilds the KG on the backend (no LLM calls) and transitions to 'ready'.
 */
async function importKG() {
  const input = document.getElementById('import-input');
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  input.value = '';
  const res = await fetch(`${API}/import`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert('Import échoué : ' + (err.detail || 'fichier .graphrag invalide.'));
    return;
  }
  const { docs } = await res.json();
  document.getElementById('docs-list').innerHTML = '';
  docs.forEach(addDocItem);
  setAppState('ready');
}

document.getElementById('export-btn').addEventListener('click', exportKG);
document.getElementById('import-input').addEventListener('change', importKG);

setAppState('upload');
initDocList();
