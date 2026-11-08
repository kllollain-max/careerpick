/* Optional CareerPick pageviews. No provider request is made before consent. */
(function () {
  'use strict';

  if (window.location.origin !== 'https://kllollain-max.github.io' ||
      !window.location.pathname.startsWith('/careerpick/') ||
      window.__CP_NAVER_ANALYTICS_V1__) return;
  window.__CP_NAVER_ANALYTICS_V1__ = true;

  var STORAGE_KEY = 'careerpick:naver-analytics-consent:v1';
  var SITE_ID = '1e121e3d2f09900';
  var consent = null;
  var storageWarning = '';
  var connectionNotice = '';
  var sdkState = 'idle';
  var sdkScript = null;
  var requested = false;
  var cancelled = false;
  var pageviewAttempted = false;

  function readChoice() {
    try {
      var value = window.localStorage.getItem(STORAGE_KEY);
      return { ok: true, value: value === 'granted' || value === 'denied' ? value : null };
    } catch (_) {
      return { ok: false, value: null };
    }
  }

  function saveChoice(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
      return window.localStorage.getItem(STORAGE_KEY) === value;
    } catch (_) {
      return false;
    }
  }

  function element(tag, id, text) {
    var node = document.createElement(tag);
    if (id) node.id = id;
    if (text) node.textContent = text;
    return node;
  }

  var section = element('section', 'cp-naver-analytics');
  section.setAttribute('aria-label', '방문 통계 설정');
  var settings = element('button', 'cp-analytics-settings', '방문 통계 설정');
  settings.type = 'button';
  settings.setAttribute('aria-controls', 'cp-analytics-panel');
  var status = element('p', 'cp-analytics-status');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  var panel = element('div', 'cp-analytics-panel');
  panel.appendChild(element('h2', '', '방문 통계를 허용하시겠어요?'));
  panel.appendChild(element('p', '', '방문자 수와 유입 경로를 확인하기 위해 네이버 애널리틱스를 사용합니다. 허용하면 네이버가 페이지 주소·접속 환경·쿠키 등 방문 정보를 처리할 수 있습니다. 허용하지 않아도 사이트를 이용할 수 있습니다.'));
  var policy = element('a', '', '개인정보처리방침 확인');
  policy.href = '/careerpick/privacy.html#visit-analytics';
  panel.appendChild(policy);
  var actions = element('div', 'cp-analytics-actions');
  var allow = element('button', 'cp-analytics-allow', '허용');
  var deny = element('button', 'cp-analytics-deny', '허용 안 함');
  allow.type = deny.type = 'button';
  actions.append(allow, deny);
  panel.appendChild(actions);
  section.append(settings, status, panel);
  document.body.appendChild(section);

  function showPanel(open, focusSettings) {
    panel.hidden = !open;
    settings.setAttribute('aria-expanded', String(open));
    if (focusSettings) settings.focus();
  }

  function renderStatus() {
    section.dataset.choice = consent || 'unset';
    section.dataset.analyticsState = sdkState;
    var label = consent === 'granted' ? '방문 통계 허용' : '방문 통계 꺼짐';
    status.textContent = [label, storageWarning, connectionNotice].filter(Boolean).join(' · ');
  }

  function fail(state, message) {
    sdkState = state;
    connectionNotice = message;
    renderStatus();
  }

  function stopAnalytics(canReload) {
    if (!requested) return;
    cancelled = true;
    sdkState = 'cancelled';
    if (sdkScript) {
      sdkScript.onload = sdkScript.onerror = null;
      sdkScript.remove();
    }
    // Removing a script cannot unload its listeners or cancel its execution.
    // Reload only when storage confirms that it cannot grant consent again.
    if (canReload) {
      window.location.reload();
    } else {
      connectionNotice = '이미 시작된 통계 연결을 완전히 종료하려면 이 탭을 닫아주세요.';
    }
  }

  function startAnalytics() {
    if (consent !== 'granted' || requested || cancelled) return;
    // Do not adopt an existing SDK: its ID and prior pageview are not ours.
    if (window.wcs || window.wcs_do ||
        document.querySelector('script[src*="wcs.pstatic.net"]') ||
        (window.wcs_add && (typeof window.wcs_add !== 'object' || window.wcs_add.wa))) {
      fail('conflict', '통계 연결을 확인해야 합니다. 사이트 이용은 계속할 수 있습니다.');
      return;
    }
    requested = true;
    sdkState = 'loading';
    sdkScript = document.createElement('script');
    sdkScript.id = 'cp-naver-analytics-sdk';
    sdkScript.src = 'https://wcs.pstatic.net/wcslog.js';
    sdkScript.async = true;
    sdkScript.onload = function () {
      if (consent !== 'granted' || cancelled || pageviewAttempted) return;
      try {
        if (window.wcs_add && window.wcs_add.wa && window.wcs_add.wa !== SITE_ID) {
          fail('conflict', '통계 연결을 확인해야 합니다. 사이트 이용은 계속할 수 있습니다.');
          return;
        }
        if (!window.wcs || typeof window.wcs_do !== 'function') {
          fail('failed', '방문 통계 연결에 실패했습니다. 사이트 이용은 계속할 수 있습니다.');
          return;
        }
        window.wcs_add = window.wcs_add || {};
        window.wcs_add.wa = SITE_ID;
        // Set before calling: a thrown error may follow a completed send.
        pageviewAttempted = true;
        window.wcs_do();
        sdkState = 'sent';
        connectionNotice = '';
        renderStatus();
      } catch (_) {
        fail('failed', '방문 통계 연결에 실패했습니다. 사이트 이용은 계속할 수 있습니다.');
      }
    };
    sdkScript.onerror = function () {
      if (!cancelled) fail('failed', '방문 통계 연결에 실패했습니다. 사이트 이용은 계속할 수 있습니다.');
    };
    try {
      document.head.appendChild(sdkScript);
    } catch (_) {
      fail('failed', '방문 통계 연결에 실패했습니다. 사이트 이용은 계속할 수 있습니다.');
    }
    renderStatus();
  }

  function choose(value) {
    consent = value;
    connectionNotice = '';
    var saved = saveChoice(value);
    storageWarning = saved ? '' : (value === 'denied'
      ? '선택을 저장하지 못했습니다. 이번 페이지에서만 꺼지며 다음 방문에는 기존 허용 설정이 다시 적용될 수 있습니다.'
      : '선택을 저장하지 못했습니다. 이번 페이지에서만 적용되며 다음 방문에는 다시 선택이 필요할 수 있습니다.');
    if (value === 'granted') {
      if (cancelled) {
        if (saved) window.location.reload();
        else connectionNotice = '새 설정을 저장한 뒤 다시 방문하면 통계를 연결할 수 있습니다.';
      } else {
        startAnalytics();
      }
    } else {
      stopAnalytics(saved);
    }
    showPanel(!saved, saved);
    renderStatus();
  }

  settings.addEventListener('click', function () { showPanel(panel.hidden, false); });
  allow.addEventListener('click', function () { choose('granted'); });
  deny.addEventListener('click', function () { choose('denied'); });
  window.addEventListener('storage', function (event) {
    if (event.key !== STORAGE_KEY && event.key !== null) return;
    try { if (event.storageArea && event.storageArea !== window.localStorage) return; }
    catch (_) { /* An unreadable store is handled as no consent below. */ }
    var stored = readChoice();
    consent = stored.value;
    storageWarning = stored.ok ? '' : '저장된 설정을 확인할 수 없습니다. 선택 전에는 방문 통계를 전송하지 않습니다.';
    // A denied or cleared setting in another tab revokes this document too.
    if (consent === 'granted') startAnalytics();
    else stopAnalytics(stored.ok);
    showPanel(consent === null, false);
    renderStatus();
  });

  var initial = readChoice();
  consent = initial.value;
  storageWarning = initial.ok ? '' : '저장된 설정을 확인할 수 없습니다. 선택 전에는 방문 통계를 전송하지 않습니다.';
  showPanel(consent === null, false);
  renderStatus();
  startAnalytics();
}());
