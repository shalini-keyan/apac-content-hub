/**
 * Cloudflare Worker: proxy for Content Copilot (OpenAI chat completions).
 *
 * 1. wrangler secret put OPENAI_API_KEY
 * 2. Deploy; set meta anz-sales-ai-endpoint to https://<worker>/chat
 *
 * Request JSON: { messages: [{role,content}], contextAssets: [...], sessionId }
 * Response JSON: { message: string }
 */
export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '*';
    const cors = {
      'Access-Control-Allow-Origin': origin.includes('shopify') ? origin : '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Accept',
      'Access-Control-Max-Age': '86400',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: cors });
    }

    if (request.method !== 'POST') {
      return json({ error: 'Use POST' }, 405, cors);
    }

    const key = env.OPENAI_API_KEY;
    if (!key) {
      return json({ error: 'OPENAI_API_KEY not set' }, 500, cors);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: 'Invalid JSON' }, 400, cors);
    }

    const { messages = [], contextAssets = [] } = body;
    if (!Array.isArray(messages) || !messages.length) {
      return json({ error: 'messages required' }, 400, cors);
    }

    const catalogBlock = formatCatalog(contextAssets);
    const system = `You are **Content Copilot**, a knowledgeable teammate for Shopify Revenue Marketing (APAC / ANZ sales). You chat naturally (like ChatGPT): you can greet people, acknowledge small talk briefly, then help them win deals with the right collateral.

## Conversation
- Be warm, concise, and human. Short replies unless they ask for depth.
- Follow the thread: references like "that deck", "the second one", or "something for a CIO" should use **conversation context** plus the catalog below.
- If their ask is vague, ask **one or two** clarifying questions (persona, deal stage, industry, ANZ vs global) before dumping links.

## Ground truth (critical)
- The JSON below is the **only** source of truth for **specific asset titles and URLs**. Never invent URLs, Doc IDs, or asset titles that are not in this JSON.
- If nothing fits well, say so honestly and offer the **closest** catalog matches or suggest how they should search the hub.

## Recommendations
- Prefer **ANZ** or **APAC** entries when they mention Australia, New Zealand, ANZ, or local retailers.
- Lead with **what to send when** (e.g. first meeting vs procurement) and **why** for that persona.
- Use Markdown: **bold** asset names; use [title](url) only when \`url\` is non-null in the JSON.

## Catalog (indexed assets for this turn)
${catalogBlock}`;

    const openaiMessages = [{ role: 'system', content: system }, ...messages];

    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${key}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: env.OPENAI_MODEL || 'gpt-4o',
        temperature: (() => {
          const t = parseFloat(env.OPENAI_TEMPERATURE || '0.55', 10);
          return Number.isFinite(t) ? t : 0.55;
        })(),
        messages: openaiMessages,
      }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return json(
        { error: data.error?.message || res.statusText || 'OpenAI error' },
        res.status >= 400 ? res.status : 502,
        cors
      );
    }

    const text = data.choices?.[0]?.message?.content;
    if (!text) {
      return json({ error: 'Empty model response' }, 502, cors);
    }

    return json({ message: text }, 200, cors);
  },
};

function formatCatalog(assets) {
  if (!assets.length) return '(No ranked assets passed from the hub; answer from general Shopify positioning.)';
  return JSON.stringify(
    assets.slice(0, 40).map((a) => ({
      title: a.title,
      type: a.type,
      url: a.url || null,
      stage: a.stage,
      theme: a.theme,
      geo: a.geo,
      summary: a.summary,
      persona: a.persona,
    })),
    null,
    0
  );
}

function json(obj, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...extraHeaders,
    },
  });
}
