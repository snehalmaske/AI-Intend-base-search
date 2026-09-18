import { useState } from 'react';
import { postSearch } from '../utils/api.js';

// Shared conversational state for the AI shopping agent. Both the full-page
// chat (AISearchChat) and the site-wide floating widget (FloatingAIChat) use
// this hook so the fetch/history logic lives in exactly one place — each
// caller creates its own instance, so their conversations never mix.
export function useAiChat(welcomeMessage) {
  const [messages, setMessages] = useState(welcomeMessage ? [welcomeMessage] : []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Returns the index of the new assistant message on success (handy for
  // scrolling it into view), or null on failure.
  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return null;

    const userMessage = { role: 'user', content: trimmed };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setError(null);
    setLoading(true);

    // Only role/content is sent as conversational history — the AI reads
    // this to resolve refinements like "show me something cheaper".
    const history = messages
      .filter((m) => m !== welcomeMessage)
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
      return updated.length - 1;
    } catch (err) {
      setError(err.message);
      setLoading(false);
      return null;
    }
  }

  return { messages, loading, error, sendMessage };
}
