/**
 * bridge/whatsapp_client.js
 * --------------------------
 * Baileys WhatsApp Web client.
 *
 * What it does:
 *   1. Connects to WhatsApp Web via WebSocket (no browser needed)
 *   2. Prints a QR code in the terminal on first run — scan with WhatsApp
 *   3. Saves session credentials in auth_info_baileys/ so you only scan once
 *   4. On every incoming text message, POSTs it to the Flask bridge server
 *      (bridge/bridge_server.py) which runs the Python agent pipeline
 *   5. Receives the generated reply from Flask and sends it back via Baileys
 *
 * Run:
 *   node bridge/whatsapp_client.js
 */

'use strict';

require('dotenv').config();

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeInMemoryStore,
  jidDecode,
} = require('@whiskeysockets/baileys');

const qrcode  = require('qrcode-terminal');
const pino    = require('pino');
const axios   = require('axios');
const path    = require('path');

// ── Config ────────────────────────────────────────────────────────────────────
const FLASK_URL      = `http://127.0.0.1:${process.env.FLASK_PORT || 5050}/incoming`;
const AUTH_DIR       = path.resolve(__dirname, '../auth_info_baileys');
const REPLY_DELAY_MS = 2000; // simulate human typing delay before sending

// ── Logger (quiet — only warn+ in prod) ──────────────────────────────────────
const logger = pino({ level: process.env.LOG_LEVEL || 'warn' });

// ── In-memory store (optional — helps with message history lookups) ───────────
const store = makeInMemoryStore({ logger: logger.child({ module: 'store' }) });

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Extract plain text from a Baileys message object.
 * Handles regular text, extended text, and image captions.
 */
function extractText(message) {
  const msg = message.message;
  if (!msg) return '';
  return (
    msg.conversation ||
    msg.extendedTextMessage?.text ||
    msg.imageMessage?.caption ||
    msg.videoMessage?.caption ||
    ''
  );
}

/**
 * Determine message type string for the decision engine.
 */
function extractType(message) {
  const msg = message.message;
  if (!msg) return 'unknown';
  if (msg.conversation || msg.extendedTextMessage) return 'text';
  if (msg.imageMessage)  return 'image';
  if (msg.videoMessage)  return 'video';
  if (msg.audioMessage)  return 'audio';
  if (msg.stickerMessage) return 'sticker';
  if (msg.documentMessage) return 'document';
  return 'unknown';
}

/**
 * Sleep helper for the human-like reply delay.
 */
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

// ── Core connection ───────────────────────────────────────────────────────────

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version }          = await fetchLatestBaileysVersion();

  console.log(`[bridge] Using Baileys v${version.join('.')}`);

  const sock = makeWASocket({
    version,
    logger,
    auth:  state,
    printQRInTerminal: false,   // we handle QR ourselves below
    browser: ['WhatsApp Persona Automation', 'Chrome', '1.0.0'],
    syncFullHistory: false,
  });

  // Bind the in-memory store to the socket
  store.bind(sock.ev);

  // ── QR code ────────────────────────────────────────────────────────────────
  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log('\n[bridge] Scan this QR code with WhatsApp on your phone:\n');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'close') {
      const code      = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      console.log(`[bridge] Connection closed (code ${code}). Reconnecting: ${!loggedOut}`);
      if (!loggedOut) {
        // Reconnect after a short back-off
        setTimeout(connectToWhatsApp, 3000);
      } else {
        console.log('[bridge] Logged out — delete auth_info_baileys/ and restart to re-scan QR.');
      }
    }

    if (connection === 'open') {
      console.log('[bridge] ✅ Connected to WhatsApp Web');
    }
  });

  // ── Save credentials on update ────────────────────────────────────────────
  sock.ev.on('creds.update', saveCreds);

  // ── Incoming messages ─────────────────────────────────────────────────────
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    // Only process new messages, not history sync
    if (type !== 'notify') return;

    for (const message of messages) {
      // Skip status broadcasts
      if (message.key.remoteJid === 'status@broadcast') continue;

      const jid        = message.key.remoteJid;
      const from_me    = message.key.fromMe;
      const text       = extractText(message);
      const msg_type   = extractType(message);
      const is_forward = !!(message.message?.extendedTextMessage?.contextInfo?.isForwarded);

      // Build payload for Flask
      const payload = {
        jid,
        from_me,
        text,
        message_type: msg_type,
        is_forwarded: is_forward,
        timestamp: message.messageTimestamp,
      };

      console.log(`[bridge] ← Incoming from ${jid} | type=${msg_type} | text=${text.slice(0, 60)}`);

      let reply = null;
      try {
        const response = await axios.post(FLASK_URL, payload, { timeout: 30000 });
        if (response.data?.reply) {
          reply = response.data.reply;
        } else {
          console.log(`[bridge] Pipeline said IGNORE for ${jid}`);
        }
      } catch (err) {
        console.error(`[bridge] Flask error: ${err.message}`);
      }

      // Send reply if pipeline approved one
      if (reply) {
        await sleep(REPLY_DELAY_MS);
        await sock.sendMessage(jid, { text: reply });
        console.log(`[bridge] → Sent reply to ${jid}: ${reply.slice(0, 60)}`);
      }
    }
  });

  return sock;
}

// ── Entry point ───────────────────────────────────────────────────────────────
connectToWhatsApp().catch((err) => {
  console.error('[bridge] Fatal error:', err);
  process.exit(1);
});
