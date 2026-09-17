export default function Footer() {
  return (
    <footer className="border-t border-blush bg-cream">
      <div className="mx-auto max-w-6xl px-4 py-10 text-sm text-ink/60 sm:px-6">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <p className="font-display text-lg text-ink">Aria</p>
          <p>Women's clothing, found by description &mdash; not filters.</p>
        </div>
        <p className="mt-6 text-center text-xs text-ink/40 sm:text-left">
          &copy; {new Date().getFullYear()} Aria. Demo storefront for AI-powered product discovery.
        </p>
      </div>
    </footer>
  );
}
