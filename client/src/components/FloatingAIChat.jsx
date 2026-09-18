import { useEffect, useRef, useState } from 'react';
import ProductMiniCard from './ProductMiniCard.jsx';
import { useAiChat } from '../hooks/useAiChat.js';

const WELCOME = {
  role: 'assistant',
  content: "Hi! Looking for something specific? Tell me the occasion, style, or vibe you're going for.",
  products: [],
};

// Site-wide floating entry point to the same shopping agent used on the
// dedicated /search page and the product-detail widget. Mounted once at the
// App layout level (outside <Routes>) so it persists across navigation and
// keeps its own conversation, separate from those other surfaces.
export default function FloatingAIChat() {
  const { messages, loading, error, sendMessage } = useAiChat(WELCOME);
  const [input, setInput] = useState('');
  const [open, setOpen] = useState(false);
  const [hasOpenedOnce, setHasOpenedOnce] = useState(false);
  const [scrolledPastHalf, setScrolledPastHalf] = useState(false);
  const scrollRef = useRef(null);

  // Gentle nudge: a small dot appears once the visitor has scrolled past the
  // halfway point of the page, as long as they haven't opened the widget
  // yet. It never reappears once they've opened it at least once.
  useEffect(() => {
    function handleScroll() {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollable <= 0) return;
      if (window.scrollY / scrollable >= 0.5) {
        setScrolledPastHalf(true);
      }
    }
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    });
  }

  function toggleOpen() {
    setOpen((v) => !v);
    setHasOpenedOnce(true);
  }

  async function handleSend(text) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setInput('');
    scrollToBottom();
    await sendMessage(trimmed);
    scrollToBottom();
  }

  function handleSubmit(e) {
    e.preventDefault();
    handleSend(input);
  }

  const showDot = scrolledPastHalf && !hasOpenedOnce;

  return (
    <>
      {/* Chat panel: always mounted, visibility/animation driven purely by
          classes so open/close is a smooth scale+fade with no mount delay. */}
      <div
        role="dialog"
        aria-label="Ask Aria"
        aria-hidden={!open}
        className={`fixed inset-x-0 bottom-0 z-50 flex h-[70vh] origin-bottom-right flex-col overflow-hidden rounded-t-2xl border border-blush bg-white shadow-2xl transition-all duration-200 sm:inset-x-auto sm:bottom-24 sm:right-6 sm:h-[500px] sm:w-[380px] sm:rounded-2xl ${
          open ? 'scale-100 opacity-100' : 'pointer-events-none scale-95 opacity-0'
        }`}
      >
        <div className="flex items-center justify-between border-b border-blush px-4 py-3">
          <p className="font-display text-base text-ink">Ask Aria</p>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Minimize chat"
            className="flex h-7 w-7 items-center justify-center rounded-full text-ink/50 hover:bg-cream hover:text-ink"
          >
            &times;
          </button>
        </div>

        <div ref={scrollRef} className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
          {messages.map((message, idx) => (
            <div key={idx} className={message.role === 'user' ? 'self-end' : 'self-start'}>
              <div
                className={`max-w-[90%] rounded-2xl px-3 py-2 text-sm ${
                  message.role === 'user' ? 'ml-auto bg-ink text-white' : 'bg-cream text-ink'
                }`}
              >
                {message.content}
              </div>

              {message.products && message.products.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  {message.products.map((product) => (
                    <ProductMiniCard key={product.id} product={product} reason={product.reason} />
                  ))}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="self-start rounded-2xl bg-cream px-3 py-2 text-sm text-ink/50">
              Aria is thinking&hellip;
            </div>
          )}

          {error && (
            <div className="self-start rounded-2xl bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="flex gap-2 border-t border-blush p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe what you're looking for..."
            className="flex-1 rounded-full border border-blush px-3 py-2 text-sm outline-none focus:border-ink"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="rounded-full bg-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </div>

      {/* Floating action button. Hidden on mobile while open: the panel is
          a full-width bottom sheet there, flush to the same corner, so this
          button would otherwise sit on top of the chat input. The panel's
          own header close button covers that case; on desktop the panel
          sits with a gap above the FAB, so no overlap and it can stay. */}
      <button
        type="button"
        onClick={toggleOpen}
        aria-label={open ? 'Close Ask Aria chat' : 'Open Ask Aria chat'}
        className={`fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 z-50 h-14 w-14 items-center justify-center rounded-full bg-ink text-white shadow-xl transition-transform hover:scale-105 sm:bottom-6 sm:right-6 ${
          open ? 'hidden sm:flex' : 'flex'
        }`}
      >
        {open ? (
          <span className="text-2xl leading-none">&times;</span>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6">
            <path
              d="M4 4h16v12H8l-4 4V4z"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
        {showDot && (
          <span className="absolute right-0 top-0 h-3 w-3 rounded-full bg-clay ring-2 ring-cream" />
        )}
      </button>
    </>
  );
}
