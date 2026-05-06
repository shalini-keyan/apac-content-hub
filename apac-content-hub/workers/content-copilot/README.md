# Content Copilot Worker

Proxies the hub to OpenAI so **Content Copilot** can chat like GPT while only citing assets from the catalog JSON each request sends.

## One-time setup

From this directory:

```bash
pnpm install
pnpm exec wrangler login
pnpm exec wrangler secret put OPENAI_API_KEY
pnpm run deploy
```

Copy the `*.workers.dev` URL from the deploy output.

## Wire the hub

In `apac-content-hub/index.html`, set:

```html
<meta name="anz-sales-ai-endpoint" content="https://YOUR-WORKER.workers.dev/chat">
```

Or test without editing the file:

`https://apac-content-hub.quick.shopify.io/?ai=https://YOUR-WORKER.workers.dev/chat`

Then `quick deploy` the hub again if you changed the meta tag.

## CI / non-interactive deploy

Create a Cloudflare API token with **Workers Edit** and set:

`export CLOUDFLARE_API_TOKEN=...`

Then `pnpm run deploy` from this folder.

## Config

- Worker source: `../../sales-ai-proxy.worker.js`
- Model / temperature: `wrangler.toml` `[vars]`; override in Cloudflare dashboard or `wrangler secret` is not used for those (vars are visible; for production you can move model to secret if needed).
