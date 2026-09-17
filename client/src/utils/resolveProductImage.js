// Maps a product's `image` path from products.json (e.g.
// "/images/products/p001-wrap-midi-dress.jpg") to whatever file actually
// lives in src/assets/products/ with that same basename, regardless of
// extension. This lets scripts/generate-product-images.js write real .jpg
// photos or a .svg placeholder without any other code needing to change.
const modules = import.meta.glob('/src/assets/products/*', {
  eager: true,
  import: 'default',
});

const imagesByBasename = {};
for (const [filePath, url] of Object.entries(modules)) {
  const basename = filePath.split('/').pop().replace(/\.[^/.]+$/, '');
  imagesByBasename[basename] = url;
}

function escapeXml(str) {
  return str.replace(
    /[<>&'"]/g,
    (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[c])
  );
}

// Shown only if generate-images hasn't been run yet at all (no file, not
// even a placeholder, exists for this product).
function genericPlaceholder(name) {
  const safeName = escapeXml(name || 'Product image');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="750">
  <rect width="100%" height="100%" fill="#f3ede4"/>
  <rect x="16" y="16" width="568" height="718" fill="none" stroke="#c9b8a8" stroke-width="1" stroke-dasharray="8,6"/>
  <text x="50%" y="47%" font-family="Georgia, serif" font-size="24" fill="#8a7461" text-anchor="middle">${safeName}</text>
  <text x="50%" y="54%" font-family="Arial, sans-serif" font-size="14" fill="#8a7461" text-anchor="middle">Run "npm run generate-images"</text>
</svg>`;
  const base64 =
    typeof window !== 'undefined' && window.btoa
      ? window.btoa(svg)
      : Buffer.from(svg).toString('base64');
  return `data:image/svg+xml;base64,${base64}`;
}

export function resolveProductImage(imagePath, productName = '') {
  const basename = (imagePath || '').split('/').pop().replace(/\.[^/.]+$/, '');
  return imagesByBasename[basename] || genericPlaceholder(productName);
}
