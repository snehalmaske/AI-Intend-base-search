import { Link } from 'react-router-dom';

export default function Hero() {
  return (
    <section className="bg-gradient-to-b from-blush/60 to-cream px-4 py-16 text-center sm:py-24">
      
      <h1 className="mx-auto mt-4 max-w-2xl font-display text-4xl leading-tight text-ink sm:text-5xl">
        Tell us what you need. We'll find the fit.
      </h1>
      
      <p className="mx-auto mt-4 max-w-xl text-base text-ink/70">
        Skip the filters &mdash; describe the occasion, vibe, or budget in your own words and
        our stylist, Aria, will shortlist real pieces from the collection with reasons why.
      </p>
      <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <Link
          to="/search"
          className="w-full rounded-full bg-ink px-8 py-3 text-sm font-medium uppercase tracking-wide text-white transition-opacity hover:opacity-90 sm:w-auto"
        >
          Ask Aria ✨
        </Link>
        <Link
          to="/shop"
          className="w-full rounded-full border border-ink px-8 py-3 text-sm font-medium uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-white sm:w-auto"
        >
          Browse Collection
        </Link>
      </div>
    </section>
  );
}
