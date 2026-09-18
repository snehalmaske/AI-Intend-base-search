import { Link } from 'react-router-dom';
import { resolveProductImage } from '../utils/resolveProductImage.js';

// Compact horizontal card for narrow spaces (the floating chat widget),
// where a grid of full ProductCards wouldn't fit.
export default function ProductMiniCard({ product, reason }) {
  return (
    <Link
      to={`/product/${product.id}`}
      className="flex gap-3 rounded-xl border border-blush bg-white p-2 transition-shadow hover:shadow-md"
    >
      <div className="h-16 w-14 shrink-0 overflow-hidden rounded-lg bg-blush/40">
        <img
          src={resolveProductImage(product.image, product.name)}
          alt={product.name}
          className="h-full w-full object-cover"
          loading="lazy"
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink">{product.name}</p>
        <p className="text-sm text-ink/60">${product.price}</p>
        {reason && <p className="mt-0.5 line-clamp-1 text-xs italic text-ink/50">{reason}</p>}
      </div>
    </Link>
  );
}
