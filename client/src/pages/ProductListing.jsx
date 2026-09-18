import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import FilterSidebar from '../components/FilterSidebar.jsx';
import ProductCard from '../components/ProductCard.jsx';
import { fetchCategories, fetchProducts, postSearch } from '../utils/api.js';

export default function ProductListing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  // Embedded AI search: a one-shot query, independent of the floating
  // widget's and /search page's own conversations (separate state, same
  // postSearch endpoint — no history is sent since each query here stands
  // on its own rather than chaining like a chat).
  const [aiInput, setAiInput] = useState('');
  const [aiResult, setAiResult] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState(null);

  const filters = useMemo(
    () => ({
      category: searchParams.get('category') || '',
      size: searchParams.get('size') || '',
      minPrice: searchParams.get('minPrice') || '',
      maxPrice: searchParams.get('maxPrice') || '',
    }),
    [searchParams]
  );

  useEffect(() => {
    fetchCategories().then((data) => setCategories(data.categories));
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchProducts(filters)
      .then((data) => setProducts(data.products))
      .finally(() => setLoading(false));
  }, [filters.category, filters.size, filters.minPrice, filters.maxPrice]);

  function handleFilterChange(next) {
    const params = {};
    Object.entries(next).forEach(([key, value]) => {
      if (value) params[key] = value;
    });
    setSearchParams(params);
  }

  async function handleAiSearch(e) {
    e.preventDefault();
    const trimmed = aiInput.trim();
    if (!trimmed || aiLoading) return;

    setAiLoading(true);
    setAiError(null);
    try {
      const result = await postSearch({ message: trimmed, history: [] });
      setAiResult(result);
    } catch (err) {
      setAiError(err.message);
      setAiResult(null);
    } finally {
      setAiLoading(false);
    }
  }

  function clearAiSearch() {
    setAiResult(null);
    setAiError(null);
    setAiInput('');
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <h1 className="font-display text-3xl text-ink">
        {filters.category || 'All Products'}
      </h1>

      <form onSubmit={handleAiSearch} className="mt-6 rounded-2xl border border-blush bg-white p-4 sm:p-5">
        <label htmlFor="ai-listing-search" className="text-xs font-semibold uppercase tracking-wide text-clay">
          Ask Aria
        </label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input
            id="ai-listing-search"
            value={aiInput}
            onChange={(e) => setAiInput(e.target.value)}
            placeholder="Try: &lsquo;something casual for a beach wedding&rsquo;"
            className="flex-1 rounded-full border border-blush px-4 py-2.5 text-sm outline-none focus:border-ink"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={aiLoading || !aiInput.trim()}
              className="flex-1 rounded-full bg-ink px-6 py-2.5 text-sm font-medium text-white disabled:opacity-40 sm:flex-none"
            >
              {aiLoading ? 'Searching…' : 'Search'}
            </button>
            {aiResult && (
              <button
                type="button"
                onClick={clearAiSearch}
                className="flex-1 rounded-full border border-blush px-4 py-2.5 text-sm text-ink/70 hover:border-ink hover:text-ink sm:flex-none"
              >
                Clear AI search
              </button>
            )}
          </div>
        </div>
        {aiError && <p className="mt-2 text-sm text-red-600">{aiError}</p>}
      </form>

      <div className="mt-8 flex flex-col gap-8 sm:flex-row">
        <FilterSidebar categories={categories} filters={filters} onChange={handleFilterChange} />
        <div className="flex-1">
          {aiResult ? (
            <div>
              <div className="flex items-start justify-between gap-4 rounded-2xl bg-cream px-4 py-3">
                <p className="text-sm text-ink">{aiResult.message}</p>
              </div>
              {aiResult.products.length > 0 ? (
                <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
                  {aiResult.products.map((product) => (
                    <ProductCard key={product.id} product={product} reason={product.reason} />
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-ink/50">
                  Try rephrasing, or use the filters below to browse the full catalog.
                </p>
              )}
            </div>
          ) : loading ? (
            <p className="text-sm text-ink/50">Loading products&hellip;</p>
          ) : products.length === 0 ? (
            <p className="text-sm text-ink/50">No products match those filters.</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              {products.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
