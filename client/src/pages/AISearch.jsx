import AISearchChat from '../components/AISearchChat.jsx';

export default function AISearch() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <h1 className="font-display text-3xl text-ink">Ask Aria</h1>
      <p className="mt-2 text-sm text-ink/60">
        Describe the occasion, style, season, or budget you have in mind &mdash; Aria will
        shortlist real pieces from the collection and explain why each one fits.
      </p>
      <div className="mt-6">
        <AISearchChat />
      </div>
    </div>
  );
}
