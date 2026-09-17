import { Link } from 'react-router-dom';

const CATEGORY_BLURBS = {
  Dresses: 'Wrap, midi, maxi & more',
  Tops: 'Blouses, knits & basics',
  Bottoms: 'Trousers, denim & skirts',
  Outerwear: 'Coats, jackets & layers',
  Accessories: 'Bags, scarves & jewelry',
};

export default function CategoryNav({ categories }) {
  return (
    <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <h2 className="font-display text-2xl text-ink">Shop by Category</h2>
      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
        {categories.map((category) => (
          <Link
            key={category}
            to={`/shop?category=${encodeURIComponent(category)}`}
            className="flex flex-col items-center justify-center gap-1 rounded-2xl border border-blush bg-white px-4 py-6 text-center transition-shadow hover:shadow-md"
          >
            <span className="font-display text-lg text-ink">{category}</span>
            <span className="text-xs text-ink/50">{CATEGORY_BLURBS[category] || ''}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
