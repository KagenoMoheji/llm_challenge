// VS Code APIの取得
const vscode = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
let isImporting = false;
        // monomdのCSSを挿入
        document.addEventListener('DOMContentLoaded', () => {
            const monomdCssElement = document.getElementById('monomd-css');
            if (monomdCssElement && typeof getMonoMDCSS === 'function') {
                let css = getMonoMDCSS();
                
                // .checklist-content の margin-left のみを置換
                css = css.replace(
                    /(\.monomd-body \.checklist-content\s*{[^}]*margin-left:\s*)([^;]+)(;)/,
                    '$1-22px$3'
                );
                
                // .checklist-content input[type="checkbox"] の margin-top のみを置換
                css = css.replace(
                    /(\.monomd-body \.checklist-content input\[type="checkbox"\]\s*{[^}]*margin-top:\s*)([^;]+)(;)/,
                    '$16px$3'
                );
                
                monomdCssElement.textContent = css;
            }
        });

        const canvas = document.getElementById('canvas');
        const canvasContent = document.getElementById('canvas-content');
        const svg = document.getElementById('svg');
        const addNodeBtn = document.getElementById('addNodeBtn');
        const clearBtn = document.getElementById('clearBtn');
        const importBtn = document.getElementById('importBtn');
        const exportBtn = document.getElementById('exportBtn');
        const fileInput = document.getElementById('fileInput');
        const contextMenu = document.getElementById('contextMenu');
        const exportModal = document.getElementById('exportModal');
        const exportModalCloseBtn = document.getElementById('exportModalCloseBtn');
        const deleteNodeBtn = document.getElementById('deleteNode');
        const deleteConnectionBtn = document.getElementById('deleteConnection');
        const exportTsvBtn = document.getElementById('exportTsvBtn');
        const exportJsonBtn = document.getElementById('exportJsonBtn');
        const helpBtn = document.getElementById('helpBtn');
        const helpBtnMobile = document.getElementById('helpBtnMobile');
        const helpModal = document.getElementById('helpModal');
        const modalCloseBtn = document.getElementById('modalCloseBtn');
        
        // 画像モーダル用
        const imageModal = document.getElementById('imageModal');
        const imageModalImg = document.getElementById('imageModalImg');
        const imageModalCloseBtn = document.getElementById('imageModalCloseBtn');
        
        // ハンバーガーメニュー用
        const hamburgerBtn = document.getElementById('hamburgerBtn');
        const hamburgerMenu = document.getElementById('hamburgerMenu');
        const menuOverlay = document.getElementById('menuOverlay');
        const addNodeBtnMobile = document.getElementById('addNodeBtnMobile');
        const clearBtnMobile = document.getElementById('clearBtnMobile');
        const importBtnMobile = document.getElementById('importBtnMobile');
        const exportBtnMobile = document.getElementById('exportBtnMobile');

        let nodes = [];
        let connections = [];
        let nodeIdCounter = 0;
        let isDraggingCanvas = false;
        let dragStart = { x: 0, y: 0 };
        let selectedConnection = null;
        let selectedNode = null;
        let connectingFrom = null;
        
        // タッチ操作用の変数
        let touchStartTime = 0;
        let touchMoved = false;
        
        // ズーム用の変数
        let currentScale = 1;
        let lastTouchDistance = 0;

        // UUID生成関数
        function generateUUID() {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        }

        // UNIX時間取得
        function getUnixTime() {
            return Math.floor(Date.now() / 1000);
        }

        // 一意のノードID生成
        function generateNodeUniqueId() {
            return `${generateUUID()}_${getUnixTime()}`;
        }

        // ノード作成
        async function createNode(x, y, content = '# 新しいテストケース\n\n内容を記述...') {
            const nodeId = nodeIdCounter++;
            const node = document.createElement('div');
            node.className = 'node';
            node.style.left = x + 'px';
            node.style.top = y + 'px';
            
            node.innerHTML = `
                <div class="resize-handle top"></div>
                <div class="resize-handle bottom"></div>
                <div class="resize-handle left"></div>
                <div class="resize-handle right"></div>
                <div class="connector top" data-direction="top"></div>
                <div class="connector bottom" data-direction="bottom"></div>
                <div class="connector left" data-direction="left"></div>
                <div class="connector right" data-direction="right"></div>
                <div class="node-header">
                    <div class="node-left-section">
                        <select class="test-type type-正常系">
                            <option value="正常系">正常系</option>
                            <option value="異常系">異常系</option>
                            <option value="その他">その他</option>
                        </select>
                        <select class="node-status status-起票">
                            <option value="起票">起票</option>
                            <option value="OK">OK</option>
                            <option value="条件付OK">条件付OK</option>
                            <option value="NG">NG</option>
                            <option value="却下">却下</option>
                            <option value="保留">保留</option>
                        </select>
                    </div>
                    <div class="node-id-container">
                        <div class="node-id" contenteditable="true">TC-${String(nodeId + 1).padStart(3, '0')}</div>
                    </div>
                </div>
                <div class="view-mode">
                    <div class="node-content"></div>
                </div>
                <div class="edit-mode">
                    <textarea class="node-textarea">${content}</textarea>
                </div>
            `;

            const nodeData = {
                id: nodeId,
                uniqueId: generateNodeUniqueId(),
                element: node,
                x: x,
                y: y,
                width: null,
                height: null,
                content: content,
                testCaseId: `TC-${String(nodeId + 1).padStart(3, '0')}`,
                status: '起票',
                testType: '正常系'
            };

            nodes.push(nodeData);
            canvasContent.appendChild(node);

            // マークダウンレンダリング
            await updateNodeContent(nodeData);

            // 初期サイズを記録
            setTimeout(() => {
                if (!nodeData.width) {
                    nodeData.width = node.offsetWidth;
                }
                if (!nodeData.height) {
                    nodeData.height = node.offsetHeight;
                }
            }, 0);

            // イベントリスナー
            setupNodeEvents(nodeData);
            
            // ステータスオプションを更新
            updateStatusOptions(nodeData);

            return nodeData;
        }

        // ノードコンテンツ更新
        async function updateNodeContent(nodeData) {
            const contentDiv = nodeData.element.querySelector('.node-content');
            const result = await renderMarkdown(nodeData.content);
            contentDiv.innerHTML = result.html;
        }

        // ノードの見た目を更新
        function updateNodeAppearance(nodeData) {
            const node = nodeData.element;
            
            // ステータスによるノードクラスの更新
            node.classList.remove('status-起票', 'status-OK', 'status-条件付OK', 'status-NG', 'status-却下', 'status-保留');
            node.classList.add(`status-${nodeData.status}`);
        }

        // 先行ノードのステータスをチェック
        function checkPredecessorStatus(nodeData) {
            // このノードに接続している先行ノード（fromノード）を取得
            const predecessorConnections = connections.filter(conn => conn.to === nodeData.id);
            
            if (predecessorConnections.length === 0) {
                // 先行ノードがない場合は制約なし
                return true;
            }
            
            // すべての先行ノードがOK/条件付OK/却下/保留のいずれかかチェック
            const allPredecessorsOk = predecessorConnections.every(conn => {
                const predecessorNode = nodes.find(n => n.id === conn.from);
                return predecessorNode && (
                    predecessorNode.status === 'OK' || 
                    predecessorNode.status === '条件付OK' ||
                    predecessorNode.status === '却下' ||
                    predecessorNode.status === '保留'
                );
            });
            
            return allPredecessorsOk;
        }

        // ステータスのオプションを更新（制約に基づいて無効化）
        function updateStatusOptions(nodeData) {
            const statusSelect = nodeData.element.querySelector('.node-status');
            const canSetTestResult = checkPredecessorStatus(nodeData);
            
            // オプションを取得
            const options = statusSelect.querySelectorAll('option');
            
            options.forEach(option => {
                const value = option.value;
                
                if (value === 'OK' || value === '条件付OK' || value === 'NG') {
                    if (!canSetTestResult) {
                        option.disabled = true;
                        // 鍵アイコンを追加
                        if (!option.textContent.startsWith('🔒 ')) {
                            option.textContent = '🔒 ' + option.value;
                        }
                    } else {
                        option.disabled = false;
                        // 鍵アイコンを削除
                        option.textContent = option.value;
                    }
                } else {
                    option.disabled = false;
                    option.textContent = option.value;
                }
            });
            
            // 現在のステータスが無効化された場合、起票に戻す
            if (!canSetTestResult && (nodeData.status === 'OK' || nodeData.status === '条件付OK' || nodeData.status === 'NG')) {
                nodeData.status = '起票';
                statusSelect.value = '起票';
                statusSelect.className = 'node-status status-起票';
                updateNodeAppearance(nodeData);
            }
        }

        // すべてのノードのステータスオプションを更新
        function updateAllStatusOptions() {
            nodes.forEach(node => {
                updateStatusOptions(node);
            });
        }

        // ノードイベント設定
        function setupNodeEvents(nodeData) {
            const node = nodeData.element;
            let isDragging = false;
            let dragOffset = { x: 0, y: 0 };

            // テスト種別変更
            const testTypeSelect = node.querySelector('.test-type');
            testTypeSelect.addEventListener('change', (e) => {
                nodeData.testType = e.target.value;
                testTypeSelect.className = `test-type type-${e.target.value}`;
                saveToSessionStorage(); // sessionStorageに保存
            });

            // テストケースID編集
            const nodeIdInput = node.querySelector('.node-id');
            nodeIdInput.addEventListener('blur', () => {
                nodeData.testCaseId = nodeIdInput.textContent;
                saveToSessionStorage(); // sessionStorageに保存
            });

            nodeIdInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    nodeIdInput.blur();
                }
            });

            // ステータス変更
            const statusSelect = node.querySelector('.node-status');
            statusSelect.addEventListener('change', (e) => {
                const newStatus = e.target.value;
                
                // 制約チェック
                if ((newStatus === 'OK' || newStatus === '条件付OK' || newStatus === 'NG') && !checkPredecessorStatus(nodeData)) {
                    alert('先行のテストケースがOK/条件付OK/却下/保留のいずれかになっていないため、このステータスは選択できません。');
                    e.target.value = nodeData.status;
                    return;
                }
                
                nodeData.status = newStatus;
                statusSelect.className = `node-status status-${newStatus}`;
                updateNodeAppearance(nodeData);
                
                // このノードのステータスが変更されたら、後続ノードのステータスオプションを更新
                updateAllStatusOptions();
                
                // sessionStorageに保存
                saveToSessionStorage();
            });

            // ドラッグ開始（マウス）
            node.addEventListener('mousedown', (e) => {
                if (e.target.tagName === 'BUTTON' || 
                    e.target.tagName === 'TEXTAREA' || 
                    e.target.tagName === 'SELECT' || 
                    e.target.classList.contains('node-id') ||
                    e.target.classList.contains('connector') ||
                    e.target.classList.contains('resize-handle')) return;
                
                isDragging = true;
                node.classList.add('dragging');
                
                // ドラッグ開始時に現在の幅を固定
                const currentWidth = node.offsetWidth;
                node.style.width = currentWidth + 'px';
                
                dragOffset.x = e.clientX - nodeData.x;
                dragOffset.y = e.clientY - nodeData.y;
                e.stopPropagation();
            });

            // タッチ開始
            node.addEventListener('touchstart', (e) => {
                if (e.target.tagName === 'BUTTON' || 
                    e.target.tagName === 'TEXTAREA' || 
                    e.target.tagName === 'SELECT' || 
                    e.target.classList.contains('node-id') ||
                    e.target.classList.contains('connector') ||
                    e.target.classList.contains('resize-handle')) return;
                
                const touch = e.touches[0];
                touchStartTime = Date.now();
                touchMoved = false;
                
                // タッチ開始位置を記録
                nodeData.touchStartX = touch.clientX;
                nodeData.touchStartY = touch.clientY;
                nodeData.touchStartScrollTop = 0;
                nodeData.isDraggingNode = false;
                nodeData.isScrolling = false;
                
                // node-content内でのタッチかチェック
                const contentDiv = node.querySelector('.node-content');
                nodeData.isTouchOnContent = contentDiv.contains(e.target);
                
                // node-content内のスクロール位置を記録
                if (nodeData.isTouchOnContent) {
                    const monomdBody = contentDiv.querySelector('.monomd-body');
                    if (monomdBody) {
                        nodeData.touchStartScrollTop = monomdBody.scrollTop || 0;
                    }
                }
                
                dragOffset.x = touch.clientX - nodeData.x;
                dragOffset.y = touch.clientY - nodeData.y;
            }, { passive: false });

            // タッチ移動
            node.addEventListener('touchmove', (e) => {
                const touch = e.touches[0];
                const deltaX = Math.abs(touch.clientX - nodeData.touchStartX);
                const deltaY = Math.abs(touch.clientY - nodeData.touchStartY);
                
                // まだ方向が確定していない場合
                if (!nodeData.isDraggingNode && !nodeData.isScrolling) {
                    // 5px以上動いたら方向を判定
                    if (deltaX > 5 || deltaY > 5) {
                        if (nodeData.isTouchOnContent && deltaY > deltaX * 1.5) {
                            // node-content内で縦方向の動きが大きい場合はスクロール
                            nodeData.isScrolling = true;
                        } else {
                            // それ以外はドラッグ
                            nodeData.isDraggingNode = true;
                            isDragging = true;
                            node.classList.add('dragging');
                            
                            // ドラッグ開始時に現在の幅を固定
                            const currentWidth = node.offsetWidth;
                            node.style.width = currentWidth + 'px';
                        }
                    }
                }
                
                // ドラッグ中
                if (nodeData.isDraggingNode && isDragging) {
                    touchMoved = true;
                    nodeData.x = touch.clientX - dragOffset.x;
                    nodeData.y = touch.clientY - dragOffset.y;
                    node.style.left = nodeData.x + 'px';
                    node.style.top = nodeData.y + 'px';
                    updateConnections();
                    e.preventDefault();
                    e.stopPropagation();
                }
                // スクロール中はデフォルト動作を許可（preventDefault しない）
            }, { passive: false });

            // タッチ終了
            node.addEventListener('touchend', (e) => {
                if (isDragging) {
                    isDragging = false;
                    node.classList.remove('dragging');
                    
                    // ダブルタップ判定（編集モード用）
                    const touchDuration = Date.now() - touchStartTime;
                    if (!touchMoved && touchDuration < 300) {
                        // シングルタップの処理はここには書かない
                    }
                }
                
                // フラグをリセット
                nodeData.isDraggingNode = false;
                nodeData.isScrolling = false;
            });

            // マークダウン部分のダブルクリックで編集モードに
            const contentDiv = node.querySelector('.node-content');
            contentDiv.addEventListener('dblclick', () => {
                // 現在のノードのサイズを取得して固定
                const currentWidth = node.offsetWidth;
                const currentHeight = node.offsetHeight;
                
                // ノードのサイズを明示的に設定
                if (!nodeData.width || nodeData.width < currentWidth) {
                    nodeData.width = currentWidth;
                }
                if (!nodeData.height || nodeData.height < currentHeight) {
                    nodeData.height = currentHeight;
                }
                
                node.style.width = nodeData.width + 'px';
                node.style.height = nodeData.height + 'px';
                
                node.classList.add('editing');
                const textarea = node.querySelector('.node-textarea');
                textarea.focus();
            });

            // テキストエリア外クリックで保存
            const textarea = node.querySelector('.node-textarea');
            document.addEventListener('click', (e) => {
                if (node.classList.contains('editing')) {
                    // テキストエリアとその親要素以外をクリックした場合
                    if (!textarea.contains(e.target) && !node.contains(e.target)) {
                        nodeData.content = textarea.value;
                        updateNodeContent(nodeData);
                        node.classList.remove('editing');
                        saveToSessionStorage(); // sessionStorageに保存
                    } else if (node.contains(e.target) && !textarea.contains(e.target) && e.target.tagName !== 'TEXTAREA') {
                        // ノード内のテキストエリア以外をクリックした場合
                        nodeData.content = textarea.value;
                        updateNodeContent(nodeData);
                        node.classList.remove('editing');
                        saveToSessionStorage(); // sessionStorageに保存
                    }
                }
            });

            // リサイズハンドルのイベント
            const resizeHandles = node.querySelectorAll('.resize-handle');
            resizeHandles.forEach(handle => {
                let isResizing = false;
                let resizeStartX = 0;
                let resizeStartY = 0;
                let startWidth = 0;
                let startHeight = 0;
                let startX = 0;
                let startY = 0;

                // マウスダウン
                handle.addEventListener('mousedown', (e) => {
                    e.stopPropagation();
                    isResizing = true;
                    resizeStartX = e.clientX;
                    resizeStartY = e.clientY;
                    startWidth = node.offsetWidth;
                    startHeight = node.offsetHeight;
                    startX = nodeData.x;
                    startY = nodeData.y;
                    node.classList.add('resizing');

                    const handleMouseMove = (e) => {
                        if (!isResizing) return;

                        const deltaX = e.clientX - resizeStartX;
                        const deltaY = e.clientY - resizeStartY;

                        if (handle.classList.contains('right')) {
                            const newWidth = Math.max(200, startWidth + deltaX);
                            node.style.width = newWidth + 'px';
                            nodeData.width = newWidth;
                        } else if (handle.classList.contains('left')) {
                            const newWidth = Math.max(200, startWidth - deltaX);
                            if (newWidth > 200) {
                                node.style.width = newWidth + 'px';
                                nodeData.width = newWidth;
                                nodeData.x = startX + deltaX;
                                node.style.left = nodeData.x + 'px';
                            }
                        } else if (handle.classList.contains('bottom')) {
                            const newHeight = Math.max(100, startHeight + deltaY);
                            node.style.height = newHeight + 'px';
                            nodeData.height = newHeight;
                        } else if (handle.classList.contains('top')) {
                            const newHeight = Math.max(100, startHeight - deltaY);
                            if (newHeight > 100) {
                                node.style.height = newHeight + 'px';
                                nodeData.height = newHeight;
                                nodeData.y = startY + deltaY;
                                node.style.top = nodeData.y + 'px';
                            }
                        }

                        updateConnections();
                    };

                    const handleMouseUp = () => {
                        if (isResizing) {
                            isResizing = false;
                            node.classList.remove('resizing');
                            document.removeEventListener('mousemove', handleMouseMove);
                            document.removeEventListener('mouseup', handleMouseUp);
                        }
                    };

                    document.addEventListener('mousemove', handleMouseMove);
                    document.addEventListener('mouseup', handleMouseUp);
                });

                // タッチ開始
                handle.addEventListener('touchstart', (e) => {
                    e.stopPropagation();
                    const touch = e.touches[0];
                    isResizing = true;
                    resizeStartX = touch.clientX;
                    resizeStartY = touch.clientY;
                    startWidth = node.offsetWidth;
                    startHeight = node.offsetHeight;
                    startX = nodeData.x;
                    startY = nodeData.y;
                    node.classList.add('resizing');
                }, { passive: false });

                // タッチ移動
                handle.addEventListener('touchmove', (e) => {
                    if (!isResizing) return;
                    
                    const touch = e.touches[0];
                    const deltaX = touch.clientX - resizeStartX;
                    const deltaY = touch.clientY - resizeStartY;

                    if (handle.classList.contains('right')) {
                        const newWidth = Math.max(200, startWidth + deltaX);
                        node.style.width = newWidth + 'px';
                        nodeData.width = newWidth;
                    } else if (handle.classList.contains('left')) {
                        const newWidth = Math.max(200, startWidth - deltaX);
                        if (newWidth > 200) {
                            node.style.width = newWidth + 'px';
                            nodeData.width = newWidth;
                            nodeData.x = startX + deltaX;
                            node.style.left = nodeData.x + 'px';
                        }
                    } else if (handle.classList.contains('bottom')) {
                        const newHeight = Math.max(100, startHeight + deltaY);
                        node.style.height = newHeight + 'px';
                        nodeData.height = newHeight;
                    } else if (handle.classList.contains('top')) {
                        const newHeight = Math.max(100, startHeight - deltaY);
                        if (newHeight > 100) {
                            node.style.height = newHeight + 'px';
                            nodeData.height = newHeight;
                            nodeData.y = startY + deltaY;
                            node.style.top = nodeData.y + 'px';
                        }
                    }

                    updateConnections();
                    e.preventDefault();
                }, { passive: false });

                // タッチ終了
                handle.addEventListener('touchend', () => {
                    if (isResizing) {
                        isResizing = false;
                        node.classList.remove('resizing');
                    }
                });
            });

            // ノードの右クリックメニュー
            node.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                selectedNode = nodeData;
                selectedConnection = null;
                contextMenu.style.left = e.clientX + 'px';
                contextMenu.style.top = e.clientY + 'px';
                contextMenu.classList.add('show');
                
                // メニュー項目の表示/非表示
                deleteNodeBtn.style.display = 'block';
                deleteConnectionBtn.style.display = 'none';
            });

            // コネクターのクリックイベント
            const connectors = node.querySelectorAll('.connector');
            connectors.forEach(connector => {
                connector.addEventListener('click', (e) => {
                    e.stopPropagation();
                    handleConnectorClick(nodeData, connector);
                });
            });

            // マウス移動
            document.addEventListener('mousemove', (e) => {
                if (isDragging) {
                    nodeData.x = e.clientX - dragOffset.x;
                    nodeData.y = e.clientY - dragOffset.y;
                    node.style.left = nodeData.x + 'px';
                    node.style.top = nodeData.y + 'px';
                    updateConnections();
                }
            });

            // ドラッグ終了
            document.addEventListener('mouseup', () => {
                if (isDragging) {
                    isDragging = false;
                    node.classList.remove('dragging');
                }
            });

            // ノード内の画像クリックで拡大表示
            node.addEventListener('click', (e) => {
                if (e.target.tagName === 'IMG' && e.target.closest('.node-content')) {
                    e.stopPropagation();
                    imageModalImg.src = e.target.src;
                    imageModalImg.alt = e.target.alt;
                    imageModal.classList.add('show');
                }
            });
        }

        // すべてのノードをクリア
        function clearAllNodes() {
            nodes.forEach(n => n.element.remove());
            nodes = [];
            connections = [];
            updateConnections();
            updateAllStatusOptions();
            saveToSessionStorage();
        }

        // ノード削除
        function deleteNode(nodeData) {
            nodeData.element.remove();
            nodes = nodes.filter(n => n.id !== nodeData.id);
            connections = connections.filter(c => c.from !== nodeData.id && c.to !== nodeData.id);
            updateConnections();
            updateAllStatusOptions();
            saveToSessionStorage();
        }

        // 接続作成
        function createConnection(fromNodeId, toNodeId, fromDirection, toDirection) {
            connections.push({ 
                from: fromNodeId, 
                to: toNodeId,
                fromDirection: fromDirection || 'center',
                toDirection: toDirection || 'center'
            });
            updateConnections();
            
            // 接続が作成されたら、すべてのノードのステータスオプションを更新
            updateAllStatusOptions();
        }

        // コネクタークリック処理
        function handleConnectorClick(nodeData, connector) {
            const direction = connector.dataset.direction;
            
            if (!connectingFrom) {
                // 接続開始
                connectingFrom = {
                    node: nodeData,
                    direction: direction,
                    connector: connector
                };
                connector.classList.add('active');
            } else {
                // 接続完了
                if (connectingFrom.node.id !== nodeData.id) {
                    createConnection(
                        connectingFrom.node.id, 
                        nodeData.id,
                        connectingFrom.direction,
                        direction
                    );
                }
                // アクティブ状態を解除
                const activeConnectors = document.querySelectorAll('.connector.active');
                activeConnectors.forEach(c => c.classList.remove('active'));
                connectingFrom = null;
            }
        }

        // TSVエスケープ関数（バックスラッシュでエスケープ）
        function escapeTsv(value) {
            if (value == null) return '';
            const stringValue = String(value);
            // バックスラッシュ、タブ、改行、キャリッジリターンをエスケープ
            return stringValue
                .replace(/\\/g, '\\\\')  // バックスラッシュ
                .replace(/\t/g, '\\t')   // タブ
                .replace(/\n/g, '\\n')   // 改行
                .replace(/\r/g, '\\r');  // キャリッジリターン
        }

        // TSV形式でエクスポート
        function exportToTsv() {
            // テストケースIDの重複チェック
            const duplicates = checkDuplicateTestCaseIds();
            if (duplicates.length > 0) {
                alert('重複のテストケースIDがあります。一意の値を登録してください。\n重複ID: ' + duplicates.join(', '));
                return;
            }

            // ヘッダー行（英語）
            const headers = [
                'unique_id',
                'test_case_id',
                'test_type',
                'status',
                'markdown_content',
                'height',
                'width',
                'x_position',
                'y_position',
                'connected_node_ids'
            ];

            let tsvContent = headers.join('\t') + '\n';

            // データ行
            nodes.forEach(node => {
                // 接続先のノードIDリストを取得（方向情報付き）
                const connectedToNodeIds = connections
                    .filter(conn => conn.from === node.id)
                    .map(conn => {
                        const targetNode = nodes.find(n => n.id === conn.to);
                        return targetNode ? {
                            direction: 'to',
                            node_id: targetNode.uniqueId,
                            connect_point: conn.fromDirection || 'center'
                        } : null;
                    })
                    .filter(conn => conn !== null);

                // 接続元のノードIDリストも取得
                const connectedFromNodeIds = connections
                    .filter(conn => conn.to === node.id)
                    .map(conn => {
                        const sourceNode = nodes.find(n => n.id === conn.from);
                        return sourceNode ? {
                            direction: 'from',
                            node_id: sourceNode.uniqueId,
                            connect_point: conn.toDirection || 'center'
                        } : null;
                    })
                    .filter(conn => conn !== null);

                // 両方を結合してJSON文字列化
                const allConnections = [...connectedToNodeIds, ...connectedFromNodeIds];
                const connectionsJson = JSON.stringify(allConnections);

                const row = [
                    escapeTsv(node.uniqueId),
                    escapeTsv(node.testCaseId.trim()),
                    escapeTsv(node.testType),
                    escapeTsv(node.status),
                    escapeTsv(node.content),
                    escapeTsv(node.height || node.element.offsetHeight),
                    escapeTsv(node.width || node.element.offsetWidth),
                    escapeTsv(node.x),
                    escapeTsv(node.y),
                    escapeTsv(connectionsJson)
                ];

                tsvContent += row.join('\t') + '\n';
            });

            // ダウンロード
            const blob = new Blob([tsvContent], { type: 'text/tab-separated-values;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
            link.setAttribute('href', url);
            link.setAttribute('download', `test_mindmap_${timestamp}.tsv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        // JSON形式でエクスポート
        // JSONデータを生成
        function generateJsonData() {
            const exportData = {
                export_date: new Date().toISOString(),
                version: '1.0',
                nodes: nodes.map(node => {
                    // 接続先のノードIDリストを取得（方向情報付き）
                    const connectedToNodeIds = connections
                        .filter(conn => conn.from === node.id)
                        .map(conn => {
                            const targetNode = nodes.find(n => n.id === conn.to);
                            return targetNode ? {
                                direction: 'to',
                                node_id: targetNode.uniqueId,
                                connect_point: conn.fromDirection || 'center'
                            } : null;
                        })
                        .filter(conn => conn !== null);

                    // 接続元のノードIDリストも取得
                    const connectedFromNodeIds = connections
                        .filter(conn => conn.to === node.id)
                        .map(conn => {
                            const sourceNode = nodes.find(n => n.id === conn.from);
                            return sourceNode ? {
                                direction: 'from',
                                node_id: sourceNode.uniqueId,
                                connect_point: conn.toDirection || 'center'
                            } : null;
                        })
                        .filter(conn => conn !== null);

                    // 両方を結合
                    const allConnections = [...connectedToNodeIds, ...connectedFromNodeIds];

                    return {
                        unique_id: node.uniqueId,
                        test_case_id: node.testCaseId.trim(),
                        test_type: node.testType,
                        status: node.status,
                        markdown_content: node.content,
                        height: node.height || node.element.offsetHeight,
                        width: node.width || node.element.offsetWidth,
                        x_position: node.x,
                        y_position: node.y,
                        connected_node_ids: allConnections
                    };
                })
            };
            return exportData;
        }

        // sessionStorageに保存
        function saveToSessionStorage() {
            try {
                const data = generateJsonData();
                const jsonString = JSON.stringify(data);
                sessionStorage.setItem('mindmap_data', jsonString);
            } catch (e) {
                console.error('sessionStorageへの保存に失敗しました:', e);
            }
        }

        // sessionStorageから読み込み
        async function loadFromSessionStorage() {
            try {
                const jsonString = sessionStorage.getItem('mindmap_data');
                if (jsonString) {
                    const data = JSON.parse(jsonString);
                    await importFromJsonData(data);
                    return true;
                }
            } catch (e) {
                console.error('sessionStorageからの読み込みに失敗しました:', e);
            }
            return false;
        }

        function exportToJson() {
            // テストケースIDの重複チェック
            const duplicates = checkDuplicateTestCaseIds();
            if (duplicates.length > 0) {
                alert('重複のテストケースIDがあります。一意の値を登録してください。\n重複ID: ' + duplicates.join(', '));
                return;
            }

            const exportData = generateJsonData();

            // JSON文字列に変換（整形あり）
            const jsonContent = JSON.stringify(exportData, null, 2);

            // ダウンロード
            const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
            link.setAttribute('href', url);
            link.setAttribute('download', `test_mindmap_${timestamp}.json`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        // SVG形式でエクスポート

        // テストケースIDの重複チェック
        function checkDuplicateTestCaseIds() {
            const testCaseIds = nodes.map(node => node.testCaseId.trim());
            const uniqueIds = new Set();
            const duplicates = [];

            testCaseIds.forEach(id => {
                if (uniqueIds.has(id)) {
                    if (!duplicates.includes(id)) {
                        duplicates.push(id);
                    }
                } else {
                    uniqueIds.add(id);
                }
            });

            return duplicates;
        }

        // TSVパース関数（バックスラッシュエスケープに対応）
        function parseTsv(text) {
            const lines = text.split('\n').filter(line => line.trim() !== '');
            
            return lines.map(line => {
                const fields = [];
                let currentField = '';
                let i = 0;
                
                while (i < line.length) {
                    const char = line[i];
                    
                    if (char === '\\' && i + 1 < line.length) {
                        // エスケープシーケンス処理
                        const nextChar = line[i + 1];
                        if (nextChar === '\\') {
                            currentField += '\\';
                        } else if (nextChar === 't') {
                            currentField += '\t';
                        } else if (nextChar === 'n') {
                            currentField += '\n';
                        } else if (nextChar === 'r') {
                            currentField += '\r';
                        } else {
                            currentField += nextChar;
                        }
                        i += 2;
                    } else if (char === '\t') {
                        // タブでフィールド区切り
                        fields.push(currentField);
                        currentField = '';
                        i++;
                    } else {
                        currentField += char;
                        i++;
                    }
                }
                
                // 最後のフィールドを追加
                fields.push(currentField);
                
                return fields;
            });
        }

        // インポート関数
        // JSONデータからインポート
        async function importFromJsonData(jsonData) {
            const importData = jsonData.nodes || [];
            
            // 既存のノードと接続をクリア
            nodes.forEach(n => n.element.remove());
            nodes = [];
            connections = [];
            nodeIdCounter = 0;
            
            // uniqueIdからnodeIdへのマッピング
            const uniqueIdToNodeId = new Map();
            
            // ノードを再作成
            for (const nodeInfo of importData) {
                const x = parseFloat(nodeInfo.x_position) || Math.random() * 600 + 100;
                const y = parseFloat(nodeInfo.y_position) || Math.random() * 400 + 100;
                const content = nodeInfo.markdown_content || '';
                
                const newNode = await createNode(x, y, content);
                
                // ノードデータを復元
                newNode.uniqueId = nodeInfo.unique_id;
                newNode.testCaseId = nodeInfo.test_case_id;
                newNode.testType = nodeInfo.test_type || '正常系';
                newNode.status = nodeInfo.status || '起票';
                newNode.width = parseFloat(nodeInfo.width) || null;
                newNode.height = parseFloat(nodeInfo.height) || null;
                
                // サイズを設定
                if (newNode.width) {
                    newNode.element.style.width = newNode.width + 'px';
                }
                if (newNode.height) {
                    newNode.element.style.height = newNode.height + 'px';
                }
                
                // UIを更新
                const nodeIdInput = newNode.element.querySelector('.node-id');
                nodeIdInput.textContent = newNode.testCaseId;
                
                const testTypeSelect = newNode.element.querySelector('.test-type');
                testTypeSelect.value = newNode.testType;
                testTypeSelect.className = `test-type type-${newNode.testType}`;
                
                const statusSelect = newNode.element.querySelector('.node-status');
                statusSelect.value = newNode.status;
                statusSelect.className = `node-status status-${newNode.status}`;
                updateNodeAppearance(newNode);
                
                // マッピングを保存
                uniqueIdToNodeId.set(nodeInfo.unique_id, newNode.id);
            }
            
            // 接続を再作成
            importData.forEach(nodeInfo => {
                const currentNode = nodes.find(n => n.uniqueId === nodeInfo.unique_id);
                if (!currentNode) return;
                
                // connected_node_idsを配列として取得（文字列の場合はパース）
                let connectedNodeIds = nodeInfo.connected_node_ids || [];
                if (typeof connectedNodeIds === 'string') {
                    try {
                        connectedNodeIds = JSON.parse(connectedNodeIds);
                    } catch (e) {
                        console.error('Failed to parse connected_node_ids:', e);
                        connectedNodeIds = [];
                    }
                }
                
                connectedNodeIds.forEach(connInfo => {
                    if (connInfo.direction === 'to') {
                        const targetNodeId = uniqueIdToNodeId.get(connInfo.node_id);
                        if (targetNodeId) {
                            const fromDirection = connInfo.connect_point || 'center';
                            
                            // 接続先ノードのデータから接続点を取得
                            const targetNodeInfo = importData.find(n => n.unique_id === connInfo.node_id);
                            let toDirection = 'center';
                            
                            if (targetNodeInfo) {
                                let targetConnections = targetNodeInfo.connected_node_ids || [];
                                if (typeof targetConnections === 'string') {
                                    try {
                                        targetConnections = JSON.parse(targetConnections);
                                    } catch (e) {
                                        targetConnections = [];
                                    }
                                }
                                
                                // 相手ノードから自分へのfrom接続を探す
                                const reverseConn = targetConnections.find(
                                    c => c.direction === 'from' && c.node_id === nodeInfo.unique_id
                                );
                                if (reverseConn) {
                                    toDirection = reverseConn.connect_point || 'center';
                                }
                            }
                            
                            createConnection(currentNode.id, targetNodeId, fromDirection, toDirection);
                        }
                    }
                });
            });
            
            updateAllStatusOptions();
        }

        async function importFromTsvText(text) {
            const tsvLines = parseTsv(text);
            if (!tsvLines || tsvLines.length < 2) return;
            const headers = tsvLines[0];
            const importData = tsvLines.slice(1).map(row => {
                const obj = {};
                headers.forEach((header, index) => {
                    obj[header] = row[index] || '';
                });
                return obj;
            });
            await importFromJsonData({ nodes: importData });
        }

        function importFromFile(file) {
            const reader = new FileReader();
            
            reader.onload = async function(e) {
                const content = e.target.result;
                const fileName = file.name.toLowerCase();
                
                try {
                    if (fileName.endsWith('.json')) {
                        // JSON形式のインポート
                        const jsonData = JSON.parse(content);
                        await importFromJsonData(jsonData);
                    } else if (fileName.endsWith('.tsv')) {
                        // TSV形式のインポート
                        const tsvLines = parseTsv(content);
                        const headers = tsvLines[0];
                        const importData = tsvLines.slice(1).map(row => {
                            const obj = {};
                            headers.forEach((header, index) => {
                                obj[header] = row[index] || '';
                            });
                            return obj;
                        });
                        
                        // TSVデータをJSON形式に変換してimport
                        await importFromJsonData({ nodes: importData });
                    } else {
                        alert('サポートされていないファイル形式です。TSVまたはJSONファイルを選択してください。');
                        return;
                    }
                    
                    alert('インポートが完了しました。');
                    
                } catch (error) {
                    console.error('Import error:', error);
                    alert('ファイルの読み込みに失敗しました。ファイル形式を確認してください。\nエラー: ' + error.message);
                }
            };
            
            reader.readAsText(file);
        }

        // 接続更新
        function updateConnections() {
            svg.innerHTML = '<defs><marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><polygon points="0 0, 10 3, 0 6" fill="white" /></marker></defs>';
            
            connections.forEach((conn, index) => {
                const fromNode = nodes.find(n => n.id === conn.from);
                const toNode = nodes.find(n => n.id === conn.to);
                
                if (fromNode && toNode) {
                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    
                    // コネクターの位置を計算
                    const fromPos = getConnectorPosition(fromNode, conn.fromDirection || 'center');
                    const toPos = getConnectorPosition(toNode, conn.toDirection || 'center');
                    
                    line.setAttribute('x1', fromPos.x);
                    line.setAttribute('y1', fromPos.y);
                    line.setAttribute('x2', toPos.x);
                    line.setAttribute('y2', toPos.y);
                    line.classList.add('connection');
                    line.dataset.connectionIndex = index;
                    
                    // 右クリックイベント
                    line.addEventListener('contextmenu', (e) => {
                        e.preventDefault();
                        selectedConnection = index;
                        selectedNode = null;
                        contextMenu.style.left = e.clientX + 'px';
                        contextMenu.style.top = e.clientY + 'px';
                        contextMenu.classList.add('show');
                        
                        // メニュー項目の表示/非表示
                        deleteNodeBtn.style.display = 'none';
                        deleteConnectionBtn.style.display = 'block';
                    });
                    
                    svg.appendChild(line);
                }
            });
            
            // sessionStorageに保存
            saveToSessionStorage();
        }

        // コネクターの位置を取得
        function getConnectorPosition(nodeData, direction) {
            const rect = nodeData.element.getBoundingClientRect();
            const nodeWidth = nodeData.width || rect.width;
            const nodeHeight = nodeData.height || rect.height;
            
            let x, y;
            
            switch(direction) {
                case 'top':
                    x = nodeData.x + nodeWidth / 2;
                    y = nodeData.y;
                    break;
                case 'bottom':
                    x = nodeData.x + nodeWidth / 2;
                    y = nodeData.y + nodeHeight;
                    break;
                case 'left':
                    x = nodeData.x;
                    y = nodeData.y + nodeHeight / 2;
                    break;
                case 'right':
                    x = nodeData.x + nodeWidth;
                    y = nodeData.y + nodeHeight / 2;
                    break;
                default: // center
                    x = nodeData.x + nodeWidth / 2;
                    y = nodeData.y + nodeHeight / 2;
                    break;
            }
            
            return { x, y };
        }

        // ツールバーイベント
        addNodeBtn.addEventListener('click', async () => {
            await createNode(Math.random() * 600 + 100, Math.random() * 400 + 100);
        });

        importBtn.addEventListener('click', () => {
            if (vscode) {
                vscode.postMessage({ type: 'requestImport' });
            } else {
                fileInput.click();
            }
        });

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                importFromFile(file);
            }
            // ファイル入力をリセット（同じファイルを再度選択できるように）
            fileInput.value = '';
        });

        exportBtn.addEventListener('click', () => {
            exportModal.classList.add('show');
        });

        exportModalCloseBtn.addEventListener('click', () => {
            exportModal.classList.remove('show');
        });

        // モーダルオーバーレイクリックで閉じる
        exportModal.addEventListener('click', (e) => {
            if (e.target === exportModal) {
                exportModal.classList.remove('show');
            }
        });

        exportTsvBtn.addEventListener('click', () => {
            exportToTsv();
            exportModal.classList.remove('show');
        });

        exportJsonBtn.addEventListener('click', () => {
            exportToJson();
            exportModal.classList.remove('show');
        });

        clearBtn.addEventListener('click', () => {
            if (vscode) {
                vscode.postMessage({ type: 'confirmClear' });
            } else {
                if (confirm('本当に削除しますか？')) {
                    clearAllNodes();
                }
            }
        });

        // 右クリックメニューのノード削除
        deleteNodeBtn.addEventListener('click', () => {
            if (selectedNode !== null) {
                if (vscode) {
                    vscode.postMessage({
                        type: 'confirmDeleteNode',
                        nodeId: selectedNode.id,
                        testCaseId: selectedNode.testCaseId
                    });
                    contextMenu.classList.remove('show');
                } else {
                    if (confirm('本当に削除しますか？')) {
                        deleteNode(selectedNode);
                        contextMenu.classList.remove('show');
                        selectedNode = null;
                    }
                }
            }
        });

        // 右クリックメニューの接続削除
        deleteConnectionBtn.addEventListener('click', () => {
            if (selectedConnection !== null) {
                connections.splice(selectedConnection, 1);
                updateConnections();
                contextMenu.classList.remove('show');
                selectedConnection = null;
                
                // 接続が削除されたら、すべてのノードのステータスオプションを更新
                updateAllStatusOptions();
                saveToSessionStorage();
            }
        });

        // 右クリックメニューを閉じる
        document.addEventListener('click', (e) => {
            if (!contextMenu.contains(e.target)) {
                contextMenu.classList.remove('show');
            }
        });

        // 操作方法モーダルの開閉
        helpBtn.addEventListener('click', () => {
            helpModal.classList.add('show');
        });

        helpBtnMobile.addEventListener('click', () => {
            helpModal.classList.add('show');
            hamburgerMenu.classList.remove('open');
            menuOverlay.classList.remove('show');
            hamburgerBtn.innerHTML = '<i class="fas fa-bars"></i> メニュー';
        });

        modalCloseBtn.addEventListener('click', () => {
            helpModal.classList.remove('show');
        });

        // モーダルオーバーレイクリックで閉じる
        helpModal.addEventListener('click', (e) => {
            if (e.target === helpModal) {
                helpModal.classList.remove('show');
            }
        });

        // 画像モーダルの開閉
        imageModalCloseBtn.addEventListener('click', () => {
            imageModal.classList.remove('show');
        });

        // 画像モーダルのオーバーレイクリックで閉じる
        imageModal.addEventListener('click', (e) => {
            if (e.target === imageModal || e.target === imageModalCloseBtn) {
                imageModal.classList.remove('show');
            }
        });

        // 右クリックメニューが表示されている時にスクロールやリサイズで閉じる
        window.addEventListener('scroll', () => {
            contextMenu.classList.remove('show');
            exportMenu.classList.remove('show');
        });

        window.addEventListener('resize', () => {
            contextMenu.classList.remove('show');
            exportMenu.classList.remove('show');
        });

        // キャンバスドラッグ（マウス）
        canvas.addEventListener('mousedown', (e) => {
            if (e.target === canvas || e.target === canvasContent || e.target === svg) {
                isDraggingCanvas = true;
                canvas.classList.add('grabbing');
                dragStart.x = e.clientX;
                dragStart.y = e.clientY;
                
                // 全ノードの幅を固定してリサイズを防止
                nodes.forEach(nodeData => {
                    const currentWidth = nodeData.element.offsetWidth;
                    nodeData.element.style.width = currentWidth + 'px';
                    nodeData.element.classList.add('dragging');
                });
            }
        });

        // キャンバスタッチ開始
        canvas.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                // 2本指でのタッチ開始 - ピンチズーム
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                lastTouchDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );
            } else if (e.touches.length === 1 && (e.target === canvas || e.target === canvasContent || e.target === svg)) {
                // 1本指でのタッチ - キャンバス移動
                const touch = e.touches[0];
                isDraggingCanvas = true;
                canvas.classList.add('grabbing');
                dragStart.x = touch.clientX;
                dragStart.y = touch.clientY;
                
                // 全ノードの幅を固定してリサイズを防止
                nodes.forEach(nodeData => {
                    const currentWidth = nodeData.element.offsetWidth;
                    nodeData.element.style.width = currentWidth + 'px';
                    nodeData.element.classList.add('dragging');
                });
            }
        }, { passive: true });

        // マウス移動
        document.addEventListener('mousemove', (e) => {
            if (isDraggingCanvas) {
                const dx = e.clientX - dragStart.x;
                const dy = e.clientY - dragStart.y;
                
                nodes.forEach(nodeData => {
                    nodeData.x += dx;
                    nodeData.y += dy;
                    nodeData.element.style.left = nodeData.x + 'px';
                    nodeData.element.style.top = nodeData.y + 'px';
                });
                
                updateConnections();
                dragStart.x = e.clientX;
                dragStart.y = e.clientY;
            }
        });

        // タッチ移動
        document.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2) {
                // 2本指でのピンチズーム
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                const currentDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );
                
                if (lastTouchDistance > 0) {
                    const scale = currentDistance / lastTouchDistance;
                    currentScale *= scale;
                    
                    // スケールの制限（0.5倍〜3倍）
                    currentScale = Math.max(0.5, Math.min(3, currentScale));
                    
                    // canvas-contentにスケールを適用（canvasのサイズは維持）
                    canvasContent.style.transform = `scale(${currentScale})`;
                    
                    // スケールをsessionStorageに保存
                    try {
                        sessionStorage.setItem('mindmap_scale', currentScale.toString());
                    } catch (e) {
                        console.error('スケールの保存に失敗:', e);
                    }
                }
                
                lastTouchDistance = currentDistance;
                e.preventDefault();
            } else if (isDraggingCanvas && e.touches.length === 1) {
                // 1本指でのキャンバス移動
                const touch = e.touches[0];
                const dx = touch.clientX - dragStart.x;
                const dy = touch.clientY - dragStart.y;
                
                nodes.forEach(nodeData => {
                    nodeData.x += dx;
                    nodeData.y += dy;
                    nodeData.element.style.left = nodeData.x + 'px';
                    nodeData.element.style.top = nodeData.y + 'px';
                });
                
                updateConnections();
                dragStart.x = touch.clientX;
                dragStart.y = touch.clientY;
                e.preventDefault();
            }
        }, { passive: false });

        // マウスアップ
        document.addEventListener('mouseup', () => {
            if (isDraggingCanvas) {
                // 全ノードのdraggingクラスを削除
                nodes.forEach(nodeData => {
                    nodeData.element.classList.remove('dragging');
                });
            }
            isDraggingCanvas = false;
            canvas.classList.remove('grabbing');
        });

        // タッチ終了
        document.addEventListener('touchend', (e) => {
            if (e.touches.length < 2) {
                lastTouchDistance = 0;
            }
            if (e.touches.length === 0) {
                if (isDraggingCanvas) {
                    // 全ノードのdraggingクラスを削除
                    nodes.forEach(nodeData => {
                        nodeData.element.classList.remove('dragging');
                    });
                }
                isDraggingCanvas = false;
                canvas.classList.remove('grabbing');
            }
        });

        // ハンバーガーメニューの開閉
        hamburgerBtn.addEventListener('click', () => {
            const isOpen = hamburgerMenu.classList.contains('open');
            
            if (isOpen) {
                // メニューを閉じる
                hamburgerMenu.classList.remove('open');
                menuOverlay.classList.remove('show');
                hamburgerBtn.innerHTML = '<i class="fas fa-bars"></i> メニュー';
            } else {
                // メニューを開く
                hamburgerMenu.classList.add('open');
                menuOverlay.classList.add('show');
                hamburgerBtn.innerHTML = '<i class="fas fa-xmark"></i> 閉じる';
            }
        });

        menuOverlay.addEventListener('click', () => {
            hamburgerMenu.classList.remove('open');
            menuOverlay.classList.remove('show');
            hamburgerBtn.innerHTML = '<i class="fas fa-bars"></i> メニュー';
        });

        // モバイルメニューのボタンイベント
        addNodeBtnMobile.addEventListener('click', async () => {
            await createNode(Math.random() * 600 + 100, Math.random() * 400 + 100);
            hamburgerMenu.classList.remove('open');
            menuOverlay.classList.remove('show');
            hamburgerBtn.innerHTML = '<i class="fas fa-bars"></i> メニュー';
        });

        clearBtnMobile.addEventListener('click', () => {
            if (vscode) {
                vscode.postMessage({ type: 'confirmClear' });
            } else {
                if (confirm('本当に削除しますか？')) {
                    clearAllNodes();
                }
            }
            hamburgerMenu.classList.remove('open');
            menuOverlay.classList.remove('show');
            hamburgerBtn.innerHTML = '<i class="fas fa-bars"></i> メニュー';
        });

        importBtnMobile.addEventListener('click', () => {
            fileInput.click();
            hamburgerMenu.classList.remove('open');
            menuOverlay.classList.remove('show');
            hamburgerBtn.innerHTML = '<i class="fas fa-bars"></i> メニュー';
        });

        exportBtnMobile.addEventListener('click', () => {
            exportModal.classList.add('show');
            hamburgerMenu.classList.remove('open');
            menuOverlay.classList.remove('show');
            hamburgerBtn.innerHTML = '<i class="fas fa-bars"></i> メニュー';
        });

        async function initDefaultNodes() {
            nodes.forEach(n => n.element.remove());
            nodes = [];
            connections = [];
            nodeIdCounter = 0;
            
            const node1 = await createNode(200, 150, '# ログイン機能テスト\n\n## 前提条件\n- ユーザーが登録済み\n- ログイン画面が表示されている\n\n## テスト手順\n1. ユーザーIDを入力\n2. パスワードを入力\n3. ログインボタンをクリック\n\n## 期待結果\nホーム画面が表示される');
            const node2 = await createNode(550, 100, '# 正常系テスト\n\n## 手順\n- 有効なID/PWを入力\n\n## 結果\n**成功**してログインできる');
            const node3 = await createNode(550, 300, '# 異常系テスト\n\n## 手順\n- 無効なPWを入力\n\n## 結果\n`エラーメッセージ`が表示される');
            
            node2.testType = '正常系';
            node2.element.querySelector('.test-type').value = '正常系';
            node2.element.querySelector('.test-type').className = 'test-type type-正常系';
            
            node3.testType = '異常系';
            node3.element.querySelector('.test-type').value = '異常系';
            node3.element.querySelector('.test-type').className = 'test-type type-異常系';
            
            createConnection(node1.id, node2.id, 'right', 'left');
            createConnection(node1.id, node3.id, 'right', 'left');
        }

        // VS Codeからのメッセージリスナー
        window.addEventListener('message', async (event) => {
            const message = event.data;
            switch (message.type) {
                case 'load':
                    isImporting = true;
                    try {
                        const text = message.text || '';
                        if (!text.trim()) {
                            await initDefaultNodes();
                        } else {
                            try {
                                const jsonData = JSON.parse(text);
                                await importFromJsonData(jsonData);
                            } catch (e) {
                                await importFromTsvText(text);
                            }
                        }
                    } catch (err) {
                        console.error('Error loading content:', err);
                    } finally {
                        isImporting = false;
                    }
                    break;
                case 'importedData':
                    isImporting = true;
                    try {
                        if (message.format === 'json') {
                            await importFromJsonData(JSON.parse(message.text));
                        } else {
                            await importFromTsvText(message.text);
                        }
                        saveToSessionStorage();
                    } catch (err) {
                        console.error('Error importing data:', err);
                        if (vscode) {
                            vscode.postMessage({ type: 'error', text: 'インポートに失敗しました: ' + err.message });
                        }
                    } finally {
                        isImporting = false;
                    }
                    break;
                case 'doClear':
                    clearAllNodes();
                    break;
                case 'doDeleteNode': {
                    const target = nodes.find(n => n.id === message.nodeId);
                    if (target) {
                        deleteNode(target);
                    }
                    break;
                }
            }
        });

        // ページロード時の初期化
        (async () => {
            // ズームスケールの復元
            try {
                const savedScale = sessionStorage.getItem('mindmap_scale');
                if (savedScale) {
                    currentScale = parseFloat(savedScale);
                    currentScale = Math.max(0.5, Math.min(3, currentScale));
                    canvasContent.style.transform = `scale(${currentScale})`;
                }
            } catch (e) {
                console.error('スケールの復元に失敗:', e);
            }
            
            if (vscode) {
                vscode.postMessage({ type: 'ready' });
            } else {
                const loadedFromStorage = await loadFromSessionStorage();
                if (!loadedFromStorage) {
                    await initDefaultNodes();
                }
            }
        })();
