/**
 * datlinx - VS Code Webview マインドマップロジック
 */

// VS Code APIの初期化
const vscode = acquireVsCodeApi ? acquireVsCodeApi() : null;

// アプリケーション状態
const state = {
    parsedFiles: [],
    nodes: new Map(),
    edges: [],
    selectedNodeId: null, // [4] 選択中ノード
    searchQuery: "",      // [3] 検索クエリ
    zoom: 1,
    panX: 40,
    panY: 40,
    isPanning: false,
    startX: 0,
    startY: 0,
    currentModalNode: null
};

// DOM要素
const canvasWrapper = document.getElementById('canvas-wrapper');
const canvas = document.getElementById('canvas');
const svgLayer = document.getElementById('svg-layer');
const nodesLayer = document.getElementById('nodes-layer');
const emptyState = document.getElementById('empty-state');
const searchInput = document.getElementById('search-input');
const searchClear = document.getElementById('search-clear');
const searchCount = document.getElementById('search-count');
const statsPill = document.getElementById('stats-pill');
const sidebarFiles = document.getElementById('sidebar-files');
const fileCountBadge = document.getElementById('file-count-badge');
const sidebar = document.getElementById('sidebar');
const folderNameBadge = document.getElementById('folder-name-badge');

/**
 * コメント除去
 */
function stripSqlComments(sql) {
    return sql
        .replace(/\/\*[\s\S]*?\*\//g, ' ')
        .replace(/--.*$/gm, ' ');
}

/**
 * [2] SQLパース
 * (FROM|JOIN)( ?\n.*| )(\n.*)?([a-zA-Z0-9]+\.)?(テーブル名|プロシージャ名|ビュー名)
 */
function parseSqlContent(fileName, fullPath, sqlContent) {
    const cleanSql = stripSqlComments(sqlContent);

    // 1. 定義されているオブジェクト名と種別
    const createRegex = /CREATE\s+(?:OR\s+REPLACE\s+)?(?:DEFENDER\s+|SECURITY\s+DEFINER\s+)?(PROCEDURE|FUNCTION|VIEW)\s+(?:\[?([a-zA-Z0-9_]+)\]?\.)?\[?([a-zA-Z0-9_]+)\]?/i;
    const matchCreate = cleanSql.match(createRegex);

    let objType = 'VIEW';
    let schema = '';
    let objName = '';

    if (matchCreate) {
        objType = matchCreate[1].toUpperCase();
        schema = matchCreate[2] || '';
        objName = matchCreate[3];
    } else {
        const baseName = fileName.replace(/\.[^/.]+$/, "");
        objName = baseName;
        if (/^sp_/i.test(baseName)) objType = 'PROCEDURE';
        else if (/^fn_/i.test(baseName)) objType = 'FUNCTION';
        else if (/^v_/i.test(baseName)) objType = 'VIEW';
    }

    // 2. 要件の正規表現で依存元を抽出
    const fromJoinRegex = /(?:\bFROM|\bJOIN)(?: ?\r?\n[ \t]*|[ \t]+)(?:\r?\n[ \t]*)?(?:\[?([a-zA-Z0-9_]+)\]?\.)?\[?([a-zA-Z0-9_]+)\]?/gi;
    
    const dependencies = [];
    let match;
    const reservedKeywords = new Set([
        'SELECT', 'WHERE', 'ON', 'AS', 'AND', 'OR', 'SET', 'GROUP', 'ORDER', 'HAVING',
        'LIMIT', 'TOP', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'OUTER', 'UNION',
        'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'INTO', 'VALUES', 'UPDATE', 'DELETE', 'INSERT',
        'LATERAL', 'UNNEST', 'APPLY'
    ]);

    while ((match = fromJoinRegex.exec(cleanSql)) !== null) {
        const depSchema = match[1] || '';
        const depName = match[2];

        if (!depName) continue;
        if (reservedKeywords.has(depName.toUpperCase())) continue;
        if (/^\d+$/.test(depName)) continue;

        if (depName.toLowerCase() !== objName.toLowerCase()) {
            if (!dependencies.some(d => d.name.toLowerCase() === depName.toLowerCase())) {
                dependencies.push({
                    schema: depSchema,
                    name: depName
                });
            }
        }
    }

    return {
        fileName,
        fullPath: fullPath || '',
        content: sqlContent,
        objType,
        schema,
        name: objName,
        dependencies
    };
}

/**
 * グラフ構築
 */
function buildGraph(parsedFiles) {
    state.nodes.clear();
    state.edges = [];

    // 1. ファイル定義オブジェクト
    parsedFiles.forEach(file => {
        const id = file.name.toLowerCase();
        state.nodes.set(id, {
            id,
            name: file.name,
            schema: file.schema,
            type: file.objType,
            fileName: file.fileName,
            fullPath: file.fullPath,
            content: file.content,
            x: 0,
            y: 0,
            level: 0,
            inDegree: 0,
            outDegree: 0
        });
    });

    // 2. 参照されているが未定義のオブジェクト（基底テーブル）
    parsedFiles.forEach(file => {
        file.dependencies.forEach(dep => {
            const depId = dep.name.toLowerCase();
            if (!state.nodes.has(depId)) {
                state.nodes.set(depId, {
                    id: depId,
                    name: dep.name,
                    schema: dep.schema,
                    type: 'TABLE',
                    fileName: '(Database Table)',
                    fullPath: '',
                    content: null,
                    x: 0,
                    y: 0,
                    level: 0,
                    inDegree: 0,
                    outDegree: 0
                });
            }
        });
    });

    // 3. エッジ構築: 依存元 (from) ──▶ 依存先 (to)
    let edgeCounter = 0;
    parsedFiles.forEach(file => {
        const targetId = file.name.toLowerCase();
        file.dependencies.forEach(dep => {
            const sourceId = dep.name.toLowerCase();
            const edgeId = `edge_${sourceId}_to_${targetId}_${edgeCounter++}`;
            state.edges.push({
                id: edgeId,
                from: sourceId,
                to: targetId
            });
        });
    });

    // 次数計算
    state.edges.forEach(edge => {
        const sourceNode = state.nodes.get(edge.from);
        const targetNode = state.nodes.get(edge.to);
        if (sourceNode) sourceNode.outDegree++;
        if (targetNode) targetNode.inDegree++;
    });

    // 4. トポロジカル階層計算
    computeNodeLevels();

    // 5. 自動レイアウト（ノード被り防止マージン）
    layoutNodes();

    // 6. レンダリング
    renderGraph();
    renderSidebar();
    updateStats();
}

/**
 * 階層（Level）計算
 */
function computeNodeLevels() {
    state.nodes.forEach(node => {
        node.level = (node.inDegree === 0) ? 0 : 0;
    });

    let changed = true;
    let iteration = 0;
    const maxIterations = 50;

    while (changed && iteration < maxIterations) {
        changed = false;
        iteration++;

        state.edges.forEach(edge => {
            const source = state.nodes.get(edge.from);
            const target = state.nodes.get(edge.to);
            if (source && target) {
                if (target.level <= source.level) {
                    target.level = source.level + 1;
                    changed = true;
                }
            }
        });
    }
}

/**
 * ノード自動レイアウト
 */
function layoutNodes() {
    const nodeWidth = 280;
    const horizontalGap = 130;
    const colWidth = nodeWidth + horizontalGap; // 410px

    const rowHeight = 150; // ノード高さ約100px + 垂直マージン50px
    const startX = 80;
    const startY = 80;

    const levelGroups = new Map();
    state.nodes.forEach(node => {
        if (!levelGroups.has(node.level)) {
            levelGroups.set(node.level, []);
        }
        levelGroups.get(node.level).push(node);
    });

    const typePriority = { 'TABLE': 0, 'VIEW': 1, 'FUNCTION': 2, 'PROCEDURE': 3 };
    
    let maxCount = 0;
    levelGroups.forEach(nodes => {
        if (nodes.length > maxCount) maxCount = nodes.length;
    });
    const maxColumnHeight = maxCount * rowHeight;

    levelGroups.forEach((nodesInLevel, level) => {
        nodesInLevel.sort((a, b) => {
            const pA = typePriority[a.type] ?? 99;
            const pB = typePriority[b.type] ?? 99;
            if (pA !== pB) return pA - pB;
            return a.name.localeCompare(b.name);
        });

        const colHeight = nodesInLevel.length * rowHeight;
        const levelStartY = startY + Math.max(0, (maxColumnHeight - colHeight) / 2);

        nodesInLevel.forEach((node, idx) => {
            node.x = startX + (level * colWidth);
            node.y = levelStartY + (idx * rowHeight);
        });
    });
}

/**
 * グラフ描画
 */
function renderGraph() {
    nodesLayer.innerHTML = '';
    
    const existingPaths = svgLayer.querySelectorAll('.edge-path');
    existingPaths.forEach(p => p.remove());

    if (state.nodes.size === 0) {
        emptyState.classList.remove('hidden');
        return;
    }
    emptyState.classList.add('hidden');

    state.nodes.forEach(node => {
        const nodeEl = createNodeElement(node);
        nodesLayer.appendChild(nodeEl);
        node.element = nodeEl;
    });

    updateEdges();
}

/**
 * ノード要素生成
 */
function createNodeElement(node) {
    const el = document.createElement('div');
    el.className = 'node';
    el.id = `node-${node.id}`;
    el.style.left = `${node.x}px`;
    el.style.top = `${node.y}px`;

    let badgeClass = 'badge-table';
    if (node.type === 'VIEW') badgeClass = 'badge-view';
    else if (node.type === 'PROCEDURE') badgeClass = 'badge-procedure';
    else if (node.type === 'FUNCTION') badgeClass = 'badge-function';

    el.innerHTML = `
        <div class="node-header">
            <span class="badge ${badgeClass}">${node.type}</span>
            <span class="node-level-tag">Level ${node.level}</span>
        </div>
        <div class="node-body">
            ${node.schema ? `<div class="node-schema">${escapeHtml(node.schema)}.</div>` : ''}
            <div class="node-name" title="${escapeHtml(node.name)}">${escapeHtml(node.name)}</div>
        </div>
        <div class="node-footer">
            <span class="stat-item" title="依存元 (参照している元)">
                In: ${node.inDegree}
            </span>
            <span class="stat-item" title="依存先 (参照されている先)">
                Out: ${node.outDegree}
            </span>
            <div style="display:flex; gap:6px;">
                ${node.content ? `<span class="stat-item" title="SQL詳細表示" style="cursor:pointer;" onclick="event.stopPropagation(); showSqlModal('${node.id}');">👁️</span>` : ''}
                ${node.fullPath ? `<span class="stat-item" title="VS Codeエディタで開く" style="cursor:pointer;" onclick="event.stopPropagation(); openFileInVSCode('${node.id}');">📄</span>` : ''}
            </div>
        </div>
    `;

    // ドラッグ移動 & クリック（ドラッグ時は選択解除・トグルを防止）
    setupNodeDrag(el, node);

    return el;
}

/**
 * [4] 依存関係探索
 */
function getLineageInfo(targetNodeId) {
    const upstreamNodeIds = new Set();
    const upstreamEdgeIds = new Set();
    const queueUp = [targetNodeId];

    while (queueUp.length > 0) {
        const currentId = queueUp.shift();
        const incomingEdges = state.edges.filter(e => e.to === currentId);
        for (const edge of incomingEdges) {
            upstreamEdgeIds.add(edge.id);
            if (edge.from !== targetNodeId && !upstreamNodeIds.has(edge.from)) {
                upstreamNodeIds.add(edge.from);
                queueUp.push(edge.from);
            }
        }
    }

    const downstreamNodeIds = new Set();
    const downstreamEdgeIds = new Set();
    const queueDown = [targetNodeId];

    while (queueDown.length > 0) {
        const currentId = queueDown.shift();
        const outgoingEdges = state.edges.filter(e => e.from === currentId);
        for (const edge of outgoingEdges) {
            downstreamEdgeIds.add(edge.id);
            if (edge.to !== targetNodeId && !downstreamNodeIds.has(edge.to)) {
                downstreamNodeIds.add(edge.to);
                queueDown.push(edge.to);
            }
        }
    }

    return {
        selectedNodeId: targetNodeId,
        upstreamNodeIds,
        upstreamEdgeIds,
        downstreamNodeIds,
        downstreamEdgeIds
    };
}

/**
 * エッジ（ベジェ曲線）の更新
 */
function updateEdges() {
    const lineage = state.selectedNodeId ? getLineageInfo(state.selectedNodeId) : null;

    state.edges.forEach(edge => {
        const source = state.nodes.get(edge.from);
        const target = state.nodes.get(edge.to);
        if (!source || !target) return;

        let pathEl = document.getElementById(edge.id);
        if (!pathEl) {
            pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            pathEl.setAttribute('id', edge.id);
            pathEl.setAttribute('class', 'edge-path');
            svgLayer.appendChild(pathEl);
        }

        const nodeWidth = 280;
        const nodeHeight = 88;

        const fromX = source.x + nodeWidth;
        const fromY = source.y + (nodeHeight / 2);
        const toX = target.x;
        const toY = target.y + (nodeHeight / 2);

        const dx = Math.max(60, (toX - fromX) * 0.5);
        const d = `M ${fromX} ${fromY} C ${fromX + dx} ${fromY}, ${toX - dx} ${toY}, ${toX} ${toY}`;
        pathEl.setAttribute('d', d);

        // [4] 色分けスタイル適用
        if (lineage) {
            if (lineage.upstreamEdgeIds.has(edge.id)) {
                pathEl.classList.add('edge-upstream');
                pathEl.classList.remove('edge-downstream', 'dimmed');
                pathEl.setAttribute('marker-end', 'url(#arrow-green)');
            } else if (lineage.downstreamEdgeIds.has(edge.id)) {
                pathEl.classList.add('edge-downstream');
                pathEl.classList.remove('edge-upstream', 'dimmed');
                pathEl.setAttribute('marker-end', 'url(#arrow-red)');
            } else {
                pathEl.classList.remove('edge-upstream', 'edge-downstream');
                pathEl.classList.add('dimmed');
                pathEl.setAttribute('marker-end', 'url(#arrow-default)');
            }
        } else {
            pathEl.classList.remove('edge-upstream', 'edge-downstream', 'dimmed');
            pathEl.setAttribute('marker-end', 'url(#arrow-default)');
        }
    });
}

function toggleNodeSelection(nodeId) {
    if (state.selectedNodeId === nodeId) {
        clearSelection();
        return;
    }
    state.selectedNodeId = nodeId;
    applySelectionStyles();
}

function clearSelection() {
    state.selectedNodeId = null;
    applySelectionStyles();
}

/**
 * [3] 検索ハイライト & [4] 依存関係ハイライト適用
 */
function applySelectionStyles() {
    const lineage = state.selectedNodeId ? getLineageInfo(state.selectedNodeId) : null;
    const query = state.searchQuery.trim().toLowerCase();

    state.nodes.forEach(node => {
        const el = node.element;
        if (!el) return;

        let isSelected = false;
        let isUpstream = false;
        let isDownstream = false;
        let isSearchMatch = false;
        let isDimmed = false;

        if (lineage) {
            if (node.id === lineage.selectedNodeId) isSelected = true;
            else if (lineage.upstreamNodeIds.has(node.id)) isUpstream = true;
            else if (lineage.downstreamNodeIds.has(node.id)) isDownstream = true;
            else isDimmed = true;
        }

        if (query) {
            const matchName = node.name.toLowerCase().includes(query);
            const matchSchema = (node.schema || '').toLowerCase().includes(query);
            if (matchName || matchSchema) {
                isSearchMatch = true;
                isDimmed = false;
            } else if (!lineage) {
                isDimmed = true;
            }
        }

        el.classList.toggle('node-selected', isSelected);
        el.classList.toggle('node-upstream', isUpstream);
        el.classList.toggle('node-downstream', isDownstream);
        el.classList.toggle('node-search-match', isSearchMatch && !isSelected && !isUpstream && !isDownstream);
        el.classList.toggle('dimmed', isDimmed);
    });

    updateEdges();
}

/**
 * [3] 検索ハンドリング
 */
searchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value;
    const query = state.searchQuery.trim().toLowerCase();

    if (query) {
        searchClear.style.display = 'block';
        let matchCount = 0;
        let firstMatchNode = null;

        state.nodes.forEach(node => {
            const matchName = node.name.toLowerCase().includes(query);
            const matchSchema = (node.schema || '').toLowerCase().includes(query);
            if (matchName || matchSchema) {
                matchCount++;
                if (!firstMatchNode) firstMatchNode = node;
            }
        });

        searchCount.textContent = `${matchCount} 件`;

        if (firstMatchNode && matchCount > 0) {
            centerOnNode(firstMatchNode);
        }
    } else {
        searchClear.style.display = 'none';
        searchCount.textContent = '';
    }

    applySelectionStyles();
});

searchClear.addEventListener('click', () => {
    searchInput.value = '';
    state.searchQuery = '';
    searchClear.style.display = 'none';
    searchCount.textContent = '';
    applySelectionStyles();
});

/**
 * ノードドラッグ移動（移動時は選択解除・トグルを防止）
 */
function setupNodeDrag(element, node) {
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let nodeStartX = 0;
    let nodeStartY = 0;
    let hasMoved = false;

    element.addEventListener('mousedown', (e) => {
        if (e.target.closest('.stat-item')) return;
        isDragging = true;
        hasMoved = false;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        nodeStartX = node.x;
        nodeStartY = node.y;
        element.style.zIndex = 50;
        e.stopPropagation();
    });

    window.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const movedDist = Math.hypot(e.clientX - dragStartX, e.clientY - dragStartY);
        if (movedDist > 4) {
            hasMoved = true;
        }
        const dx = (e.clientX - dragStartX) / state.zoom;
        const dy = (e.clientY - dragStartY) / state.zoom;
        node.x = nodeStartX + dx;
        node.y = nodeStartY + dy;
        element.style.left = `${node.x}px`;
        element.style.top = `${node.y}px`;
        updateEdges();
    });

    window.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            element.style.zIndex = '';
        }
    });

    // クリック時: ドラッグ移動していなければ選択トグル
    element.addEventListener('click', (e) => {
        e.stopPropagation();
        if (hasMoved) {
            hasMoved = false;
            return;
        }
        toggleNodeSelection(node.id);
    });
}

/**
 * キャンバスのパン＆ズーム（ドラッグ移動中はハイライトを解除しない）
 */
function updateTransform() {
    canvas.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
}

let isPanningMove = false;
let panStartMouseX = 0;
let panStartMouseY = 0;

canvasWrapper.addEventListener('mousedown', (e) => {
    if (e.target.closest('.node') || e.target.closest('.controls-overlay')) return;
    state.isPanning = true;
    isPanningMove = false;
    panStartMouseX = e.clientX;
    panStartMouseY = e.clientY;
    state.startX = e.clientX - state.panX;
    state.startY = e.clientY - state.panY;
    canvasWrapper.classList.add('grabbing');
    // ここでは clearSelection() を呼ばない（ドラッグでハイライトが外れるのを防止）
});

window.addEventListener('mousemove', (e) => {
    if (!state.isPanning) return;
    const movedDist = Math.hypot(e.clientX - panStartMouseX, e.clientY - panStartMouseY);
    if (movedDist > 4) {
        isPanningMove = true; // 4px以上動いた場合はドラッグ移動と判定
    }
    state.panX = e.clientX - state.startX;
    state.panY = e.clientY - state.startY;
    updateTransform();
});

window.addEventListener('mouseup', () => {
    if (state.isPanning) {
        state.isPanning = false;
        canvasWrapper.classList.remove('grabbing');
        // ドラッグ移動ではなく、背景をその場でクリックしたときだけ選択解除
        if (!isPanningMove) {
            clearSelection();
        }
    }
});

canvasWrapper.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = 1.08;
    const mouseX = e.clientX - canvasWrapper.getBoundingClientRect().left;
    const mouseY = e.clientY - canvasWrapper.getBoundingClientRect().top;

    let newZoom;
    if (e.deltaY < 0) {
        newZoom = Math.min(2.5, state.zoom * zoomFactor);
    } else {
        newZoom = Math.max(0.2, state.zoom / zoomFactor);
    }

    state.panX = mouseX - (mouseX - state.panX) * (newZoom / state.zoom);
    state.panY = mouseY - (mouseY - state.panY) * (newZoom / state.zoom);
    state.zoom = newZoom;
    updateTransform();
});

document.getElementById('btn-zoom-in').addEventListener('click', () => {
    state.zoom = Math.min(2.5, state.zoom * 1.2);
    updateTransform();
});
document.getElementById('btn-zoom-out').addEventListener('click', () => {
    state.zoom = Math.max(0.2, state.zoom / 1.2);
    updateTransform();
});
document.getElementById('btn-zoom-reset').addEventListener('click', () => {
    fitToScreen();
});
document.getElementById('btn-clear-selection').addEventListener('click', () => {
    clearSelection();
});
document.getElementById('btn-auto-layout').addEventListener('click', () => {
    layoutNodes();
    renderGraph();
    fitToScreen();
});

/**
 * 全体表示フィット
 */
function fitToScreen() {
    if (state.nodes.size === 0) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    state.nodes.forEach(node => {
        minX = Math.min(minX, node.x);
        minY = Math.min(minY, node.y);
        maxX = Math.max(maxX, node.x + 280);
        maxY = Math.max(maxY, node.y + 120);
    });

    const padding = 80;
    const contentW = (maxX - minX) + padding * 2;
    const contentH = (maxY - minY) + padding * 2;
    const viewW = canvasWrapper.clientWidth;
    const viewH = canvasWrapper.clientHeight;

    const scaleX = viewW / contentW;
    const scaleY = viewH / contentH;
    state.zoom = Math.min(1.1, Math.max(0.25, Math.min(scaleX, scaleY)));

    state.panX = (viewW - contentW * state.zoom) / 2 - minX * state.zoom + padding * state.zoom;
    state.panY = (viewH - contentH * state.zoom) / 2 - minY * state.zoom + padding * state.zoom;

    updateTransform();
}

function centerOnNode(node) {
    const viewW = canvasWrapper.clientWidth;
    const viewH = canvasWrapper.clientHeight;
    state.panX = (viewW / 2) - ((node.x + 140) * state.zoom);
    state.panY = (viewH / 2) - ((node.y + 50) * state.zoom);
    updateTransform();
}

/**
 * VS Codeメッセージング
 */
document.getElementById('btn-select-folder').addEventListener('click', () => {
    requestSelectFolder();
});

document.getElementById('btn-reload').addEventListener('click', () => {
    if (vscode) {
        vscode.postMessage({ type: 'reload' });
    }
});

function requestSelectFolder() {
    if (vscode) {
        vscode.postMessage({ type: 'selectFolder' });
    }
}

function openFileInVSCode(nodeId) {
    const node = state.nodes.get(nodeId);
    if (node && node.fullPath && vscode) {
        vscode.postMessage({
            type: 'openFileInEditor',
            filePath: node.fullPath
        });
    }
}

// 拡張機能からのメッセージ受信
window.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg.type === 'loadFiles') {
        folderNameBadge.textContent = msg.folderName || 'SQL Files';
        folderNameBadge.title = msg.folderPath || '';

        const parsedList = msg.files.map(f => parseSqlContent(f.name, f.fullPath, f.content));
        state.parsedFiles = parsedList;
        buildGraph(parsedList);
        fitToScreen();
    }
});

// サイドバー
function renderSidebar() {
    sidebarFiles.innerHTML = '';
    fileCountBadge.textContent = `${state.parsedFiles.length} 件`;

    state.parsedFiles.forEach(file => {
        const card = document.createElement('div');
        card.className = 'file-card';
        card.innerHTML = `
            <div class="file-card-title">
                <span>${escapeHtml(file.name)}</span>
                <span class="badge ${file.objType === 'PROCEDURE' ? 'badge-procedure' : file.objType === 'FUNCTION' ? 'badge-function' : 'badge-view'}">${file.objType}</span>
            </div>
            <div class="file-card-deps">
                ${file.dependencies.length > 0 
                    ? file.dependencies.map(d => `<span class="dep-pill">⮑ ${escapeHtml(d.name)}</span>`).join('') 
                    : '<span style="color:#64748b;">(依存なし)</span>'}
            </div>
        `;

        card.addEventListener('click', () => {
            const node = state.nodes.get(file.name.toLowerCase());
            if (node) {
                centerOnNode(node);
                toggleNodeSelection(node.id);
            }
        });

        sidebarFiles.appendChild(card);
    });
}

function updateStats() {
    statsPill.textContent = `${state.nodes.size} ノード / ${state.edges.length} 依存関係`;
}

// サイドバー開閉（margin-rightでスムーズに伸縮し、キャンバス描画領域が右端まで拡大）
document.getElementById('btn-toggle-sidebar').addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
});

// SQLモーダル
const sqlModal = document.getElementById('sql-modal');
const modalTitle = document.getElementById('modal-title');
const modalContent = document.getElementById('modal-content');
const btnModalOpenEditor = document.getElementById('btn-modal-open-editor');

function showSqlModal(nodeId) {
    const node = state.nodes.get(nodeId);
    if (!node || !node.content) return;

    state.currentModalNode = node;
    modalTitle.textContent = `${node.name} (${node.fileName})`;
    modalContent.textContent = node.content;

    if (node.fullPath) {
        btnModalOpenEditor.style.display = 'inline-flex';
    } else {
        btnModalOpenEditor.style.display = 'none';
    }

    sqlModal.classList.remove('hidden');
}

btnModalOpenEditor.addEventListener('click', () => {
    if (state.currentModalNode && state.currentModalNode.fullPath) {
        openFileInVSCode(state.currentModalNode.id);
        sqlModal.classList.add('hidden');
    }
});

document.getElementById('btn-close-modal').addEventListener('click', () => {
    sqlModal.classList.add('hidden');
});

sqlModal.addEventListener('click', (e) => {
    if (e.target === sqlModal) sqlModal.classList.add('hidden');
});

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// 読み込み完了通知を拡張機能ホストへ送信
window.addEventListener('DOMContentLoaded', () => {
    if (vscode) {
        vscode.postMessage({ type: 'ready' });
    }
});
