const SIZES = ['XS', 'S', 'M', 'L', 'XL'];
const PRICE_BRACKETS = [
  { label: 'Any price', min: '', max: '' },
  { label: 'Under $50', min: '', max: '50' },
  { label: '$50 – $100', min: '50', max: '100' },
  { label: 'Over $100', min: '100', max: '' },
];

export default function FilterSidebar({ categories, filters, onChange }) {
  function update(patch) {
    onChange({ ...filters, ...patch });
  }

  return (
    <aside className="w-full shrink-0 space-y-6 sm:w-56">
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">
          Category
        </h3>
        <div className="flex flex-col gap-1">
          <button
            className={`text-left text-sm ${!filters.category ? 'font-semibold text-clay' : 'text-ink/70'}`}
            onClick={() => update({ category: '' })}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              className={`text-left text-sm ${filters.category === c ? 'font-semibold text-clay' : 'text-ink/70'}`}
              onClick={() => update({ category: c })}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">Price</h3>
        <div className="flex flex-col gap-1">
          {PRICE_BRACKETS.map((b) => (
            <button
              key={b.label}
              className={`text-left text-sm ${
                filters.minPrice === b.min && filters.maxPrice === b.max
                  ? 'font-semibold text-clay'
                  : 'text-ink/70'
              }`}
              onClick={() => update({ minPrice: b.min, maxPrice: b.max })}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">Size</h3>
        <div className="flex flex-wrap gap-2">
          <button
            className={`rounded-full border px-3 py-1 text-xs ${
              !filters.size ? 'border-ink bg-ink text-white' : 'border-blush text-ink/70'
            }`}
            onClick={() => update({ size: '' })}
          >
            All
          </button>
          {SIZES.map((s) => (
            <button
              key={s}
              className={`rounded-full border px-3 py-1 text-xs ${
                filters.size === s ? 'border-ink bg-ink text-white' : 'border-blush text-ink/70'
              }`}
              onClick={() => update({ size: s })}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
