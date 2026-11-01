// popup.js - Scheduled Clicker Popup Logic

document.addEventListener('DOMContentLoaded', async () => {
  const btnPickElement = document.getElementById('btnPickElement');
  const selectedElementBox = document.getElementById('selectedElementBox');
  const targetText = document.getElementById('targetText');
  const targetSelector = document.getElementById('targetSelector');
  const targetUrl = document.getElementById('targetUrl');
  const btnTestClick = document.getElementById('btnTestClick');

  const detectedAlert = document.getElementById('detectedAlert');
  const detectedMsg = document.getElementById('detectedMsg');
  const btnApplyDetected = document.getElementById('btnApplyDetected');

  const datetimeInput = document.getElementById('datetimeInput');
  const btnSchedule = document.getElementById('btnSchedule');
  const taskList = document.getElementById('taskList');
  const taskCount = document.getElementById('taskCount');

  let currentTarget = null;
  let detectedTimeData = null;

  // 1. アクティブなタブを取得
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // 2. 現在タブに content.js を確実に入れておく
  if (activeTab && activeTab.id && !activeTab.url.startsWith('chrome://')) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        files: ['content.js']
      });

      // ページ内の回復テキスト自動スキャン
      chrome.tabs.sendMessage(activeTab.id, { action: 'DETECT_RECOVERY' }, (res) => {
        if (chrome.runtime.lastError) return;
        if (res && res.detected) {
          detectedTimeData = res.detected;
          detectedMsg.textContent = `検出: ${res.detected.matchedText}`;
          detectedAlert.classList.remove('hidden');
        }
      });
    } catch (e) {
      console.warn('Script inject error:', e);
    }
  }

  // 3. ストレージから前回の選択要素とタスク一覧を読み込み
  const storageData = await chrome.storage.local.get(['lastPickedElement', 'scheduled_clicker_tasks']);
  if (storageData.lastPickedElement) {
    // アクティブタブと同じURLまたは直近選択した要素を表示
    setCurrentTarget(storageData.lastPickedElement);
  }

  renderTasks(storageData.scheduled_clicker_tasks || []);

  // 選択要素の反映関数
  function setCurrentTarget(elem) {
    currentTarget = elem;
    targetText.textContent = elem.innerText || '(テキストなし)';
    targetSelector.textContent = elem.selector || elem.xpath || '-';
    targetUrl.textContent = elem.url || '-';
    selectedElementBox.classList.remove('hidden');
    checkScheduleReady();
  }

  // スケジュールボタンの有効化チェック
  function checkScheduleReady() {
    const hasTarget = !!currentTarget;
    const hasTime = !!datetimeInput.value;
    btnSchedule.disabled = !(hasTarget && hasTime);
  }

  // 日時ピッカーの初期値（デフォルトは現在時刻+5分）
  function setDefaultDateTime(addMinutes = 5) {
    const now = new Date(Date.now() + addMinutes * 60 * 1000);
    const localIso = new Date(now.getTime() - (now.getTimezoneOffset() * 60000)).toISOString().slice(0, 16);
    datetimeInput.value = localIso;
    checkScheduleReady();
  }
  setDefaultDateTime(5);

  // クイック加算ボタン
  document.querySelectorAll('.btn-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const addMin = parseInt(btn.getAttribute('data-add-min'), 10);
      setDefaultDateTime(addMin);
    });
  });

  // 検出された回復時刻の適用ボタン
  btnApplyDetected.addEventListener('click', () => {
    if (detectedTimeData && detectedTimeData.isoString) {
      datetimeInput.value = detectedTimeData.isoString;
      checkScheduleReady();
    }
  });

  datetimeInput.addEventListener('change', checkScheduleReady);
  datetimeInput.addEventListener('input', checkScheduleReady);

  // 要素ピッカーの開始
  btnPickElement.addEventListener('click', async () => {
    if (!activeTab || !activeTab.id) return;

    try {
      await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        files: ['content.js']
      });

      await chrome.tabs.sendMessage(activeTab.id, { action: 'START_PICKER' });
      // ユーザーが要素をクリックできるようにポップアップを閉じる
      window.close();
    } catch (err) {
      alert('要素ピッカーを起動できませんでした: ' + err.message);
    }
  });

  // 今すぐテストクリック
  btnTestClick.addEventListener('click', async () => {
    if (!currentTarget || !activeTab || !activeTab.id) return;
    btnTestClick.disabled = true;
    btnTestClick.textContent = '⏳ クリック中...';

    try {
      const res = await chrome.tabs.sendMessage(activeTab.id, {
        action: 'TRIGGER_CLICK',
        target: currentTarget
      });

      if (res && res.success) {
        alert('✅ クリックに成功しました！');
      } else {
        alert('⚠️ クリックに失敗しました: ' + (res?.reason || '不明なエラー'));
      }
    } catch (e) {
      alert('エラー: ' + e.message);
    } finally {
      btnTestClick.disabled = false;
      btnTestClick.textContent = '⚡ 今すぐテストクリック';
    }
  });

  // スケジュール登録
  btnSchedule.addEventListener('click', async () => {
    if (!currentTarget || !datetimeInput.value) return;

    const scheduledDate = new Date(datetimeInput.value);
    const scheduledTime = scheduledDate.getTime();

    if (scheduledTime <= Date.now()) {
      alert('指定日時は未来の時刻を選択してください。');
      return;
    }

    const newTask = {
      id: 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
      createdAt: Date.now(),
      scheduledTime: scheduledTime,
      url: currentTarget.url || activeTab?.url,
      title: currentTarget.title || activeTab?.title,
      selector: currentTarget.selector,
      xpath: currentTarget.xpath,
      innerText: currentTarget.innerText,
      status: 'WAITING'
    };

    chrome.runtime.sendMessage({ action: 'SCHEDULE_TASK', task: newTask }, async () => {
      const data = await chrome.storage.local.get('scheduled_clicker_tasks');
      renderTasks(data.scheduled_clicker_tasks || []);
      alert(`⏰ ${scheduledDate.toLocaleTimeString()} にスケジュールを登録しました！`);
    });
  });

  // タスク一覧描画
  function renderTasks(tasks) {
    taskCount.textContent = `${tasks.length}件`;
    taskList.innerHTML = '';

    if (tasks.length === 0) {
      taskList.innerHTML = '<div class="empty-state">予約中のタスクはありません</div>';
      return;
    }

    // 新しい順にソート
    const sorted = [...tasks].sort((a, b) => b.createdAt - a.createdAt);

    sorted.forEach(t => {
      const item = document.createElement('div');
      item.className = 'task-item';

      const schedTimeStr = new Date(t.scheduledTime).toLocaleString('ja-JP', {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });

      const statusClass = `status-${t.status || 'WAITING'}`;
      let statusLabel = '待機中';
      if (t.status === 'COMPLETED') statusLabel = '完了';
      if (t.status === 'FAILED') statusLabel = '失敗';
      if (t.status === 'RUNNING') statusLabel = '実行中';

      item.innerHTML = `
        <div class="task-item-header">
          <span class="task-time">⏰ ${schedTimeStr}</span>
          <span class="task-status ${statusClass}">${statusLabel}</span>
        </div>
        <div class="task-target">
          <strong>ボタン:</strong> ${escapeHtml(t.innerText || t.selector || '(要素)')}
        </div>
        ${t.resultMessage ? `<div class="text-xs text-muted">${escapeHtml(t.resultMessage)}</div>` : ''}
        <div class="task-actions">
          <button class="btn btn-xs btn-outline btn-delete" data-task-id="${t.id}">
            ${t.status === 'WAITING' ? 'キャンセル' : '削除'}
          </button>
        </div>
      `;

      item.querySelector('.btn-delete').addEventListener('click', async (e) => {
        const taskId = e.target.getAttribute('data-task-id');
        chrome.runtime.sendMessage({ action: 'CANCEL_TASK', taskId: taskId }, async () => {
          const updated = await chrome.storage.local.get('scheduled_clicker_tasks');
          renderTasks(updated.scheduled_clicker_tasks || []);
        });
      });

      taskList.appendChild(item);
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, m => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    })[m]);
  }
});
