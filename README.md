# Maison Vireo — Women's Fashion, Found by Description

A women's clothing e-commerce storefront with an AI-powered, intent-based product
discovery agent. Instead of clicking filters, customers describe what they want
in plain language ("something for a beach wedding, under $100") and an AI
shopping assistant ("Aria") returns a ranked shortlist from the real catalog
with a reason for each pick, and can be refined conversationally ("cheaper",
"more formal", etc).

## Tech stack

- **Frontend:** React 18 + Vite + Tailwind CSS, React Router
- **Backend:** Node.js + Express (npm workspaces monorepo)
- **Data:** `data/products.json` — 30 real products, served directly (no database)
- **AI:** Claude API (`@anthropic-ai/sdk`) via Anthropic's tool-use feature, for
  structured, catalog-grounded recommendations

## Project structure

```
data/products.json              # single source of truth for the catalog
server/                         # Express API
  src/index.js                  # app entry
  src/routes/products.js        # GET /api/products, /api/products/:id, /categories
  src/routes/search.js          # POST /api/search  (AI shopping agent)
  src/services/claude.js        # Claude system prompt + tool-use call
  src/data/products.js          # reads data/products.json
client/                         # Vite + React storefront
  src/pages/                    # Home, ProductListing, ProductDetail, Cart, AISearch
  src/components/               # Header, Footer, ProductCard, AISearchChat, ...
  src/context/CartContext.jsx   # client-side cart state
  src/utils/resolveProductImage.js  # maps products.json image path -> generated asset
  src/assets/products/          # generated/placeholder product photos land here
scripts/generate-product-images.js  # image generation script (see below)
```

## Setup

```bash
npm install
npm run dev
```

This installs both workspaces (`client`, `server`) and starts:
- the Express API on `http://localhost:3001`
- the Vite dev server on `http://localhost:5173` (proxies `/api/*` to the server)

Open `http://localhost:5173`.

Without any API keys configured, the storefront, filters, cart, and product
pages all work immediately. Only the AI search agent needs a key (below), and
product photos fall back to labeled placeholders until you run the image
generation script.

## Adding your API keys

### 1. Claude API key (AI search agent)

```bash
cp server/.env.example server/.env
```

Edit `server/.env` and set:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at https://console.anthropic.com/settings/keys. The model used is
controlled by `CLAUDE_MODEL` in the same file (defaults to a Claude Sonnet
model) — change it there if that model name isn't available on your account.

Restart `npm run dev` after adding the key. Without it, `/api/search` returns
a clear 503 error and the chat UI surfaces that message instead of failing
silently.

### 2. Image generation key (product photos)

```bash
cp .env.example .env
```

Edit the repo-root `.env` and set **one** of:

```
OPENAI_API_KEY=sk-...       # uses gpt-image-1
STABILITY_API_KEY=sk-...    # uses Stability's stable-image/generate/core
```

Then generate real product photos for all 30 products:

```bash
npm run generate-images
```

This script (`scripts/generate-product-images.js`):
- Builds an image prompt per product from its name, category, colors,
  material, and long description.
- Saves each image to `client/src/assets/products/<filename-from-products.json>`
  (e.g. `p001-wrap-midi-dress.jpg`), so no other code needs to change.
- **Skips any product whose image file already exists** — safe to re-run
  after adding new products; you only pay for what's missing.
- Falls back to a clearly-labeled placeholder SVG per product if no image
  API key is set (or if a generation call fails), so the site still runs.

The frontend resolves each product's photo by filename via
`resolveProductImage.js`, matching on basename regardless of extension — so
it works whether a file is a generated `.jpg` or a placeholder `.svg`.

## How the AI search agent works

`POST /api/search` (`server/src/routes/search.js` → `server/src/services/claude.js`):

1. The full catalog (trimmed to the fields relevant for matching: name,
   category, price, sizes, colors, material, tags, description) is embedded
   in the system prompt, along with instructions for Claude to act as a
   personal shopping assistant.
2. The customer's message plus prior conversation turns are sent as the
   message history, so follow-ups like "show me something cheaper" or "more
   formal" are resolved as refinements of the earlier request.
3. Claude is forced to respond via a `recommend_products` tool call
   (`tool_choice`), which returns strict JSON: a conversational `message`, an
   `isClarifyingQuestion` flag, and a ranked `products` array of
   `{ id, reason }`.
4. The server cross-checks every returned `id` against the real catalog and
   drops anything that isn't an exact match, so the AI can never recommend a
   product that doesn't exist.
5. If the request is too vague (e.g. "help me find clothes"), the system
   prompt instructs Claude to ask exactly one clarifying question and return
   no products, rather than guessing.

The frontend (`AISearchChat.jsx`) renders the conversation as chat bubbles,
with each recommended product shown as a `ProductCard` including the AI's
stated reason for that pick.

## Other scripts

```bash
npm run build          # production build of the client
npm start              # run the production server (serves the built client + API on one port)
npm run dev:server     # run only the API, in dev mode
npm run dev:client     # run only the Vite dev server
```

## Deploying (Render)

In production, `server/src/index.js` also serves the built client
(`client/dist`) directly — one process, one URL, no separate frontend host or
CORS setup needed. `render.yaml` at the repo root configures this for
[Render](https://render.com)'s free tier:

1. Push this repo to GitHub (already done if you're reading this from there).
2. On [render.com](https://render.com), click **New +** → **Blueprint**, and
   connect this repository. Render reads `render.yaml` automatically.
3. When prompted, paste your `ANTHROPIC_API_KEY` — it's the only secret you
   need to supply; everything else in `render.yaml` is preconfigured.
4. Deploy. Render runs `npm install && npm run build` then `npm start`, and
   gives you a public URL (e.g. `https://maison-vireo.onrender.com`).

Notes:
- The free tier spins the service down after ~15 minutes idle, so the first
  request after a quiet period takes ~30-50s to wake up.
- Product images: `npm run generate-images` is a local dev-time script.
  If you want real photos live on the deployed site, run it locally first
  and commit the generated files in `client/src/assets/products/` before
  pushing — the build step bundles whatever's already committed there.
- `CLAUDE_MODEL` is already set in `render.yaml`. `PORT` doesn't need to be
  set at all — Render injects it automatically and the server already reads
  `process.env.PORT`.

## Extending the catalog

Add new entries to `data/products.json` following the existing shape
(`id`, `category`, `tags.{occasion,style,season,fit,colorMood}`, etc — the
`tags` object is what the AI agent matches against), then run
`npm run generate-images` to generate photos for just the new products.
