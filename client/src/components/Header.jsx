import { useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useCart } from '../context/CartContext.jsx';

const navLinks = [{ to: '/shop', label: 'Shop' }];

export default function Header() {
  const { totalItems } = useCart();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-blush bg-cream/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/" className="whitespace-nowrap font-display text-xl tracking-wide text-ink sm:text-2xl">
          Maison Vireo
        </Link>

        <nav className="hidden items-center gap-8 sm:flex">
          {navLinks.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `text-sm font-medium uppercase tracking-wide transition-colors ${
                  isActive ? 'text-clay' : 'text-ink/70 hover:text-ink'
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
          <Link to="/cart" className="relative text-sm font-medium uppercase tracking-wide text-ink/70 hover:text-ink">
            Cart
            {totalItems > 0 && (
              <span className="absolute -right-3 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-clay text-[11px] text-white">
                {totalItems}
              </span>
            )}
          </Link>
        </nav>

        <div className="flex items-center gap-4 sm:hidden">
          <Link to="/cart" className="relative text-sm font-medium">
            Cart
            {totalItems > 0 && (
              <span className="absolute -right-3 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-clay text-[11px] text-white">
                {totalItems}
              </span>
            )}
          </Link>
          <button
            aria-label="Toggle menu"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-blush"
          >
            <span className="text-lg">{menuOpen ? '×' : '☰'}</span>
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav className="flex flex-col border-t border-blush bg-cream px-4 py-3 sm:hidden">
          {navLinks.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              onClick={() => setMenuOpen(false)}
              className="py-2 text-sm font-medium uppercase tracking-wide text-ink/80"
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}
