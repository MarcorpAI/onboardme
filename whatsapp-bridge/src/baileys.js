import pino from 'pino';
import { createRequire } from 'module';
import { formatPhoneNumber, forwardToApi } from './api.js';

const require = createRequire(import.meta.url);
const baileys = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');

const makeWASocket = baileys.default || baileys;
const {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore
} = baileys;

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const SESSION_PATH = process.env.BAILEYS_SESSION_PATH || './sessions';
const MAPPING_FILE = path.join(SESSION_PATH, 'lid_mapping.json');

const FALLBACK_VERSION = [2, 3000, 1037641644];

let currentSock = null;
let currentQR = null;
let isConnected = false;
let isReady = false;

const RECONNECT_DELAY_MS = 8000;

let lidToPhone = new Map();
let phoneToLid = new Map();

function loadMapping() {
  try {
    if (fs.existsSync(MAPPING_FILE)) {
      const data = JSON.parse(fs.readFileSync(MAPPING_FILE, 'utf8'));
      lidToPhone = new Map(Object.entries(data.lidToPhone || {}));
      phoneToLid = new Map(Object.entries(data.phoneToLid || {}));
      logger.info({ entries: lidToPhone.size }, 'Loaded LID mapping');
    }
  } catch (error) {
    logger.warn({ error: error.message }, 'Failed to load LID mapping');
  }
}

function saveMapping() {
  try {
    const data = {
      lidToPhone: Object.fromEntries(lidToPhone),
      phoneToLid: Object.fromEntries(phoneToLid)
    };
    fs.writeFileSync(MAPPING_FILE, JSON.stringify(data, null, 2));
  } catch (error) {
    logger.warn({ error: error.message }, 'Failed to save LID mapping');
  }
}

function storeMapping(phone, lid) {
  if (!phone || !lid) return;
  const phoneNum = phone.replace(/\D/g, '');
  const lidNum = lid.replace('@lid', '').replace('@s.whatsapp.net', '');
  lidToPhone.set(lidNum, phoneNum);
  lidToPhone.set(lid, phoneNum);
  phoneToLid.set(phoneNum, lidNum);
  phoneToLid.set(phone, lidNum);
  saveMapping();
}

function getPhoneFromLid(lid) {
  if (!lid) return null;
  const clean = lid.replace('@lid', '').replace('@s.whatsapp.net', '');
  return lidToPhone.get(clean) || lidToPhone.get(lid) || null;
}

function getLidFromPhone(phone) {
  if (!phone) return null;
  const clean = phone.replace(/\D/g, '');
  return phoneToLid.get(clean) || phoneToLid.get(phone) || null;
}

export function getConnectionStatus() {
  return {
    connected: isConnected,
    ready: isReady,
    qr: currentQR
  };
}

export async function disconnectAndClearSession() {
  try {
    if (currentSock?.logout) {
      await currentSock.logout();
    } else if (currentSock?.end) {
      currentSock.end(undefined);
    }
  } catch (error) {
    logger.warn({ error: error.message }, 'Error during WhatsApp logout');
  }

  currentSock = null;
  currentQR = null;
  isConnected = false;
  isReady = false;
  lidToPhone = new Map();
  phoneToLid = new Map();

  try {
    fs.rmSync(SESSION_PATH, { recursive: true, force: true });
    fs.mkdirSync(SESSION_PATH, { recursive: true });
  } catch (error) {
    logger.warn({ error: error.message }, 'Failed to clear session path');
  }

  setTimeout(startSock, 1000);
  logger.info('WhatsApp session cleared, restarting socket');
}

async function resolveVersion() {
  try {
    const result = await fetchLatestBaileysVersion();
    if (result.isLatest) {
      logger.info({ version: result.version.join('.') }, 'Using latest WA version');
      return result.version;
    }
  } catch (error) {
    logger.warn({ error: error.message }, 'fetchLatestBaileysVersion failed');
  }
  return FALLBACK_VERSION;
}

function extractPhoneFromMessage(message) {
  const remoteJid = message.key?.remoteJid;
  const remoteJidAlt = message.key?.remoteJidAlt;
  const participant = message.key?.participant;
  const participantAlt = message.key?.participantAlt;
  const senderPn = message.key?.senderPn;

  let phone = null;
  let jid = remoteJid;

  // Check if remoteJidAlt has the phone (for DMs)
  if (remoteJidAlt && !remoteJidAlt.includes('@lid') && remoteJidAlt.includes('@s.whatsapp.net')) {
    phone = remoteJidAlt.split('@')[0];
  }

  // Check senderPn (available in recent Baileys versions)
  if (!phone && senderPn) {
    phone = senderPn;
  }

  // Check participantAlt (for groups)
  if (!phone && participantAlt && !participantAlt.includes('@lid') && participantAlt.includes('@s.whatsapp.net')) {
    phone = participantAlt.split('@')[0];
  }

  // If still no phone but we have a LID, check internal mapping
  if (!phone && remoteJid?.includes('@lid')) {
    phone = getPhoneFromLid(remoteJid);
  }

  // If it's a regular phone JID, extract directly
  if (!phone && remoteJid && remoteJid.includes('@s.whatsapp.net')) {
    phone = remoteJid.split('@')[0];
  }

  // If it's a LID and we found a phone, store the mapping
  if (phone && remoteJid?.includes('@lid')) {
    storeMapping(phone, remoteJid);
  }

  return { phone, jid };
}

function isGroupMessage(message) {
  const remoteJid = message.key?.remoteJid || '';
  const participant = message.key?.participant || '';
  return remoteJid.endsWith('@g.us') || Boolean(participant);
}

async function startSock() {
  try {
    loadMapping();

    const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);
    const version = await resolveVersion();

    logger.info({ version: version.join('.') }, 'Starting Baileys socket');

    isConnected = false;
    isReady = false;
    currentQR = null;

    const sock = makeWASocket({
      version,
      logger,
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      printQRInTerminal: true,
      browser: ['MacOS', 'Safari', '14.4.1'],
      connectTimeoutMs: 60000,
      defaultQueryTimeoutMs: 60000,
      keepAliveIntervalMs: 30000,
      markOnlineOnConnect: false,
    });

    currentSock = sock;

    sock.ev.on('connection.update', (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        currentQR = qr;
        logger.info('QR Code ready - scan with WhatsApp');
        qrcode.generate(qr, { small: true });
      }

      if (connection === 'open') {
        isConnected = true;
        isReady = true;
        currentQR = null;
        logger.info('WhatsApp connected successfully');
      }

      if (connection === 'close') {
        const errorCode = lastDisconnect?.error?.output?.statusCode || lastDisconnect?.error?.data?.reason;

        isConnected = false;
        isReady = false;

        logger.warn({ errorCode }, 'Connection closed');

        if (errorCode === DisconnectReason?.loggedOut || errorCode === 'logout') {
          logger.error('Session logged out');
          return;
        }

        if (errorCode === 405) {
          logger.error('405 error - WA version rejected');
          return;
        }

        logger.info(`Reconnecting in ${RECONNECT_DELAY_MS / 1000}s...`);
        setTimeout(startSock, RECONNECT_DELAY_MS);
      }
    });

    sock.ev.on('creds.update', saveCreds);

    // Listen for LID mapping updates from Baileys
    sock.ev.on('lid-mapping.update', (mappings) => {
      for (const { lid, pn } of mappings) {
        if (lid && pn) {
          storeMapping(pn, lid);
          logger.info({ lid, pn }, 'LID mapping updated');
        }
      }
    });

    sock.ev.on('contacts.upsert', (contacts) => {
      for (const contact of contacts) {
        if (contact.phoneNumber && contact.lid) {
          storeMapping(contact.phoneNumber, contact.lid);
        }
        if (contact.id && contact.phoneNumber && !contact.id.includes('@')) {
          storeMapping(contact.phoneNumber, contact.id);
        }
      }
    });

    sock.ev.on('messages.upsert', async ({ messages }) => {
      for (const message of messages) {
        if (message.key.fromMe) continue;

        const msgContent = message.message?.conversation
          || message.message?.extendedTextMessage?.text
          || '';

        const jid = message.key?.remoteJid;

        if (!msgContent || jid === 'status@broadcast') {
          continue;
        }

        if (isGroupMessage(message)) {
          logger.info({ jid }, 'Ignoring group message');
          continue;
        }

        const { phone, jid: actualJid } = extractPhoneFromMessage(message);

        if (!phone) {
          logger.warn({ jid }, 'Could not extract phone number from message');
          continue;
        }

        logger.info({ phone, jid: actualJid, remoteJidAlt: message.key?.remoteJidAlt }, 'Incoming message');

        try {
          await forwardToApi(phone, msgContent, actualJid);
        } catch (error) {
          logger.error({ error: error.message }, 'Failed to forward message');
        }
      }
    });

    return sock;
  } catch (error) {
    logger.error({ error: error.message }, 'Failed to start Baileys');
    setTimeout(startSock, RECONNECT_DELAY_MS);
  }
}

export async function createBaileysBot() {
  return startSock();
}

export async function sendWhatsAppMessage(sockArg, to, message) {
  const socketToUse = sockArg || currentSock;

  if (!socketToUse || !isReady) {
    logger.warn('Socket not ready');
    return { success: false };
  }

  let jid;
  let formattedNumber;
  if (to.includes('@')) {
    jid = to;
    formattedNumber = to.split('@')[0];
  } else {
    formattedNumber = formatPhoneNumber(to);
    jid = formattedNumber.replace('+', '') + '@s.whatsapp.net';
  }

  try {
    const result = await socketToUse.sendMessage(jid, { text: message });
    const finalJid = result?.key?.remoteJid || jid;

    // Store the mapping between phone and LID
    if (finalJid.includes('@lid')) {
      storeMapping(formattedNumber.replace('+', ''), finalJid);
    } else if (finalJid.includes('@s.whatsapp.net') && !finalJid.includes('@lid')) {
      // After sending, we know this phone's LID if we had one
      const storedLid = getLidFromPhone(formattedNumber.replace('+', ''));
      if (storedLid) {
        storeMapping(formattedNumber.replace('+', ''), storedLid);
      }
    }

    logger.info({ to: formattedNumber, jid: finalJid }, 'Message sent');
    return { success: true, jid: finalJid };
  } catch (error) {
    logger.error({ to: formattedNumber, error: error.message }, 'Failed to send message');
    return { success: false };
  }
}

export { formatPhoneNumber };
