import { createContext, useContext, useMemo, useState } from 'react';

const CartContext = createContext(null);

export function CartProvider({ children }) {
  const [items, setItems] = useState([]); // { product, size, qty }

  function addToCart(product, size, qty = 1) {
    setItems((prev) => {
      const existing = prev.find((i) => i.product.id === product.id && i.size === size);
      if (existing) {
        return prev.map((i) =>
          i.product.id === product.id && i.size === size ? { ...i, qty: i.qty + qty } : i
        );
      }
      return [...prev, { product, size, qty }];
    });
  }

  function removeFromCart(productId, size) {
    setItems((prev) => prev.filter((i) => !(i.product.id === productId && i.size === size)));
  }

  function updateQty(productId, size, qty) {
    if (qty < 1) return removeFromCart(productId, size);
    setItems((prev) =>
      prev.map((i) => (i.product.id === productId && i.size === size ? { ...i, qty } : i))
    );
  }

  function clearCart() {
    setItems([]);
  }

  const totalItems = useMemo(() => items.reduce((sum, i) => sum + i.qty, 0), [items]);
  const subtotal = useMemo(
    () => items.reduce((sum, i) => sum + i.product.price * i.qty, 0),
    [items]
  );

  const value = { items, addToCart, removeFromCart, updateQty, clearCart, totalItems, subtotal };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error('useCart must be used within a CartProvider');
  return ctx;
}
