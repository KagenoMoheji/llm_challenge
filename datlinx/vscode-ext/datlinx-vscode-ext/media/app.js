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
    duplicateTables: [],        // 重複テーブル情報一覧
    hideDuplicateTables: false, // 重複「CREATE TABLE」の非表示トグル状態
    selectedNodeId: null,       // [4] 選択中ノード
    searchQuery: "",            // [3] 検索クエリ
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
const sidebar = document.getElementById('sidebar');
const sidebarFiles = document.getElementById('sidebar-files');
const fileCountBadge = document.getElementById('file-count-badge');
const sidebarDuplicates = document.getElementById('sidebar-duplicates');
const toggleHideDuplicates = document.getElementById('toggle-hide-duplicates');
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
 * [2] SQLパース (CREATE PROCEDURE / VIEW / FUNCTION / TABLE + FROM / JOIN + INSERT INTO)
 */
function parseSqlContent(fileName, fullPath, sqlContent) {
    const cleanSql = stripSqlComments(sqlContent);

    // 1. 定義されているオブジェクト名と種別
    const createRegex = /CREATE\s+(?:OR\s+REPLACE\s+)?(?:DEFENDER\s+|SECURITY\s+DEFINER\s+)?(PROCEDURE|FUNCTION|VIEW|TABLE)\s+(?:\[?([a-zA-Z0-9_]+)\]?\.)?\[?([a-zA-Z0-9_]+)\]?/i;
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
        else if (/^(?:tbl_|t_|m_|create_table_)/i.test(baseName)) objType = 'TABLE';
    }

    // 2. FROM / JOIN からの依存元抽出
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

    // 3. INSERT INTO 投入先テーブルの抽出 (プロシージャ用)
    const insertRegex = /\bINSERT\s+(?:INTO\s+)?(?:\[?([a-zA-Z0-9_]+)\]?\.)?\[?([a-zA-Z0-9_]+)\]?/gi;
    const insertTargets = [];
    let insertMatch;

    while ((insertMatch = insertRegex.exec(cleanSql)) !== null) {
        const insSchema = insertMatch[1] || '';
        const insName = insertMatch[2];

        if (!insName) continue;
        if (reservedKeywords.has(insName.toUpperCase())) continue;

        if (!insertTargets.some(t => t.name.toLowerCase() === insName.toLowerCase())) {
            insertTargets.push({
                schema: insSchema,
                name: insName
            });
        }
    }

    return {
        fileName,
        fullPath: fullPath || '',
        content: sqlContent,
        objType,
        schema,
        name: objName,
        dependencies,
        insertTargets
    };
}

/**
 * 重複テーブル一覧の検出
 * INSERTも行っているプロシージャの投入先テーブルと、CREATE TABLEされたテーブルの間で同名テーブルを検出
 */
function detectDuplicateTables(parsedFiles) {
    const tableDefinitions = new Map(); // tableNameLower -> file
    parsedFiles.forEach(file => {
        if (file.objType === 'TABLE') {
            tableDefinitions.set(file.name.toLowerCase(), file);
        }
    });

    const duplicates = [];
    parsedFiles.forEach(file => {
        if (file.insertTargets && file.insertTargets.length > 0) {
            file.insertTargets.forEach(target => {
                const targetLower = target.name.toLowerCase();
                if (tableDefinitions.has(targetLower)) {
                    const tableFile = tableDefinitions.get(targetLower);
                    duplicates.push({
                        tableName: target.name,
                        schema: target.schema || tableFile.schema,
                        procedureName: file.name,
                        procedureFileName: file.fileName,
                        procedureId: file.name.toLowerCase(),
                        tableFileName: tableFile.fileName,
                        tableId: targetLower
                    });
                }
            });
        }
    });

    state.duplicateTables = duplicates;
}

/**
 * グラフ構築
 */
function buildGraph(parsedFiles) {
    state.nodes.clear();
    state.edges = [];

    // 重複テーブルの検出
    detectDuplicateTables(parsedFiles);

    // 定義済みTABLEのセット
    const definedTableIds = new Set();
    parsedFiles.forEach(file => {
        if (file.objType === 'TABLE') {
            definedTableIds.add(file.name.toLowerCase());
        }
    });

    // 重複テーブル名セット
    const duplicateTableIds = new Set(state.duplicateTables.map(d => d.tableId));

    // プロシージャ投入先マップ: targetTableLower -> [procedureId, ...]
    const insertProducerMap = new Map();
    parsedFiles.forEach(file => {
        if (file.insertTargets) {
            file.insertTargets.forEach(target => {
                const tId = target.name.toLowerCase();
                if (!insertProducerMap.has(tId)) {
                    insertProducerMap.set(tId, []);
                }
                insertProducerMap.get(tId).push(file.name.toLowerCase());
            });
        }
    });

    // 1. 各ファイルで定義されているオブジェクトをノード登録
    parsedFiles.forEach(file => {
        const id = file.name.toLowerCase();

        // 「重複CREATE TABLEを非表示」がONかつ自身が重複TABLEの場合、マインドマップノードから除外
        if (state.hideDuplicateTables && file.objType === 'TABLE' && duplicateTableIds.has(id)) {
            return;
        }

        state.nodes.set(id, {
            id,
            name: file.name,
            schema: file.schema,
            type: file.objType,
            fileName: file.fileName,
            fullPath: file.fullPath,
            content: file.content,
            insertTargets: file.insertTargets || [],
            isDuplicateTable: duplicateTableIds.has(id) && file.objType === 'TABLE',
            x: 0,
            y: 0,
            level: 0,
            inDegree: 0,
            outDegree: 0
        });
    });

    // 2. FROM / JOIN で参照されているが未定義のオブジェクトを TABLE ノードとして登録
    // （※INSERT投入先テーブルでCREATE TABLEが無いものはプロシージャ自身が現在地となるためノード作成しない）
    parsedFiles.forEach(file => {
        file.dependencies.forEach(dep => {
            const depId = dep.name.toLowerCase();
            if (!state.nodes.has(depId)) {
                // 重複テーブルかつ非表示ONなら作成しない
                if (state.hideDuplicateTables && duplicateTableIds.has(depId)) return;
                // プロシージャの投入先でCREATE TABLEが無い場合も、プロシージャが現在地となるため作成しない
                if (insertProducerMap.has(depId) && !definedTableIds.has(depId)) return;

                state.nodes.set(depId, {
                    id: depId,
                    name: dep.name,
                    schema: dep.schema,
                    type: 'TABLE',
                    fileName: '(Database Table)',
                    fullPath: '',
                    content: null,
                    insertTargets: [],
                    isDuplicateTable: false,
                    x: 0,
                    y: 0,
                    level: 0,
                    inDegree: 0,
                    outDegree: 0
                });
            }
        });
    });

    // 3. エッジの構築
    let edgeCounter = 0;
    const addedEdgeSet = new Set();

    function addEdge(sourceId, targetId) {
        if (sourceId === targetId) return;
        const key = `${sourceId}___${targetId}`;
        if (addedEdgeSet.has(key)) return;
        addedEdgeSet.add(key);

        state.edges.push({
            id: `edge_${sourceId}_to_${targetId}_${edgeCounter++}`,
            from: sourceId,
            to: targetId
        });
    }

    parsedFiles.forEach(file => {
        const targetId = file.name.toLowerCase();

        // FROM / JOIN の接続
        file.dependencies.forEach(dep => {
            const sourceDepId = dep.name.toLowerCase();

            // もし参照元テーブルにINSERTしているプロシージャが存在する場合:
            // A) 重複CREATE TABLEがあり非表示トグルがONの場合
            // B) そもそも重複するCREATE TABLEが存在しない（CREATE TABLEが無い）場合
            // ──▶ プロシージャから直接接続（プロシージャ自身が投入先テーブルの現在地）
            if (insertProducerMap.has(sourceDepId)) {
                const isDupAndHidden = state.hideDuplicateTables && duplicateTableIds.has(sourceDepId);
                const isNotCreated = !definedTableIds.has(sourceDepId);

                if (isDupAndHidden || isNotCreated) {
                    const producers = insertProducerMap.get(sourceDepId);
                    producers.forEach(producerProcId => {
                        if (state.nodes.has(producerProcId) && state.nodes.has(targetId)) {
                            addEdge(producerProcId, targetId);
                        }
                    });
                    return;
                }
            }

            if (state.nodes.has(sourceDepId) && state.nodes.has(targetId)) {
                addEdge(sourceDepId, targetId);
            }
        });

        // INSERT INTO の接続 (プロシージャ ──▶ 投入先テーブル)
        // ※CREATE TABLE が存在し、かつ非表示トグルがOFFの時のみエッジを作成
        if (file.insertTargets && file.insertTargets.length > 0) {
            file.insertTargets.forEach(target => {
                const insTargetId = target.name.toLowerCase();
                // CREATE TABLE が無い場合、または非表示トグルONの場合はエッジを作らない
                if (!definedTableIds.has(insTargetId) || (state.hideDuplicateTables && duplicateTableIds.has(insTargetId))) {
                    return;
                }
                if (state.nodes.has(targetId) && state.nodes.has(insTargetId)) {
                    addEdge(targetId, insTargetId);
                }
            });
        }
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
    renderDuplicatesSidebar();
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
    const nodeWidth = 290;
    const horizontalGap = 130;
    const colWidth = nodeWidth + horizontalGap; // 420px

    const rowHeight = 155; // ノード高さ約100px + 垂直マージン55px
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

    // INSERT投入先テーブルのバッジ表示 (プロシージャがINSERTを持つ場合)
    let insertBadgeHtml = '';
    if (node.insertTargets && node.insertTargets.length > 0) {
        const targetNames = node.insertTargets.map(t => escapeHtml(t.name)).join(', ');
        insertBadgeHtml = `
            <div class="node-insert-badge" title="INSERT投入先テーブル (現在地): ${targetNames}">
                ↳ 投入先: ${targetNames}
            </div>
        `;
    }

    el.innerHTML = `
        <div class="node-header">
            <span class="badge ${badgeClass}">${node.type}</span>
            <span class="node-level-tag">Level ${node.level}</span>
        </div>
        <div class="node-body">
            ${node.schema ? `<div class="node-schema">${escapeHtml(node.schema)}.</div>` : ''}
            <div class="node-name" title="${escapeHtml(node.name)}">${escapeHtml(node.name)}</div>
            ${insertBadgeHtml}
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

        const nodeWidth = 290;
        const nodeHeight = 92;

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
        maxX = Math.max(maxX, node.x + 290);
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
    state.panX = (viewW / 2) - ((node.x + 145) * state.zoom);
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

/**
 * 上段: 解析済みSQLファイル一覧の描画
 */
function renderSidebar() {
    sidebarFiles.innerHTML = '';
    fileCountBadge.textContent = `${state.parsedFiles.length} 件`;

    state.parsedFiles.forEach(file => {
        const card = document.createElement('div');
        card.className = 'file-card';

        let badgeClass = 'badge-table';
        if (file.objType === 'VIEW') badgeClass = 'badge-view';
        else if (file.objType === 'PROCEDURE') badgeClass = 'badge-procedure';
        else if (file.objType === 'FUNCTION') badgeClass = 'badge-function';

        let insertHtml = '';
        if (file.insertTargets && file.insertTargets.length > 0) {
            insertHtml = file.insertTargets.map(t => `<span class="insert-pill">↳ INSERT: ${escapeHtml(t.name)}</span>`).join('');
        }

        card.innerHTML = `
            <div class="file-card-title">
                <span>${escapeHtml(file.name)}</span>
                <span class="badge ${badgeClass}">${file.objType}</span>
            </div>
            <div class="file-card-deps">
                ${insertHtml}
                ${file.dependencies.length > 0 
                    ? file.dependencies.map(d => `<span class="dep-pill">⮑ ${escapeHtml(d.name)}</span>`).join('') 
                    : (!insertHtml ? '<span style="color:#64748b;">(依存なし)</span>' : '')}
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

/**
 * 下段: 重複テーブル一覧の描画
 */
function renderDuplicatesSidebar() {
    sidebarDuplicates.innerHTML = '';

    if (state.duplicateTables.length === 0) {
        sidebarDuplicates.innerHTML = `
            <div style="text-align:center; padding: 24px 10px; color: var(--text-sub); font-size: 12px;">
                <div style="font-size: 18px; color: #34d399; margin-bottom: 6px;">✓</div>
                INSERT投入先とCREATE TABLEの重複はありません
            </div>
        `;
        return;
    }

    state.duplicateTables.forEach(dup => {
        const card = document.createElement('div');
        card.className = 'duplicate-card';
        card.innerHTML = `
            <div class="dup-table-name">
                <span>${escapeHtml(dup.schema ? dup.schema + '.' : '')}${escapeHtml(dup.tableName)}</span>
            </div>
            <div class="dup-detail">
                <div class="dup-row">
                    <span class="badge badge-procedure" style="font-size:9px;">PROC</span>
                    <span style="color:var(--text-main); font-weight:600;">${escapeHtml(dup.procedureName)}</span>
                    <span style="font-size:10px; color:#94a3b8;">(投入元)</span>
                </div>
                <div class="dup-row">
                    <span class="badge badge-table" style="font-size:9px;">TABLE</span>
                    <span style="color:var(--text-main); font-weight:600;">${escapeHtml(dup.tableFileName)}</span>
                    <span style="font-size:10px; color:#94a3b8;">(定義元)</span>
                </div>
            </div>
        `;

        // クリックで該当ノードへジャンプ
        card.addEventListener('click', () => {
            const targetNode = state.nodes.get(dup.procedureId) || state.nodes.get(dup.tableId);
            if (targetNode) {
                centerOnNode(targetNode);
                toggleNodeSelection(targetNode.id);
            }
        });

        sidebarDuplicates.appendChild(card);
    });
}

/**
 * 重複CREATE TABLE非表示トグルの変更イベント
 */
toggleHideDuplicates.addEventListener('change', (e) => {
    state.hideDuplicateTables = e.target.checked;
    buildGraph(state.parsedFiles);
    fitToScreen();
});

function updateStats() {
    statsPill.textContent = `${state.nodes.size} ノード / ${state.edges.length} 依存関係`;
}

// サイドバー開閉（margin-rightでスムーズに伸縮し、キャンバス描画領域が右端まで拡大）
document.getElementById('btn-toggle-sidebar').addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
});

/**
 * 各一覧のハンバーガーメニュー風折りたたみトグル
 */
const sectionFiles = document.getElementById('section-files');
const sectionDuplicates = document.getElementById('section-duplicates');

document.getElementById('btn-toggle-section-files').addEventListener('click', () => {
    sectionFiles.classList.toggle('is-collapsed');
});

document.getElementById('btn-toggle-section-duplicates').addEventListener('click', () => {
    sectionDuplicates.classList.toggle('is-collapsed');
});

/**
 * スプリッターによる上下リサイズ機能
 */
const resizer = document.getElementById('sidebar-resizer');
let isResizing = false;
let startY = 0;
let startHeight = 0;

resizer.addEventListener('mousedown', (e) => {
    if (sectionFiles.classList.contains('is-collapsed') || sectionDuplicates.classList.contains('is-collapsed')) {
        return;
    }
    isResizing = true;
    startY = e.clientY;
    startHeight = sectionFiles.getBoundingClientRect().height;
    resizer.classList.add('resizing');
    document.body.style.cursor = 'row-resize';
    e.preventDefault();
});

window.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const deltaY = e.clientY - startY;
    const newHeight = Math.max(90, Math.min(sidebar.clientHeight - 130, startHeight + deltaY));
    sectionFiles.style.height = `${newHeight}px`;
    sectionFiles.style.flex = 'none';
});

window.addEventListener('mouseup', () => {
    if (isResizing) {
        isResizing = false;
        resizer.classList.remove('resizing');
        document.body.style.cursor = '';
    }
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
