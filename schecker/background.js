// background.js - Scheduled Clicker Service Worker

// タスク保存のストレージキー
const STORAGE_KEY = 'scheduled_clicker_tasks';

// タスクリストを取得
async function getTasks() {
  const data = await chrome.storage.local.get(STORAGE_KEY);
  return data[STORAGE_KEY] || [];
}

// タスクリストを保存
async function saveTasks(tasks) {
  await chrome.storage.local.set({ [STORAGE_KEY]: tasks });
}

// 通知を表示
function showNotification(title, message) {
  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icons/icon128.png',
    title: `[Scheduled Clicker] ${title}`,
    message: message,
    priority: 2
  });
}

// タブに対してクリックを試行（リトライ付き）
async function attemptClickWithRetry(task, tabId, maxRetries = 10, intervalMs = 3000) {
  let attempt = 0;

  while (attempt < maxRetries) {
    attempt++;
    console.log(`[Scheduled Clicker] Attempt ${attempt}/${maxRetries} for task: ${task.id}`);

    try {
      // content script が注入されているか確認・注入
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tabId },
          files: ['content.js']
        });
      } catch (injectErr) {
        // すでに注入されている場合などは無視
      }

      // クリック指示メッセージを送信
      const response = await chrome.tabs.sendMessage(tabId, {
        action: 'TRIGGER_CLICK',
        target: {
          selector: task.selector,
          xpath: task.xpath,
          innerText: task.innerText
        }
      });

      if (response && response.success) {
        console.log(`[Scheduled Clicker] Click succeeded on attempt ${attempt}!`);
        return { success: true, attempts: attempt, clickedText: response.clickedText };
      } else {
        console.warn(`[Scheduled Clicker] Attempt ${attempt} failed: ${response?.reason || 'Unknown'}`);
      }
    } catch (err) {
      console.warn(`[Scheduled Clicker] Message error on attempt ${attempt}:`, err);
    }

    if (attempt < maxRetries) {
      await new Promise(resolve => setTimeout(resolve, intervalMs));
    }
  }

  return { success: false, attempts: attempt, reason: 'TIMEOUT_RETRY_EXHAUSTED' };
}

// アラーム発火時のハンドラ
chrome.alarms.onAlarm.addListener(async (alarm) => {
  const taskId = alarm.name;
  console.log(`[Scheduled Clicker] Alarm fired for task: ${taskId}`);

  // アラームの多重発火防止
  await chrome.alarms.clear(taskId);

  const tasks = await getTasks();
  const taskIndex = tasks.findIndex(t => t.id === taskId);
  if (taskIndex === -1) {
    console.warn(`[Scheduled Clicker] Task not found for alarm: ${taskId}`);
    return;
  }

  const task = tasks[taskIndex];
  if (task.status === 'RUNNING' || task.status === 'COMPLETED') {
    console.log(`[Scheduled Clicker] Task ${taskId} is already ${task.status}. Skipping.`);
    return;
  }

  task.status = 'RUNNING';
  task.executedAt = Date.now();
  await saveTasks(tasks);

  // 対象タブを探す (URLが一致するか前方一致するタブ)
  const allTabs = await chrome.tabs.query({});
  let targetTab = allTabs.find(tab => tab.url === task.url);

  // 完全一致がない場合、ホスト名や同一ドメインのタブをフォールバック検索
  if (!targetTab && task.url) {
    try {
      const taskOrigin = new URL(task.url).origin;
      targetTab = allTabs.find(tab => tab.url && tab.url.startsWith(taskOrigin));
    } catch (e) {}
  }

  // タブが開かれていなければ、新しく開く
  let createdNewTab = false;
  if (!targetTab) {
    console.log(`[Scheduled Clicker] Target tab not found. Opening new tab: ${task.url}`);
    targetTab = await chrome.tabs.create({ url: task.url, active: true });
    createdNewTab = true;
    // ページのロード完了を待機
    await new Promise(resolve => setTimeout(resolve, 6000));
  } else {
    // 既存タブをアクティブにする
    await chrome.tabs.update(targetTab.id, { active: true });
  }

  // クリック実行（リトライ付き）
  const result = await attemptClickWithRetry(task, targetTab.id, 10, 3000);

  // タスク状態を更新
  const updatedTasks = await getTasks();
  const currentTask = updatedTasks.find(t => t.id === taskId);
  if (currentTask) {
    if (result.success) {
      currentTask.status = 'COMPLETED';
      currentTask.resultMessage = `クリック成功 (試行回数: ${result.attempts}回)`;
      showNotification('クリック成功！', `「${task.innerText || task.selector}」のクリックに成功しました。`);
    } else {
      currentTask.status = 'FAILED';
      currentTask.resultMessage = `失敗: ${result.reason || '要素が見つかりませんでした'}`;
      showNotification('クリック失敗', `ボタンが見つからないか無効な状態でした。(${result.reason})`);
    }
    await saveTasks(updatedTasks);
  }
});

// メッセージハンドラ (ポップアップ等との連携)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'SCHEDULE_TASK') {
    (async () => {
      const task = message.task;
      const tasks = await getTasks();
      tasks.push(task);
      await saveTasks(tasks);

      // アラーム設定
      chrome.alarms.create(task.id, {
        when: task.scheduledTime
      });

      sendResponse({ success: true, taskId: task.id });
    })();
    return true;
  } else if (message.action === 'CANCEL_TASK') {
    (async () => {
      const taskId = message.taskId;
      await chrome.alarms.clear(taskId);
      let tasks = await getTasks();
      tasks = tasks.filter(t => t.id !== taskId);
      await saveTasks(tasks);
      sendResponse({ success: true });
    })();
    return true;
  }
});
