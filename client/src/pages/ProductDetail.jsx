import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import SizeSelector from '../components/SizeSelector.jsx';
import { resolveProductImage } from '../utils/resolveProductImage.js';
import { fetchProduct } from '../utils/api.js';
import { useCart } from '../context/CartContext.jsx';

export default function ProductDetail() {
  const { id } = useParams();
  const { addToCart } = useCart();
  const [product, setProduct] = useState(null);
  const [size, setSize] = useState('');
  const [added, setAdded] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setProduct(null);
    setSize('');
    setAdded(false);
    fetchProduct(id)
      .then((data) => setProduct(data.product))
      .catch((err) => setError(err.message));
  }, [id]);

  if (error) return <p className="mx-auto max-w-3xl px-4 py-16 text-center text-ink/60">{error}</p>;
  if (!product) return <p className="mx-auto max-w-3xl px-4 py-16 text-center text-ink/40">Loading&hellip;</p>;

  function handleAddToCart() {
    if (!size) return;
    addToCart(product, size);
    setAdded(true);
    setTimeout(() => setAdded(false), 2000);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <Link to="/shop" className="text-sm text-ink/50 hover:text-ink">
        &larr; Back to shop
      </Link>

      <div className="mt-6 grid gap-10 sm:grid-cols-2">
        <div className="aspect-[4/5] overflow-hidden rounded-2xl bg-blush/40">
          <img
            src={resolveProductImage(product.image, product.name)}
            alt={product.name}
            className="h-full w-full object-cover"
          />
        </div>

        <div>
          <p className="text-xs uppercase tracking-wide text-clay">{product.category}</p>
          <h1 className="mt-1 font-display text-3xl text-ink">{product.name}</h1>
          <p className="mt-2 text-xl font-medium text-ink">${product.price}</p>

          <p className="mt-4 text-sm leading-relaxed text-ink/70">{product.longDescription}</p>
          <p className="mt-3 text-sm text-ink/50">Material: {product.material}</p>

          <div className="mt-6">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">
              Colors
            </p>
            <p className="text-sm text-ink/70">{product.colors.join(', ')}</p>
          </div>

          <div className="mt-6">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">
              Select size
            </p>
            <SizeSelector sizes={product.sizes} selected={size} onSelect={setSize} />
          </div>

          <button
            onClick={handleAddToCart}
            disabled={!size}
            // Capped width (not full-bleed) on mobile only, so this button's
            // right edge never sits under the floating chat FAB regardless
            // of scroll position — sm:w-auto makes the cap a no-op on
            // desktop, where the button already isn't full width.
            className="mt-8 w-[calc(100%-4rem)] rounded-full bg-ink px-8 py-3 text-sm font-medium uppercase tracking-wide text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40 sm:w-auto"
          >
            {added ? 'Added ✓' : size ? 'Add to Cart' : 'Select a size'}
          </button>
        </div>
      </div>
    </div>
  );
}
