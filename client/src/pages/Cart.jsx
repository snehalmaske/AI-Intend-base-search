import { Link } from 'react-router-dom';
import { resolveProductImage } from '../utils/resolveProductImage.js';
import { useCart } from '../context/CartContext.jsx';

export default function Cart() {
  const { items, updateQty, removeFromCart, subtotal } = useCart();

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center">
        <h1 className="font-display text-2xl text-ink">Your cart is empty</h1>
        <p className="mt-2 text-sm text-ink/60">
          Let Aria help you find something, or browse the collection.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link to="/search" className="rounded-full bg-ink px-6 py-2 text-sm text-white">
            Ask Aria
          </Link>
          <Link to="/shop" className="rounded-full border border-ink px-6 py-2 text-sm text-ink">
            Browse Shop
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <h1 className="font-display text-3xl text-ink">Your Cart</h1>

      <div className="mt-8 flex flex-col gap-4">
        {items.map(({ product, size, qty }) => (
          <div
            key={`${product.id}-${size}`}
            className="flex flex-wrap items-center gap-4 rounded-2xl border border-blush bg-white p-4"
          >
            <div className="h-24 w-20 shrink-0 overflow-hidden rounded-xl bg-blush/40">
              <img
                src={resolveProductImage(product.image, product.name)}
                alt={product.name}
                className="h-full w-full object-cover"
              />
            </div>
            <div className="min-w-[8rem] flex-1 basis-32">
              <p className="font-display text-lg text-ink">{product.name}</p>
              <p className="text-sm text-ink/50">Size {size}</p>
              <p className="mt-1 text-sm font-medium text-ink">${product.price}</p>
            </div>
            <div className="ml-auto flex items-center gap-3">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => updateQty(product.id, size, qty - 1)}
                  className="h-8 w-8 rounded-full border border-blush text-ink"
                >
                  &minus;
                </button>
                <span className="w-6 text-center text-sm">{qty}</span>
                <button
                  onClick={() => updateQty(product.id, size, qty + 1)}
                  className="h-8 w-8 rounded-full border border-blush text-ink"
                >
                  +
                </button>
              </div>
              <button
                onClick={() => removeFromCart(product.id, size)}
                className="whitespace-nowrap text-xs uppercase tracking-wide text-ink/40 hover:text-ink"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-between rounded-2xl border border-blush bg-white p-6">
        <span className="font-display text-xl text-ink">Subtotal</span>
        <span className="font-display text-xl text-ink">${subtotal.toFixed(2)}</span>
      </div>

      <button
        onClick={() => alert('Checkout is not implemented in this demo.')}
        className="mt-6 w-full rounded-full bg-ink px-8 py-3 text-sm font-medium uppercase tracking-wide text-white sm:w-auto"
      >
        Checkout
      </button>
    </div>
  );
}
