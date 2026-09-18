import { useRef, useState } from 'react';
import ProductCard from './ProductCard.jsx';
import { postSearch } from '../utils/api.js';

const STARTER_PROMPTS = [
  'Something for a beach wedding, under $100',
  'Cozy office outfit for winter',
  'Edgy date night look',
  'Breathable travel outfit for a hot vacation',
];

const WELCOME = {
  role: 'assistant',
  content:
    "Hi, I'm Aria, your personal shopping assistant. Tell me about the occasion, style, season, or budget you have in mind and I'll pull some pieces for you.",
  products: [],
};

export default function AISearchChat() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);
  const messageRefs = useRef([]);

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    });
  }

  // Brings a message's text bubble to the top of the chat window instead of
  // jumping straight to the bottom. This way, when a reply also includes
  // recommended products, the customer reads the message first (e.g. "that
  // exact style isn't in the collection, but here's what's close") and has
  // to scroll to see the products, rather than everything appearing at once.
  function scrollMessageToTop(idx) {
    requestAnimationFrame(() => {
      messageRefs.current[idx]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMessage = { role: 'user', content: trimmed };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setInput('');
    setError(null);
    setLoading(true);
    scrollToBottom();

    // Only role/content is sent as conversational history — the AI reads
    // this to resolve refinements like "show me something cheaper".
    const history = messages
      .filter((m) => m !== WELCOME)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const result = await postSearch({ message: trimmed, history });
      const updated = [
        ...nextMessages,
        {
          role: 'assistant',
          content: result.message,
          products: result.products,
          isClarifyingQuestion: result.isClarifyingQuestion,
        },
      ];
      setMessages(updated);
      setLoading(false);
      scrollMessageToTop(updated.length - 1);
    } catch (err) {
      setError(err.message);
      setLoading(false);
      scrollToBottom();
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    sendMessage(input);
  }

  return (
    <div className="flex flex-col rounded-2xl border border-blush bg-white">
      <div ref={scrollRef} className="flex max-h-[65vh] flex-col gap-6 overflow-y-auto p-4 sm:p-6">
        {messages.map((message, idx) => (
          <div
            key={idx}
            ref={(el) => (messageRefs.current[idx] = el)}
            // scroll-mt so the sticky site header doesn't cover this message
            // when scrollIntoView falls back to scrolling the whole page
            // (happens when the chat itself is short enough not to scroll).
            className={`scroll-mt-24 ${message.role === 'user' ? 'self-end' : 'self-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm sm:max-w-md ${
                message.role === 'user'
                  ? 'ml-auto bg-ink text-white'
                  : 'bg-cream text-ink'
              }`}
            >
              {message.content}
            </div>

            {message.products && message.products.length > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                {message.products.map((product) => (
                  <ProductCard key={product.id} product={product} reason={product.reason} />
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="self-start rounded-2xl bg-cream px-4 py-3 text-sm text-ink/50">
            Aria is thinking&hellip;
          </div>
        )}

        {error && (
          <div className="self-start rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}
      </div>

      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 border-t border-blush px-4 py-3 sm:px-6">
          {STARTER_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => sendMessage(prompt)}
              className="rounded-full border border-blush px-3 py-1.5 text-xs text-ink/70 hover:border-ink hover:text-ink"
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-blush p-4 sm:p-6">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe what you're looking for..."
          className="flex-1 rounded-full border border-blush px-4 py-2 text-sm outline-none focus:border-ink"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-full bg-ink px-6 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  );
}
