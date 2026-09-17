import { Router } from 'express';
import { getProducts, getProductById } from '../data/products.js';

const router = Router();

// GET /api/products?category=Dresses&size=M&color=Black&minPrice=0&maxPrice=200
router.get('/', (req, res) => {
  const { category, size, color, minPrice, maxPrice } = req.query;
  let products = getProducts();

  if (category) {
    products = products.filter(
      (p) => p.category.toLowerCase() === String(category).toLowerCase()
    );
  }
  if (size) {
    products = products.filter((p) => p.sizes.includes(size));
  }
  if (color) {
    const wanted = String(color).toLowerCase();
    products = products.filter((p) =>
      p.colors.some((c) => c.toLowerCase().includes(wanted))
    );
  }
  if (minPrice) {
    products = products.filter((p) => p.price >= Number(minPrice));
  }
  if (maxPrice) {
    products = products.filter((p) => p.price <= Number(maxPrice));
  }

  res.json({ products, total: products.length });
});

router.get('/categories', (_req, res) => {
  const categories = [...new Set(getProducts().map((p) => p.category))];
  res.json({ categories });
});

router.get('/:id', (req, res) => {
  const product = getProductById(req.params.id);
  if (!product) {
    return res.status(404).json({ error: 'Product not found' });
  }
  res.json({ product });
});

export default router;
