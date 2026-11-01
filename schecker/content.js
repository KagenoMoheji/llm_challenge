// content.js - Scheduled Clicker Content Script

(function () {
  if (window.__scheduledClickerLoaded) return;
  window.__scheduledClickerLoaded = true;

  let isPicking = false;
  let hoveredElement = null;
  let prevOutline = '';
  let prevBg = '';
  let lastClickTime = 0; // 2重クリック防止用タイムスタンプ

  // ユーティリティ: 要素の最適なセレクタを生成
  function generateSelector(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';

    // 1. data-testid や aria-label など一意になりやすい属性を優先
    if (el.hasAttribute('data-testid')) {
      return `[data-testid="${el.getAttribute('data-testid')}"]`;
    }
    if (el.hasAttribute('aria-label')) {
      return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
    }

    // 2. ID (数字で始まらない場合)
    if (el.id && !/^\d/.test(el.id)) {
      return `#${CSS.escape(el.id)}`;
    }

    // 3. パス階層生成
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body && current !== document.documentElement) {
      let selector = current.tagName.toLowerCase();
      
      // 有効なクラスがあれば最大2個付与 (動的ランダムクラス除外を考慮)
      if (current.classList.length > 0) {
        const validClasses = Array.from(current.classList)
          .filter(c => !c.includes(':') && !c.match(/^[a-z0-9_-]{10,}$/i)) // Tailwindのランダムハッシュぽいものを除外
          .slice(0, 2);
        if (validClasses.length > 0) {
          selector += '.' + validClasses.map(c => CSS.escape(c)).join('.');
        }
      }

      // 兄弟要素の中でのインデックス
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
        if (siblings.length > 1) {
          const index = siblings.indexOf(current) + 1;
          selector += `:nth-of-type(${index})`;
        }
      }

      parts.unshift(selector);
      if (parts.length >= 4) break; // 深すぎないようにする
      current = current.parentElement;
    }

    return parts.join(' > ');
  }

  // ユーティリティ: XPath 生成
  function getXPath(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) return '';
    if (element.id) return `//*[@id="${element.id}"]`;
    
    const paths = [];
    for (; element && element.nodeType === Node.ELEMENT_NODE; element = element.parentNode) {
      let index = 0;
      let hasSameNodes = false;
      for (let sibling = element.previousSibling; sibling; sibling = sibling.previousSibling) {
        if (sibling.nodeType === Node.DOCUMENT_TYPE_NODE) continue;
        if (sibling.nodeName === element.nodeName) {
          index++;
          hasSameNodes = true;
        }
      }
      if (hasSameNodes || element.nextSibling) {
        paths.unshift(`${element.nodeName.toLowerCase()}[${index + 1}]`);
      } else {
        paths.unshift(element.nodeName.toLowerCase());
      }
    }
    return paths.length ? '/' + paths.join('/') : '';
  }

  // Claude等の「利用枠はMM月dd日のHH:mmに回復します」を検出
  function detectRecoveryTime() {
    const text = document.body ? document.body.innerText : '';
    // 例: "利用枠は10月24日の23:00に回復します" や "10月24日 23:00"
    const match = text.match(/(?:利用枠は)?(\d{1,2})月(\d{1,2})日(?:の|\s*)(\d{1,2}):(\d{2})/);
    if (match) {
      const now = new Date();
      const month = parseInt(match[1], 10) - 1;
      const day = parseInt(match[2], 10);
      const hour = parseInt(match[3], 10);
      const minute = parseInt(match[4], 10);
      
      let year = now.getFullYear();
      const targetDate = new Date(year, month, day, hour, minute, 0);
      // 年またぎの考慮
      if (targetDate.getTime() < now.getTime() - 1000 * 60 * 60 * 24 * 30) {
        targetDate.setFullYear(year + 1);
      }
      return {
        matchedText: match[0],
        timestamp: targetDate.getTime(),
        isoString: new Date(targetDate.getTime() - (targetDate.getTimezoneOffset() * 60000)).toISOString().slice(0, 16)
      };
    }
    return null;
  }

  // ピッカー用のオーバーレイバッジ
  let badgeEl = null;
  function showBadge(text) {
    if (!badgeEl) {
      badgeEl = document.createElement('div');
      badgeEl.id = '__scheduled_clicker_badge';
      badgeEl.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: #1e293b;
        color: #ffffff;
        padding: 10px 18px;
        border-radius: 8px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 14px;
        font-weight: 500;
        z-index: 2147483647;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        pointer-events: none;
        border: 1px solid #3b82f6;
      `;
      document.body.appendChild(badgeEl);
    }
    badgeEl.textContent = text;
    badgeEl.style.display = 'block';
  }

  function hideBadge() {
    if (badgeEl) {
      badgeEl.style.display = 'none';
    }
  }

  // ピッカーのハイライト解除
  function clearHighlight() {
    if (hoveredElement) {
      hoveredElement.style.outline = prevOutline;
      hoveredElement.style.backgroundColor = prevBg;
      hoveredElement = null;
    }
  }

  // イベントハンドラ
  function handleMouseOver(e) {
    if (!isPicking) return;
    e.stopPropagation();

    clearHighlight();

    hoveredElement = e.target;
    prevOutline = hoveredElement.style.outline;
    prevBg = hoveredElement.style.backgroundColor;

    hoveredElement.style.outline = '3px solid #2563eb';
    hoveredElement.style.backgroundColor = 'rgba(37, 99, 235, 0.15)';
  }

  function handleClick(e) {
    if (!isPicking) return;
    e.preventDefault();
    e.stopPropagation();

    const el = e.target;
    clearHighlight();
    stopPicker();

    const selector = generateSelector(el);
    const xpath = getXPath(el);
    const innerText = (el.innerText || el.textContent || '').trim().slice(0, 100);
    const tagName = el.tagName.toLowerCase();

    // 選択結果をストレージに一時保存＆バックグラウンドに通知
    const pickedInfo = {
      tagName,
      selector,
      xpath,
      innerText,
      url: window.location.href,
      title: document.title,
      detectedRecoveryTime: detectRecoveryTime()
    };

    chrome.storage.local.set({ lastPickedElement: pickedInfo }, () => {
      chrome.runtime.sendMessage({ action: 'ELEMENT_PICKED_SUCCESS', data: pickedInfo });
    });
  }

  function handleKeyDown(e) {
    if (!isPicking) return;
    if (e.key === 'Escape') {
      clearHighlight();
      stopPicker();
      chrome.runtime.sendMessage({ action: 'PICKER_CANCELLED' });
    }
  }

  function startPicker() {
    isPicking = true;
    showBadge('🎯 クリックしたいボタン・要素をクリックしてください (Escでキャンセル)');
    document.addEventListener('mouseover', handleMouseOver, true);
    document.addEventListener('click', handleClick, true);
    document.addEventListener('keydown', handleKeyDown, true);
  }

  function stopPicker() {
    isPicking = false;
    hideBadge();
    document.removeEventListener('mouseover', handleMouseOver, true);
    document.removeEventListener('click', handleClick, true);
    document.removeEventListener('keydown', handleKeyDown, true);
  }

  // 要素を探索してクリックする関数
  function findAndClick(target) {
    let el = null;

    // 1. セレクタで探す
    if (target.selector) {
      try {
        el = document.querySelector(target.selector);
      } catch (e) {
        console.warn('Selector query failed:', e);
      }
    }

    // 2. ボタンテキストで探す (Claudeの「続ける」「再開」等のボタンの場合に非常に有効)
    if (!el && target.innerText) {
      const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]'));
      el = candidates.find(c => {
        const text = (c.innerText || c.textContent || '').trim();
        return text && (text === target.innerText || text.includes(target.innerText) || target.innerText.includes(text));
      });
    }

    // 3. XPathで探す
    if (!el && target.xpath) {
      try {
        const res = document.evaluate(target.xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        el = res.singleNodeValue;
      } catch (e) {
        console.warn('XPath query failed:', e);
      }
    }

    if (!el) {
      return { success: false, reason: 'ELEMENT_NOT_FOUND' };
    }

    // 直近3秒以内の重複クリック防止ガード
    const now = Date.now();
    if (now - lastClickTime < 3000) {
      console.log('[Scheduled Clicker] 3秒以内の重複クリック要求をスキップしました。');
      return { success: true, skipped: true, clickedText: (el.innerText || el.textContent || '').trim() };
    }

    // disabled状態チェック
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
      return { success: false, reason: 'ELEMENT_DISABLED' };
    }

    // 画面内にスクロールして確実にクリック
    try {
      el.scrollIntoView({ behavior: 'instant', block: 'center' });
      
      // マウスホバーと押し込みの事前イベントのみ発火 (clickは含めない)
      const prepEvents = ['mouseenter', 'mouseover', 'mousedown', 'mouseup'];
      prepEvents.forEach(evtName => {
        const evt = new MouseEvent(evtName, {
          bubbles: true,
          cancelable: true,
          view: window
        });
        el.dispatchEvent(evt);
      });

      // 単一の確定クリックを実行 (el.click または 単一の click イベント)
      if (typeof el.click === 'function') {
        el.click();
      } else {
        const clickEvt = new MouseEvent('click', {
          bubbles: true,
          cancelable: true,
          view: window
        });
        el.dispatchEvent(clickEvt);
      }

      lastClickTime = Date.now();
      el.setAttribute('data-scheduled-clicked', 'true');

      return { success: true, clickedText: (el.innerText || el.textContent || '').trim() };
    } catch (err) {
      return { success: false, reason: 'CLICK_ERROR: ' + err.message };
    }
  }

  // メッセージ受信リスナー
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'START_PICKER') {
      startPicker();
      sendResponse({ status: 'PICKER_STARTED' });
    } else if (message.action === 'STOP_PICKER') {
      clearHighlight();
      stopPicker();
      sendResponse({ status: 'PICKER_STOPPED' });
    } else if (message.action === 'TRIGGER_CLICK') {
      const result = findAndClick(message.target);
      sendResponse(result);
    } else if (message.action === 'DETECT_RECOVERY') {
      sendResponse({ detected: detectRecoveryTime() });
    }
    return true;
  });

})();
