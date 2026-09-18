import { Route, Routes } from 'react-router-dom';
import Header from './components/Header.jsx';
import Footer from './components/Footer.jsx';
import FloatingAIChat from './components/FloatingAIChat.jsx';
import Home from './pages/Home.jsx';
import ProductListing from './pages/ProductListing.jsx';
import ProductDetail from './pages/ProductDetail.jsx';
import Cart from './pages/Cart.jsx';
import AISearch from './pages/AISearch.jsx';

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      {/* Extra bottom space on mobile so the floating chat FAB always floats
          over empty space instead of sitting on top of a page's bottom-most
          button (e.g. Add to Cart). Desktop doesn't need it: the FAB is a
          small corner button and primary CTAs there aren't full-width. */}
      <main className="flex-1 pb-24 sm:pb-0">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/shop" element={<ProductListing />} />
          <Route path="/product/:id" element={<ProductDetail />} />
          <Route path="/cart" element={<Cart />} />
          <Route path="/search" element={<AISearch />} />
        </Routes>
      </main>
      <Footer />
      <FloatingAIChat />
    </div>
  );
}
