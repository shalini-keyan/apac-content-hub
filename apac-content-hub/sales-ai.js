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

  /** Greetings and small talk: no LLM in offline mode, so we handle these explicitly. */
  function isLikelyChitChat(raw) {
    const q = (raw || '').trim().toLowerCase();
    if (q.length <= 2) return true;
    if (
      /^(hi|hello|hey|hiya|yo|sup|thanks?|thank you|thx|cheers|gm|good (morning|afternoon|evening)|what'?s up|whats up|howdy|how are you|you good|u good|ok(ay)?|cool|nice|lol+)[\s!.?]*$/i.test(
        q
      )
    ) {
      return true;
    }
    const words = q.split(/\s+/).filter(Boolean);
    if (words.length > 5) return false;
    const stop = new Set([
      'hi', 'hello', 'hey', 'yo', 'sup', 'thanks', 'thank', 'you', 'thx', 'cheers', 'whats', 'what', 'up', 'how', 'are', 'is', 'it', 'the', 'a', 'an', 'to', 'in', 'on', 'for', 'there', 'here', 'yes', 'no', 'ok', 'cool', 'nice', 'good', 'doing', 'going', 'just', 'chilling', 'anyone', 'testing', 'test',
    ]);
    const allStop = words.every((w) => {
      const x = w.replace(/[^a-z]/gi, '');
      return x.length <= 2 || stop.has(x);
    });
    return allStop && words.length <= 4;
  }

  /** Curated ANZ starters when the query does not map to search terms (e.g. “hi”). */
  function pickAnzStarters(assets, n) {
    const credOrder = { 'VERY HIGH': 3, HIGH: 2, MED: 1, LOW: 0 };
    const scored = assets
      .filter((a) => {
        const geo = (a.geo || a.region || '').toString();
        const okGeo = /anz/i.test(geo);
        const preferType = /pitch|deck|case study|presentation|report|blog/i.test(a.type || '');
        return okGeo && (a.status === 'published' || !a.status) && (preferType || a.url);
      })
      .map((a) => ({
        a,
        s: (credOrder[a.credibility] || 0) + (a.title && /anz|pitch|case/i.test(a.title) ? 2 : 0),
      }))
      .sort((x, y) => y.s - x.s);
    const out = [];
    const seen = new Set();
    for (const { a } of scored) {
      const k = a.title || '';
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(a);
      if (out.length >= n) break;
    }
    return out;
  }

  function formatPickList(ranked, max) {
    const lines = [];
    ranked.slice(0, max).forEach((a, i) => {
      const link = a.url ? `[${a.title}](${a.url})` : a.title;
      lines.push(`${i + 1}. ${link} · ${a.type || 'Asset'} · ${a.stage || '—'} · ${a.geo || '—'}`);
      if (a.summary) lines.push('   ' + trimSummary(a.summary));
    });
    return lines;
  }

  function localChitChatReply(assets) {
    const starters = pickAnzStarters(assets, 6);
    const lines = [];
    lines.push(
      'Hey! Right now this Copilot is in **offline mode** (no AI endpoint on this site), so I am **not** running a full language model. I cannot freestyle chat the way ChatGPT would.'
    );
    lines.push('');
    lines.push(
      'What I **can** do here is **rank assets** when you describe a deal or asset type. Try something like: **“BOFU ANZ case study for department stores”** or **“deck for CIO unified commerce”**.'
    );
    lines.push('');
    if (starters.length) {
      lines.push('**Popular ANZ picks** to open while you refine your ask:');
      lines.push('');
      lines.push(...formatPickList(starters, 6));
      lines.push('');
    }
    lines.push(
      '**Want real back-and-forth?** Your team needs to set `anz-sales-ai-endpoint` on this hub (or test with `?ai=https://…`) to a proxy that calls OpenAI or similar.'
    );
    return lines.join('\n');
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
        '<p><strong>Ask in plain language</strong> about what to send a prospect, which deck fits a CIO, ANZ case studies, etc.</p>' +
        '<p class="sales-ai-welcome-sub">' +
        (endpoint
          ? 'Your connected model sees catalog context and can reply conversationally, including clarifying questions.'
          : '<strong>No AI endpoint is configured on this site.</strong> Replies use catalog search and templates, not a live chat model. Add <code>anz-sales-ai-endpoint</code> (or <code>?ai=</code>) for real conversation.') +
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

  function localFallbackReply(query, ranked, assets) {
    const lines = [];
    lines.push(
      '**Offline mode:** I matched your words against this hub’s catalog (no LLM). Here is what ranked closest.'
    );
    lines.push('');
    if (!ranked.length) {
      lines.push(
        'I did not get strong keyword overlap. Add **stage** (TOFU/MOFU/BOFU), **format** (deck, case study, blog), **industry**, or **ANZ**, then send again.'
      );
      lines.push('');
      const starters = pickAnzStarters(assets, 5);
      if (starters.length) {
        lines.push('**ANZ examples you can start from:**');
        lines.push('');
        lines.push(...formatPickList(starters, 5));
        lines.push('');
      }
      lines.push(
        '**Full conversational answers** need an AI endpoint on this site (see tip below).'
      );
      lines.push('');
      lines.push(
        '**Tip:** `<meta name="anz-sales-ai-endpoint" content="https://…">` or `?ai=` pointing at your secure proxy.'
      );
      return lines.join('\n');
    }
    lines.push('**Closest matches**');
    lines.push('');
    lines.push(...formatPickList(ranked, 8));
    lines.push('');
    lines.push(
      '**Tip:** Connect an endpoint for follow-up questions and synthesis, not just keyword ranking.'
    );
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
        await new Promise((r) => setTimeout(r, 120));
        if (isLikelyChitChat(text)) {
          reply = localChitChatReply(assetsRef);
        } else {
          reply = localFallbackReply(text, ranked, assetsRef);
        }
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
        const hubSearch = document.getElementById('search');
        if (inp && hubSearch && hubSearch.value.trim()) inp.value = hubSearch.value.trim();
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
