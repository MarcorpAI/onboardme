import pino from 'pino';
import axios from 'axios';

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const API_URL = process.env.API_URL || 'http://localhost:8000';

export async function forwardToApi(whatsapp, message, jid) {
  try {
    const response = await axios.post(`${API_URL}/webhook/inbound`, {
      whatsapp,
      message,
      jid
    }, { timeout: 30000 });
    
    logger.info({ whatsapp, status: response.status }, 'Message forwarded to API');
    return response.data;
  } catch (error) {
    logger.error({ whatsapp, error: error.message }, 'Failed to forward message to API');
    throw error;
  }
}

export async function sendMessageViaApi(to, message) {
  try {
    const response = await axios.post(`${API_URL}/webhook/send`, {
      to,
      message
    }, { timeout: 30000 });
    
    logger.info({ to, status: response.status }, 'Send request sent to API');
    return response.data;
  } catch (error) {
    logger.error({ to, error: error.message }, 'Failed to send via API');
    throw error;
  }
}

export function formatPhoneNumber(phone) {
  let formatted = phone.replace(/[\s\-]/g, '');
  // If it starts with 0 and is 11 digits, it's likely a Nigerian number (e.g. 0810...)
  if (formatted.startsWith('0') && formatted.length === 11) {
    formatted = '234' + formatted.substring(1);
  }
  if (!formatted.startsWith('+')) {
    formatted = '+' + formatted;
  }
  return formatted;
}