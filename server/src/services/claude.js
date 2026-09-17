import Anthropic from '@anthropic-ai/sdk';
import { getProducts } from '../data/products.js';

const MODEL = process.env.CLAUDE_MODEL || 'claude-sonnet-4-6';

let client = null;
function getClient() {
  if (!process.env.ANTHROPIC_API_KEY) {
    throw new Error(
      'ANTHROPIC_API_KEY is not set. Add it to server/.env to use the AI search agent.'
    );
  }
  if (!client) {
    client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  }
  return client;
}

// Trim each product to the fields the agent actually needs to reason about.
// Keeps the prompt small and stops Claude from inventing fields like SKUs.
function catalogForPrompt() {
  return getProducts().map((p) => ({
    id: p.id,
    name: p.name,
    category: p.category,
    subcategory: p.subcategory,
    price: p.price,
    sizes: p.sizes,
    colors: p.colors,
    material: p.material,
    tags: p.tags,
    description: p.shortDescription,
  }));
}

const SYSTEM_PROMPT = `You are Aria, a friendly and knowledgeable personal shopping assistant for a women's clothing e-commerce store.

You help customers find products by understanding their intent in plain language: occasion, style, weather/season, budget, fit preference, and color mood. You do NOT rely on the customer clicking filters.

Rules you must always follow:
1. Only recommend products that exist in the CATALOG provided below. Never invent products, IDs, prices, or attributes. Every "id" you return must be copied exactly from the catalog.
2. Read the customer's full conversation history, not just their latest message. Treat later messages as refinements of earlier ones (e.g. "show me something cheaper", "more formal", "I don't like that color") unless they clearly start a new request.
3. If the request is too vague or ambiguous to produce a good shortlist (e.g. no occasion, style, or category signal at all, such as "help me find clothes"), do NOT guess. Instead ask exactly ONE short, specific clarifying question, and return an empty products array.
4. Otherwise, return a ranked shortlist of 2-5 products (fewer if the catalog genuinely has fewer good matches) that best fit the request, ordered best-match first.
5. For each recommended product, write a short (1-2 sentence) "reason" explaining specifically why it fits THIS customer's request — reference the occasion, style, season, price, or fit signal you matched on. Do not write generic marketing copy.
6. Write a short, warm "message" (1-3 sentences) to the customer summarizing your picks or, if asking a clarifying question, framing that question.
7. Always call the recommend_products tool exactly once with your full response. Do not respond in plain text.

CATALOG (JSON array of available products):
${JSON.stringify(catalogForPrompt())}`;

const RECOMMEND_TOOL = {
  name: 'recommend_products',
  description:
    'Return the shopping assistant reply: a conversational message plus a ranked list of catalog product recommendations (or a clarifying question with no products).',
  input_schema: {
    type: 'object',
    properties: {
      message: {
        type: 'string',
        description:
          "Warm, conversational reply to the customer. If asking a clarifying question, this IS the question.",
      },
      isClarifyingQuestion: {
        type: 'boolean',
        description: 'True if "message" is a clarifying question and no products are being recommended yet.',
      },
      products: {
        type: 'array',
        description: 'Ranked shortlist, best match first. Empty if isClarifyingQuestion is true.',
        items: {
          type: 'object',
          properties: {
            id: {
              type: 'string',
              description: 'Exact product id from the catalog, e.g. "P001".',
            },
            reason: {
              type: 'string',
              description: '1-2 sentences on why this product fits the customer\'s specific request.',
            },
          },
          required: ['id', 'reason'],
        },
      },
    },
    required: ['message', 'isClarifyingQuestion', 'products'],
  },
};

// history: array of { role: 'user' | 'assistant', content: string }
export async function getShoppingRecommendations({ message, history = [] }) {
  const anthropic = getClient();

  const messages = [
    ...history.map((h) => ({ role: h.role, content: h.content })),
    { role: 'user', content: message },
  ];

  const response = await anthropic.messages.create({
    model: MODEL,
    max_tokens: 1500,
    system: SYSTEM_PROMPT,
    tools: [RECOMMEND_TOOL],
    tool_choice: { type: 'tool', name: 'recommend_products' },
    messages,
  });

  const toolUse = response.content.find((block) => block.type === 'tool_use');
  if (!toolUse) {
    throw new Error('AI agent did not return a structured recommendation.');
  }

  const { message: reply, isClarifyingQuestion, products: picks } = toolUse.input;

  // Defend against a hallucinated id slipping through despite the system prompt.
  const catalogIds = new Set(getProducts().map((p) => p.id));
  const validPicks = (picks || []).filter((pick) => catalogIds.has(pick.id));

  const products = validPicks
    .map((pick) => {
      const product = getProducts().find((p) => p.id === pick.id);
      return { ...product, reason: pick.reason };
    })
    .filter(Boolean);

  return {
    message: reply,
    isClarifyingQuestion: Boolean(isClarifyingQuestion),
    products,
  };
}
