import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import productsRouter from './routes/products.js';
import searchRouter from './routes/search.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CLIENT_DIST = path.join(__dirname, '../../client/dist');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

app.get('/api/health', (_req, res) => res.json({ status: 'ok' }));
app.use('/api/products', productsRouter);
app.use('/api/search', searchRouter);

// In production this single server also serves the built React app
// (client/dist), so the whole site is one deployment on one origin — no
// separate frontend host or CORS wiring needed. In local dev, the client
// runs on its own Vite server instead, so client/dist won't exist yet;
// express.static and the catch-all below simply no-op until it's built.
app.use(express.static(CLIENT_DIST));
app.get(/^(?!\/api).*/, (_req, res) => {
  res.sendFile(path.join(CLIENT_DIST, 'index.html'), (err) => {
    if (err) res.status(404).send('Run "npm run build" to generate the client first.');
  });
});

app.listen(PORT, () => {
  console.log(`API server listening on http://localhost:${PORT}`);
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn(
      'ANTHROPIC_API_KEY is not set — the AI search agent will return an error until you add it to server/.env'
    );
  }
});
