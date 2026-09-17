import { Link } from 'react-router-dom';
import { resolveProductImage } from '../utils/resolveProductImage.js';

export default function ProductCard({ product, reason }) {
  return (
    <Link
      to={`/product/${product.id}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-blush bg-white transition-shadow hover:shadow-lg"
    >
      <div className="aspect-[4/5] overflow-hidden bg-blush/40">
        <img
          src={resolveProductImage(product.image, product.name)}
          alt={product.name}
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          loading="lazy"
        />
      </div>
      <div className="flex flex-1 flex-col gap-1 p-4">
        <p className="text-xs uppercase tracking-wide text-clay">{product.category}</p>
        <h3 className="font-display text-lg leading-snug text-ink">{product.name}</h3>
        <p className="mt-auto pt-2 text-base font-medium text-ink">${product.price}</p>
        {reason && (
          <p className="mt-2 rounded-lg bg-cream px-3 py-2 text-sm italic text-ink/70">
            "{reason}"
          </p>
        )}
      </div>
    </Link>
  );
}
