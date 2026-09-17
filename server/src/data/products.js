import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PRODUCTS_PATH = join(__dirname, '../../../data/products.json');

let cache = null;

// Reads the shared data/products.json once and keeps it in memory.
// Re-reads on server restart, which is all this catalog size needs.
export function getProducts() {
  if (!cache) {
    const raw = readFileSync(PRODUCTS_PATH, 'utf-8');
    cache = JSON.parse(raw);
  }
  return cache;
}

export function getProductById(id) {
  return getProducts().find((p) => p.id === id) || null;
}
