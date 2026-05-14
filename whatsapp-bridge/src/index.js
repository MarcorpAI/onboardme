import 'dotenv/config';
import pino from 'pino';
import express from 'express';
import { createBaileysBot, sendWhatsAppMessage, getConnectionStatus } from './baileys.js';

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const API_URL = process.env.API_URL || 'http://localhost:8000';
const PORT = process.env.PORT || 3000;

const app = express();
app.use(express.json());

app.get('/health', (req, res) => {
  const status = getConnectionStatus();
  res.json({ status: 'healthy', connected: status.connected });
});

app.post('/send', async (req, res) => {
  const { to, message } = req.body;
  
  if (!to || !message) {
    return res.status(400).json({ error: 'Missing to or message' });
  }
  
  const status = getConnectionStatus();
  if (!status.connected || !status.ready) {
    logger.warn({ status }, 'Cannot send - not connected');
    return res.status(503).json({ error: 'WhatsApp not connected or not ready' });
  }
  
  try {
    const result = await sendWhatsAppMessage(null, to, message);
    if (result.success) {
      res.json({ status: 'sent', jid: result.jid });
    } else {
      res.status(500).json({ error: 'Failed to send message' });
    }
  } catch (error) {
    logger.error({ error: error.message }, 'Send error');
    res.status(500).json({ error: error.message });
  }
});

app.get('/qr', (req, res) => {
  const status = getConnectionStatus();
  if (status.qr) {
    res.json({ qr: status.qr });
  } else if (status.connected) {
    res.json({ qr: null, message: 'Already connected' });
  } else {
    res.json({ qr: null, message: 'Waiting for QR code...' });
  }
});

async function main() {
  try {
    await createBaileysBot();
    
    app.listen(PORT, () => {
      logger.info(`WhatsApp Bridge listening on port ${PORT}`);
      logger.info(`API URL: ${API_URL}`);
    });
  } catch (error) {
    logger.error({ error: error.message }, 'Failed to start bridge');
    process.exit(1);
  }
}

main();