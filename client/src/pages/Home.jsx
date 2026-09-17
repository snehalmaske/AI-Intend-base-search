import { useEffect, useState } from 'react';
import Hero from '../components/Hero.jsx';
import CategoryNav from '../components/CategoryNav.jsx';
import ProductCard from '../components/ProductCard.jsx';
import { fetchCategories, fetchProducts } from '../utils/api.js';

export default function Home() {
  const [categories, setCategories] = useState([]);
  const [featured, setFeatured] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchCategories(), fetchProducts()])
      .then(([catData, productData]) => {
        setCategories(catData.categories);
        setFeatured(productData.products.slice(0, 8));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <Hero />
      {categories.length > 0 && <CategoryNav categories={categories} />}

      <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-2xl text-ink">Featured Pieces</h2>
        </div>
        {loading ? (
          <p className="mt-6 text-sm text-ink/50">Loading products&hellip;</p>
        ) : (
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
            {featured.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
