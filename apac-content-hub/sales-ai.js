/**
 * Content Copilot for APAC Content Hub — client bundle.
 * Configure the AI backend via:
 *   <meta name="anz-sales-ai-endpoint" content="https://your-worker.workers.dev/chat">
 *   or URL query ?ai=https://...
 *   or localStorage.setItem('anzSalesAiEndpoint', url)
 *
 * Without an endpoint, sends still rank catalog assets and show a local fallback summary.
 */
(function () {
  'use strict';

  const STORAGE_MESSAGES = 'anzSalesAiMessages';
  const MAX_CONTEXT_ASSETS = 22;
  const SUMMARY_MAX = 420;

  function getEndpoint() {
    const meta = document.querySelector('meta[name="anz-sales-ai-endpoint"]');
    const fromMeta = meta && meta.getAttribute('content');
    if (fromMeta && fromMeta.trim()) return fromMeta.trim();
    try {
      const q = new URLSearchParams(window.location.search).get('ai');
      if (q) return q.trim();
    } catch (_) {}
    try {
      const ls = localStorage.getItem('anzSalesAiEndpoint');
      if (ls) return ls.trim();
    } catch (_) {}
    return '';
  }

  function tokenize(text) {
    return (text || '')
      .toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .split(/\s+/)
      .filter((t) => t.length > 2);
  }

  /** @param {object[]} assets normalized hub assets */
  function scoreAssetsForQuery(query, assets, limit) {
    const terms = tokenize(query);
    if (!terms.length || !assets.length) return [];

    const scored = assets.map((a) => {
      let score = 0;
      const hay = [
        a.title,
        a.summary,
        a.theme,
        a.type,
        a.persona,
        a.notes,
        (a.segment || []).join(' '),
        a.industry,
        a.geo,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      for (const t of terms) {
        if (hay.includes(t)) score += 3;
      }
      const title = (a.title || '').toLowerCase();
      for (const t of terms) {
        if (title.includes(t)) score += 4;
      }

      const g = (a.geo || a.region || '').toString();
      if (/anz|australia|new zealand|au|nz/i.test(query) && /ANZ/i.test(g)) score += 5;
      if (a.credibility === 'VERY HIGH' || a.credibility === 'HIGH') score += 1;
      if (a.status === 'published') score += 0.5;

      return { a, score };
    });

    const positive = scored.filter((x) => x.score > 0).sort((a, b) => b.score - a.score);
    const list = (positive.length ? positive : scored.sort((a, b) => b.score - a.score)).slice(0, limit);

    return list.map((x) => x.a);
  }

  function trimSummary(s) {
    if (!s) return '';
    s = s.replace(/\s+/g, ' ').trim();
    if (s.length <= SUMMARY_MAX) return s;
    return s.slice(0, SUMMARY_MAX) + '…';
  }

  function assetToContext(a) {
    return {
      title: a.title || '',
      type: a.type || '',
      url: a.url || '',
      internal: a.internal || '',
      stage: a.stage || '',
      theme: a.theme || '',
      geo: a.geo || '',
      persona: a.persona || '',
      summary: trimSummary(a.summary || ''),
      notes: trimSummary(a.notes || ''),
      segment: a.segment || [],
      credibility: a.credibility || '',
      status: a.status || '',
    };
  }

  function simpleEscapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  /** Minimal formatting: newlines, **bold**, [label](url) */
  function formatReply(text) {
    let h = simpleEscapeHtml(text || '');
    h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    h = h.replace(/\n/g, '<br>');
    return h;
  }

  function loadStoredMessages() {
    try {
      const raw = sessionStorage.getItem(STORAGE_MESSAGES);
      if (raw) return JSON.parse(raw);
    } catch (_) {}
    return [];
  }

  function saveStoredMessages(msgs) {
    try {
      sessionStorage.setItem(STORAGE_MESSAGES, JSON.stringify(msgs.slice(-40)));
    } catch (_) {}
  }

  let assetsRef = [];
  let chatMessages = loadStoredMessages();

  function renderChat(root) {
    const list = root.querySelector('[data-sales-ai-messages]');
    if (!list) return;
    const endpoint = getEndpoint();
    list.innerHTML = '';

    if (!chatMessages.length) {
      const hint = document.createElement('div');
      hint.className = 'sales-ai-welcome';
      hint.innerHTML =
        '<p><strong>Ask anything</strong> about what to send a prospect, which deck fits a CIO meeting, ANZ case studies for retail, etc.</p>' +
        '<p class="sales-ai-welcome-sub">I pull the closest matches from this hub catalog, then ' +
        (endpoint
          ? 'your connected model reasons over them and can ask a clarifying question before recommending.'
          : '<strong>add an AI endpoint</strong> (meta tag, <code>?ai=</code>, or localStorage) for full reasoning. Until then you still get ranked asset picks.') +
        '</p>';
      list.appendChild(hint);
      return;
    }

    for (const m of chatMessages) {
      const row = document.createElement('div');
      row.className = 'sales-ai-msg sales-ai-msg--' + m.role;
      const bubble = document.createElement('div');
      bubble.className = 'sales-ai-bubble';
      if (m.role === 'assistant') {
        bubble.innerHTML = formatReply(m.content);
      } else {
        bubble.textContent = m.content;
      }
      row.appendChild(bubble);
      list.appendChild(row);
    }
    list.scrollTop = list.scrollHeight;
  }

  function setBusy(root, on) {
    const btn = root.querySelector('[data-sales-ai-send]');
    const inp = root.querySelector('[data-sales-ai-input]');
    if (btn) btn.disabled = !!on;
    if (inp) inp.disabled = !!on;
    root.classList.toggle('sales-ai--busy', !!on);
  }

  function localFallbackReply(query, ranked) {
    const lines = [];
    lines.push('Here are the closest assets in this hub right now (connect an AI endpoint for deeper reasoning and follow-up questions).');
    lines.push('');
    if (!ranked.length) {
      lines.push('No strong keyword overlap. Try the search bar or name a format (deck, case study, blog).');
      return lines.join('\n');
    }
    lines.push('**Top picks**');
    ranked.slice(0, 8).forEach((a, i) => {
      const link = a.url ? `[${a.title}](${a.url})` : a.title;
      lines.push(`${i + 1}. ${link} — _${a.type || 'Asset'}_ · ${a.stage || ''} · ${a.geo || ''}`);
      if (a.summary) lines.push('   ' + trimSummary(a.summary));
    });
    lines.push('');
    lines.push('**Tip:** Add `<meta name="anz-sales-ai-endpoint" content="https://…">` or `?ai=` with your proxy URL to enable the full assistant.');
    return lines.join('\n');
  }

  async function callAssistant(endpoint, userText, history, contextAssets) {
    const body = {
      messages: history.concat([{ role: 'user', content: userText }]),
      contextAssets,
      sessionId: window.__anzSalesAiSession || (window.__anzSalesAiSession = crypto.randomUUID()),
    };

    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 120000);

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
      mode: 'cors',
    }).finally(() => clearTimeout(t));

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(errText || `Request failed (${res.status})`);
    }

    const data = await res.json();
    const content = data.message || data.content || data.reply || (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content);
    if (!content || typeof content !== 'string') {
      throw new Error('Unexpected response from AI endpoint');
    }
    return content;
  }

  async function onSend(root) {
    const inp = root.querySelector('[data-sales-ai-input]');
    const text = (inp && inp.value || '').trim();
    if (!text) return;

    const endpoint = getEndpoint();
    const ranked = scoreAssetsForQuery(text, assetsRef, MAX_CONTEXT_ASSETS);
    const contextAssets = ranked.map(assetToContext);

    chatMessages.push({ role: 'user', content: text });
    saveStoredMessages(chatMessages);
    inp.value = '';
    renderChat(root);

    setBusy(root, true);
    const status = root.querySelector('[data-sales-ai-status]');
    if (status) status.textContent = endpoint ? 'Thinking with catalog context…' : 'Ranking catalog (offline mode)…';

    try {
      let reply;
      if (endpoint) {
        const hist = chatMessages.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
        reply = await callAssistant(endpoint, text, hist, contextAssets);
      } else {
        await new Promise((r) => setTimeout(r, 180));
        reply = localFallbackReply(text, ranked);
      }

      chatMessages.push({ role: 'assistant', content: reply });
      saveStoredMessages(chatMessages);
      if (status) status.textContent = '';
    } catch (e) {
      const msg = e && e.message ? e.message : 'Something went wrong';
      chatMessages.push({
        role: 'assistant',
        content: '**Could not reach the AI endpoint.**\n\n' + msg + '\n\nCheck CORS, URL, and that your proxy forwards to the model.',
      });
      saveStoredMessages(chatMessages);
      if (status) status.textContent = '';
    }

    setBusy(root, false);
    renderChat(root);
  }

  function wire(root) {
    const send = root.querySelector('[data-sales-ai-send]');
    const inp = root.querySelector('[data-sales-ai-input]');
    const clearBtn = root.querySelector('[data-sales-ai-clear]');

    if (send) send.addEventListener('click', () => onSend(root));
    if (inp) {
      inp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          onSend(root);
        }
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        chatMessages = [];
        saveStoredMessages(chatMessages);
        renderChat(root);
      });
    }
  }

  function mount() {
    const root = document.getElementById('salesAiPanel');
    if (!root) return;

    wire(root);

    const openers = document.querySelectorAll('[data-open-sales-ai]');
    openers.forEach((el) =>
      el.addEventListener('click', () => {
        root.classList.add('open');
        root.setAttribute('aria-hidden', 'false');
        const inp = root.querySelector('[data-sales-ai-input]');
        const na = document.getElementById('naturalAgentInput');
        if (inp && na && na.value.trim()) inp.value = na.value.trim();
        refreshEndpointUi();
        if (inp) setTimeout(() => inp.focus(), 200);
      })
    );

    root.querySelectorAll('[data-close-sales-ai]').forEach((el) => {
      el.addEventListener('click', () => {
        root.classList.remove('open');
        root.setAttribute('aria-hidden', 'true');
      });
    });

    renderChat(root);
    refreshEndpointUi();
  }

  function refreshEndpointUi() {
    const ep = getEndpoint();
    document.querySelectorAll('[data-sales-ai-mode]').forEach((pill) => {
      pill.classList.toggle('offline', !ep);
    });
  }

  window.__salesAiOnAssetsLoaded = function (assets) {
    assetsRef = Array.isArray(assets) ? assets : [];
    const badge = document.querySelector('[data-sales-ai-count]');
    if (badge) badge.textContent = String(assetsRef.length);
    refreshEndpointUi();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
