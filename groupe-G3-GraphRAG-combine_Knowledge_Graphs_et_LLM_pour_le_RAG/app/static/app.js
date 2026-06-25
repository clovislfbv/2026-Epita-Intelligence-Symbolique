const API = '';
let appState = 'upload';
let lastSubgraphNodes = [];
let lastSubgraphEdges = [];
let simulation = null;
let graphData = null;
/** @type {Array<{role: string, content: string}>} */
let chatHistory = [];

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
  const newChatBtn = document.getElementById('new-chat-btn');
  if (s === 'ready') {
    input.disabled = false; sendBtn.disabled = false;
    badge.classList.remove('visible'); buildBtn.textContent = '✓ Knowledge Graph built';
    buildBtn.disabled = true; exportBtn.disabled = false; newChatBtn.disabled = false;
    document.getElementById('progress-box').style.display = 'none';
    loadGraphOverview();
  } else if (s === 'building') {
    input.disabled = true; sendBtn.disabled = true;
    badge.textContent = '⚙ Building KG…'; badge.classList.add('visible');
    buildBtn.disabled = true; exportBtn.disabled = true; newChatBtn.disabled = true;
  } else {
    input.disabled = true; sendBtn.disabled = true;
    badge.textContent = '⏳ Upload your documents first'; badge.classList.add('visible');
    buildBtn.disabled = false; exportBtn.disabled = true; newChatBtn.disabled = true;
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
    chatHistory = [];
    setAppState('upload');
  });
});

document.getElementById('reset-btn').addEventListener('click', async () => {
  await fetch(`${API}/reset`, { method: 'POST' });
  document.getElementById('docs-list').innerHTML = '';
  document.getElementById('build-btn').disabled = true;
  chatHistory = [];
  setAppState('upload');
});

document.getElementById('graph-back-btn').addEventListener('click', () => {
  document.getElementById('load-more-btn').style.display = 'none';
  loadGraphOverview();
});

document.getElementById('load-more-btn').addEventListener('click', async () => {
  const truncated = await loadMoreCommunity();
  document.getElementById('load-more-btn').style.display = truncated ? 'inline-block' : 'none';
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
    if (stage === 'error') { es.close(); alert('Error: ' + message); setAppState('upload'); }
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
 * Reads the chat input, sends a query (with conversation history) to the
 * backend, renders the response, and appends both turns to chatHistory.
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
      body: JSON.stringify({ question: q, history: chatHistory })
    });
    const data = await r.json();
    updateMessage(typingId, data);
    lastSubgraphNodes = data.subgraph_nodes;
    lastSubgraphEdges = data.subgraph_edges;
    showFocusSubgraph(lastSubgraphNodes, lastSubgraphEdges);
    chatHistory.push({ role: 'user', content: q });
    chatHistory.push({ role: 'assistant', content: data.answer });
  } catch (err) {
    updateMessage(typingId, null, 'Request failed.');
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
  if (type === 'bot') div.innerHTML = `<div class="msg-bot-hdr">✦ GraphRAG</div><div class="msg-text msg-md">${text}</div>`;
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
  el.querySelector('.msg-text').innerHTML = marked.parse(data.answer);
  const hopCount = data.trace.length;
  const nodeCount = data.subgraph_nodes.length;
  const docCount = data.docs_used.length;
  const chipId = `chip-${id}`;
  const drawerId = `drawer-${id}`;
  const chip = document.createElement('div');
  chip.innerHTML = `
    <span class="chip" id="${chipId}" onclick="toggleDrawer('${chipId}','${drawerId}')">
      ⚡ ${hopCount}-hop · ${nodeCount} entities · ${docCount} docs — see details ↓
    </span>
    <div class="drawer" id="${drawerId}">
      <div class="drawer-inner">
        <div class="drawer-label">🔍 Reasoning steps</div>
        ${data.trace.map(s => `
          <div class="step-row">
            <div class="step-dot-n">${s.hop}</div>
            <div>
              <div class="step-title">Hop ${s.hop} — ${s.relation}</div>
              <div class="step-desc">From: ${s.from_node}</div>
              <div class="etags">${s.to_nodes.map(n => `<span class="etag">${n}</span>`).join('')}</div>
            </div>
          </div>`).join('')}
        <div class="drawer-label" style="margin-top:10px">📄 Source documents</div>
        <div class="docs-used-list">
          ${data.docs_used.length ? data.docs_used.map(d => `<div class="doc-used-item">📄 <strong>${d.filename}</strong></div>`).join('') : '<div style="font-size:11px;color:#94a3b8">No documents traced</div>'}
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

let viewMode = 'overview';
let overviewData = null;
let currentCommunityId = null;
let currentLimit = 150;

/**
 * Fetches the community-level overview and renders it as clickable bubbles.
 */
async function loadGraphOverview() {
  try {
    const data = await (await fetch(`${API}/graph/overview`)).json();
    overviewData = data;
    viewMode = 'overview';
    document.getElementById('graph-back-btn').style.display = 'none';
    document.getElementById('load-more-btn').style.display = 'none';
    renderOverview(data);
    renderCommunityFilters(data.communities);
    document.getElementById('stat-nodes').textContent = data.stats.node_count;
    document.getElementById('stat-edges').textContent = data.stats.edge_count;
    document.getElementById('stat-comms').textContent = data.stats.community_count;
  } catch (_) {}
}

/**
 * Renders one circle per community, sized by member count, via a D3 pack layout.
 * @param {Object} data - Response from GET /graph/overview.
 */
function renderOverview(data) {
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();
  const W = document.getElementById('graph-svg').clientWidth;
  const H = document.getElementById('graph-svg').clientHeight;
  const g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', e => g.attr('transform', e.transform)));

  const root = d3.pack().size([W - 20, H - 20]).padding(8)(
    d3.hierarchy({ children: data.communities }).sum(d => d.size || 1)
  );

  const bubble = g.selectAll('g').data(root.children || []).enter().append('g')
    .attr('class', 'comm-bubble')
    .attr('transform', d => `translate(${d.x + 10},${d.y + 10})`)
    .on('click', (event, d) => openCommunity(d.data.id));

  bubble.append('circle').attr('r', d => d.r)
    .attr('fill', d => d.data.color + '22').attr('stroke', d => d.data.color).attr('stroke-width', 2);

  bubble.append('text').text(d => d.data.label).attr('text-anchor', 'middle').attr('dy', -4)
    .attr('font-size', 11).attr('fill', d => d.data.color).attr('font-weight', 700);

  bubble.append('text').text(d => `${d.data.size} entities`).attr('text-anchor', 'middle').attr('dy', 11)
    .attr('font-size', 9).attr('fill', d => d.data.color);
}

/**
 * Fetches a community's nodes/edges and renders them, replacing the overview.
 * @param {number} id - The community id to open.
 */
async function openCommunity(id) {
  const data = await (await fetch(`${API}/graph/community/${id}?limit=150`)).json();
  viewMode = 'detail';
  currentCommunityId = id;
  currentLimit = 150;
  graphData = { nodes: data.nodes, edges: data.edges };
  document.getElementById('graph-back-btn').style.display = 'inline-block';
  document.getElementById('load-more-btn').style.display = data.truncated ? 'inline-block' : 'none';
  renderGraph(graphData);
}

/**
 * Merges newly fetched nodes/edges into the currently rendered graph in place,
 * then re-renders. Nodes that already exist keep their D3-assigned x/y
 * (force simulations only randomize position for nodes missing x/y), so
 * already-visible nodes do not jump when new ones are added.
 * @param {Array} newNodes - Node objects to add (deduped by id).
 * @param {Array} newEdges - Edge objects to add (deduped by source-target pair).
 */
function mergeIntoGraph(newNodes, newEdges) {
  const existingIds = new Set(graphData.nodes.map(n => n.id));
  for (const n of newNodes) {
    if (!existingIds.has(n.id)) { graphData.nodes.push(n); existingIds.add(n.id); }
  }
  const edgeKey = e => `${e.source}->${e.target}`;
  const existingEdgeKeys = new Set(graphData.edges.map(edgeKey));
  for (const e of newEdges) {
    const k = edgeKey(e);
    if (!existingEdgeKeys.has(k)) { graphData.edges.push(e); existingEdgeKeys.add(k); }
  }
  renderGraph(graphData);
}

/**
 * Fetches a node's 1-hop neighbors and merges them into the current view.
 * @param {string} name - The node id to expand.
 */
async function expandNode(name) {
  const data = await (await fetch(`${API}/graph/node/${encodeURIComponent(name)}/neighbors?limit=40`)).json();
  mergeIntoGraph(data.nodes, data.edges);
}

/**
 * Re-fetches the current community at a higher limit and merges the result.
 * @returns {Promise<boolean>} Whether the community still has more nodes beyond the new limit.
 */
async function loadMoreCommunity() {
  currentLimit += 150;
  const data = await (await fetch(`${API}/graph/community/${currentCommunityId}?limit=${currentLimit}`)).json();
  mergeIntoGraph(data.nodes, data.edges);
  return data.truncated;
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

  node.on('click', (event, d) => expandNode(d.id));

  const tooltip = document.getElementById('graph-tooltip');
  node.on('mouseover', (event, d) => {
    const rels = data.edges.filter(e => e.source === d.id || e.target === d.id)
      .map(e => `<div class="tt-rel">${e.source} →[${e.relation}]→ ${e.target}</div>`).join('');
    tooltip.innerHTML = `<div class="tt-name">${d.id}</div><div class="tt-type">Community ${d.community + 1}</div>${rels}`;
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
 * Renders the subgraph of the latest Q&A answer directly (no community
 * overview needed first) — the pipeline already caps this at <=150 nodes.
 * @param {string[]} nodeNames - Node ids from the query response.
 * @param {Array} edgeTuples - [source, relation, target] tuples from the query response.
 */
function showFocusSubgraph(nodeNames, edgeTuples) {
  const nodeSet = new Set(nodeNames);
  const nodes = nodeNames.map(id => ({
    id,
    community: 0,
    color: '#f59e0b',
    degree: edgeTuples.filter(e => e[0] === id || e[2] === id).length,
  }));
  const edges = edgeTuples
    .filter(e => nodeSet.has(e[0]) && nodeSet.has(e[2]))
    .map(e => ({ source: e[0], target: e[2], relation: e[1] }));
  viewMode = 'detail';
  currentCommunityId = null;
  graphData = { nodes, edges };
  document.getElementById('graph-back-btn').style.display = 'inline-block';
  document.getElementById('load-more-btn').style.display = 'none';
  renderGraph(graphData);
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
  if (!res.ok) { alert('Export failed: graph not built yet.'); return; }
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
    alert('Import failed: ' + (err.detail || 'invalid .graphrag file.'));
    return;
  }
  const { docs } = await res.json();
  document.getElementById('docs-list').innerHTML = '';
  docs.forEach(addDocItem);
  setAppState('ready');
}

document.getElementById('export-btn').addEventListener('click', exportKG);
document.getElementById('import-input').addEventListener('change', importKG);

document.getElementById('new-chat-btn').addEventListener('click', () => {
  chatHistory = [];
  const area = document.getElementById('chat-area');
  area.innerHTML = `<div class="msg msg-bot">
    <div class="msg-bot-hdr">✦ GraphRAG</div>
    <span class="msg-text">New conversation started. Ask your question!</span>
  </div>`;
});

setAppState('upload');
initDocList();
