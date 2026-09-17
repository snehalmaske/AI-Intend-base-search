const BASE = '/api';

async function handle(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export async function fetchProducts(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const res = await fetch(`${BASE}/products?${params.toString()}`);
  return handle(res);
}

export async function fetchCategories() {
  const res = await fetch(`${BASE}/products/categories`);
  return handle(res);
}

export async function fetchProduct(id) {
  const res = await fetch(`${BASE}/products/${id}`);
  return handle(res);
}

export async function postSearch({ message, history }) {
  const res = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  });
  return handle(res);
}
