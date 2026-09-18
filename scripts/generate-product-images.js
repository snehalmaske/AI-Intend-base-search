#!/usr/bin/env node
// Generates a real product photo for every entry in data/products.json using
// the OpenAI Images API (gpt-image-1) or the Stability AI API, and saves it
// to client/src/assets/products/<filename-from-products.json>.
//
// Usage: npm run generate-images   (reads OPENAI_API_KEY / STABILITY_API_KEY from .env)
//
// Idempotent: any product whose image file already exists is skipped, so
// re-running only pays for images that are still missing.
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const PRODUCTS_PATH = path.join(ROOT, 'data/products.json');
const OUTPUT_DIR = path.join(ROOT, 'client/src/assets/products');

const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const STABILITY_API_KEY = process.env.STABILITY_API_KEY;

function buildPrompt(product) {
  const colors = product.colors.join(' / ');
  return (
    `Professional e-commerce product photo of a ${colors} ${product.material} ${product.name}. ` +
    `${product.longDescription} ` +
    `Shot on a plain white background with soft studio lighting, high resolution, centered composition, ` +
    `no models, no text, no watermark, no logos.`
  );
}

function filenameFor(product) {
  return path.basename(product.image);
}

function placeholderPathFor(outputPath) {
  return outputPath.replace(/\.(jpe?g|png)$/i, '.svg');
}

async function generateWithOpenAI(prompt) {
  const res = await fetch('https://api.openai.com/v1/images/generations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: 'gpt-image-1',
      prompt,
      size: '1024x1024',
      n: 1,
    }),
  });
  if (!res.ok) {
    throw new Error(`OpenAI Images API error ${res.status}: ${await res.text()}`);
  }
  const data = await res.json();
  return Buffer.from(data.data[0].b64_json, 'base64');
}

async function generateWithStability(prompt) {
  const form = new FormData();
  form.append('prompt', prompt);
  form.append('output_format', 'jpeg');
  form.append('aspect_ratio', '1:1');

  const res = await fetch('https://api.stability.ai/v2beta/stable-image/generate/core', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${STABILITY_API_KEY}`,
      Accept: 'image/*',
    },
    body: form,
  });
  if (!res.ok) {
    throw new Error(`Stability API error ${res.status}: ${await res.text()}`);
  }
  return Buffer.from(await res.arrayBuffer());
}

function escapeXml(str) {
  return str.replace(/[<>&'"]/g, (c) => ({
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
    "'": '&apos;',
    '"': '&quot;',
  })[c]);
}

// Clearly-labeled fallback so the storefront still renders when no image
// API key is configured. Written as .svg since it needs no image codec;
// the frontend's image resolver matches products to files by basename, so
// the extension doesn't matter.
function writePlaceholder(outputPath, product) {
  const bg = '#f3ede4';
  const fg = '#8a7461';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
  <rect width="100%" height="100%" fill="${bg}"/>
  <rect x="24" y="24" width="976" height="976" fill="none" stroke="${fg}" stroke-width="2" stroke-dasharray="10,8"/>
  <text x="50%" y="45%" font-family="Georgia, serif" font-size="40" fill="${fg}" text-anchor="middle">${escapeXml(product.name)}</text>
  <text x="50%" y="53%" font-family="Arial, sans-serif" font-size="26" fill="${fg}" text-anchor="middle" font-weight="bold">PLACEHOLDER IMAGE</text>
  <text x="50%" y="59%" font-family="Arial, sans-serif" font-size="16" fill="${fg}" text-anchor="middle">Add OPENAI_API_KEY or STABILITY_API_KEY to .env, then run</text>
  <text x="50%" y="63%" font-family="Arial, sans-serif" font-size="16" fill="${fg}" text-anchor="middle">"npm run generate-images"</text>
</svg>`;
  const svgPath = placeholderPathFor(outputPath);
  fs.writeFileSync(svgPath, svg, 'utf-8');
}

async function main() {
  const products = JSON.parse(fs.readFileSync(PRODUCTS_PATH, 'utf-8'));
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const hasOpenAI = Boolean(OPENAI_API_KEY);
  const hasStability = Boolean(STABILITY_API_KEY);

  if (!hasOpenAI && !hasStability) {
    console.warn(
      'No OPENAI_API_KEY or STABILITY_API_KEY found in .env — generating labeled placeholder images instead.\n' +
        'Add a key to .env (see .env.example) and re-run "npm run generate-images" for real product photos.\n'
    );
  }

  let generated = 0;
  let skipped = 0;
  let placeholders = 0;

  for (const product of products) {
    const filename = filenameFor(product);
    const outputPath = path.join(OUTPUT_DIR, filename);
    const svgPath = placeholderPathFor(outputPath);
    const hasRealImage = fs.existsSync(outputPath);
    const hasPlaceholder = fs.existsSync(svgPath);

    // A real photo is done — never touch it. A placeholder only counts as
    // "done" if we still have no key to upgrade it with; otherwise this run
    // should replace it with a real photo.
    if (hasRealImage || (hasPlaceholder && !hasOpenAI && !hasStability)) {
      console.log(`skip   ${filename} (${hasRealImage ? 'real image' : 'placeholder'} already exists)`);
      skipped++;
      continue;
    }

    const prompt = buildPrompt(product);

    try {
      if (hasOpenAI) {
        console.log(`gen    ${filename} (OpenAI gpt-image-1)`);
        fs.writeFileSync(outputPath, await generateWithOpenAI(prompt));
        if (hasPlaceholder) fs.unlinkSync(svgPath);
        generated++;
      } else if (hasStability) {
        console.log(`gen    ${filename} (Stability AI)`);
        fs.writeFileSync(outputPath, await generateWithStability(prompt));
        if (hasPlaceholder) fs.unlinkSync(svgPath);
        generated++;
      } else {
        writePlaceholder(outputPath, product);
        console.log(`place  ${filename} (placeholder — no API key set)`);
        placeholders++;
      }
    } catch (err) {
      console.error(`FAILED ${filename}: ${err.message}`);
      if (!hasPlaceholder) writePlaceholder(outputPath, product);
      placeholders++;
    }
  }

  console.log(
    `\nDone. Generated: ${generated}, Skipped (existing): ${skipped}, Placeholders: ${placeholders}`
  );
}

main();
