import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import FilterSidebar from '../components/FilterSidebar.jsx';
import ProductCard from '../components/ProductCard.jsx';
import { fetchCategories, fetchProducts } from '../utils/api.js';

export default function ProductListing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <h1 className="font-display text-3xl text-ink">
        {filters.category || 'All Products'}
      </h1>
      <div className="mt-8 flex flex-col gap-8 sm:flex-row">
        <FilterSidebar categories={categories} filters={filters} onChange={handleFilterChange} />
        <div className="flex-1">
          {loading ? (
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
