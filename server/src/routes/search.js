import { Router } from 'express';
import { getShoppingRecommendations } from '../services/claude.js';

const router = Router();

// POST /api/search  { message: string, history?: [{role, content}] }
router.post('/', async (req, res) => {
  const { message, history } = req.body || {};

  if (!message || typeof message !== 'string' || !message.trim()) {
    return res.status(400).json({ error: 'A non-empty "message" string is required.' });
  }

  try {
    const result = await getShoppingRecommendations({ message, history });
    res.json(result);
  } catch (err) {
    console.error('AI search error:', err.message);
    const status = err.message.includes('ANTHROPIC_API_KEY') ? 503 : 500;
    res.status(status).json({ error: err.message });
  }
});

export default router;
