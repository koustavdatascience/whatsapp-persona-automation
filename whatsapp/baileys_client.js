'use strict';

/**
 * whatsapp/baileys_client.js
 * ---------------------------
 * Baileys WhatsApp Web client — CommonJS, @whiskeysockets/baileys.
 *
 * DRY_RUN flag
 * ------------
 * When DRY_RUN = true the client will log "[DRY_RUN] would reply to <jid>: <reply>"
 * but will NOT call sock.sendMessage — safe for testing against real contacts.
 * Flip to false only for controlled testing against a known consenting contact.
 * Session 4.2 replaces this with a proper toggle.
 */

// ─── FLIP THIS TO FALSE ONLY FOR CONTROLLED TESTING AGAINST A KNOWN ──────────
// ─── CONSENTING CONTACT. Session 4.2 replaces this with a proper toggle. ─────
const DRY_RUN = true;

require('dotenv').config();

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');

const qrcode = require('qrcode-terminal');
const axios  = require('axios');
const pino   = require('pino');
const path   = require('path');

// ── Config ────────────────────────────────────────────────────────────────────
const BRIDGE_URL = `http://127.0.0.1:${process.env.AGENT_BRIDGE_PORT || 5001}/process`;
const AUTH_DIR   = path.resolve(__dirname, '../auth_info_baileys');

// ── Logger — force silent, suppress all pino output including key dumps ───────
const logger = pino({ level: 'silent' }).child({});
logger.level = 'silent';

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Extract plain text from a Baileys message object.
 * Priority: conversation → extendedTextMessage.text → media caption → ""
 */
function extractText(msg) {
  if (!msg) return '';
  return (
    msg.conversation ||
    msg.extendedTextMessage?.text ||
    msg.imageMessage?.caption  ||
    msg.videoMessage?.caption  ||
    msg.audioMessage?.caption  ||
    ''
  );
}

/**
 * Determine message_type string.
 * "text" | "image" | "video" | "audio" | "other"
 */
function extractType(msg) {
  if (!msg) return 'other';
  if (msg.conversation || msg.extendedTextMessage) return 'text';
  if (msg.imageMessage)  return 'image';
  if (msg.videoMessage)  return 'video';
  if (msg.audioMessage)  return 'audio';
  return 'other';
}

/**
 * Safely check is_forwarded — never crashes if contextInfo is missing.
 */
function extractIsForwarded(msg) {
  if (!msg) return false;
  return !!(
    msg.extendedTextMessage?.contextInfo?.isForwarded ||
    msg.imageMessage?.contextInfo?.isForwarded        ||
    msg.videoMessage?.contextInfo?.isForwarded        ||
    msg.audioMessage?.contextInfo?.isForwarded        ||
    false
  );
}

/**
 * Random delay between min and max milliseconds.
 */
const randomDelay = (min, max) =>
  new Promise((res) => setTimeout(res, Math.floor(Math.random() * (max - min + 1)) + min));

// ── Core connection ───────────────────────────────────────────────────────────

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version }          = await fetchLatestBaileysVersion();

  console.log(`[ROUTE] Baileys version: ${version.join('.')}`);
  console.log(`[ROUTE] DRY_RUN = ${DRY_RUN}`);
  console.log(`[ROUTE] Bridge  = ${BRIDGE_URL}`);

  const sock = makeWASocket({
    version,
    logger,
    auth:               state,
    printQRInTerminal:  false,   // we handle QR ourselves
    browser:            ['WhatsApp Persona Automation', 'Chrome', '1.0.0'],
    syncFullHistory:    false,
  });

  // ── QR + connection lifecycle ─────────────────────────────────────────────
  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log('\n[ROUTE] Scan this QR code with WhatsApp:\n');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'close') {
      const code      = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      console.log(`[ROUTE] Connection closed (code=${code}) — reconnect: ${!loggedOut}`);
      if (!loggedOut) {
        setTimeout(connectToWhatsApp, 3000);
      } else {
        console.log('[ROUTE] Logged out — delete auth_info_baileys/ and restart.');
      }
    }

    if (connection === 'open') {
      console.log('[ROUTE] ✅ Connected to WhatsApp Web');
    }
  });

  // ── Save credentials ──────────────────────────────────────────────────────
  sock.ev.on('creds.update', saveCreds);

  // ── Incoming messages ─────────────────────────────────────────────────────
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    // CRITICAL: only process genuinely new real-time messages
    if (type !== 'notify') {
      console.log('[SKIP] history sync message, ignoring');
      return;
    }

    for (const message of messages) {
      // Skip status broadcasts
      if (message.key.remoteJid === 'status@broadcast') continue;

      const jid     = message.key.remoteJid;
      const from_me = message.key.fromMe;

      // Skip own messages
      if (from_me) {
        console.log(`[SKIP] own message (${jid})`);
        continue;
      }

      const inner       = message.message;
      const text        = extractText(inner);
      const messageType = extractType(inner);
      const isForwarded = extractIsForwarded(inner);

      console.log(`[ROUTE] ← ${jid} | type=${messageType} | forwarded=${isForwarded} | text=${text.slice(0, 60)}`);

      // Build payload for agent bridge
      const payload = {
        jid,
        text,
        message_type: messageType,
        is_forwarded: isForwarded,
        from_me,
      };

      // POST to agent/bridge.py
      let result = null;
      try {
        const response = await axios.post(BRIDGE_URL, payload, { timeout: 30000 });
        result = response.data;
        console.log(`[DECISION] jid=${jid} | should_reply=${result.should_reply} | relationship=${result.relationship} | reason=${result.reason}`);
      } catch (err) {
        console.error(`[DECISION] Bridge POST failed: ${err.message}`);
        continue;
      }

      // Send reply if approved
      if (result?.should_reply && result?.reply) {
        if (DRY_RUN) {
          // DRY RUN — log only, do NOT send
          console.log(`[DRY_RUN] would reply to ${jid}: ${result.reply}`);
        } else {
          // LIVE — wait random human-like delay then send
          const delay = Math.floor(Math.random() * (8000 - 3000 + 1)) + 3000;
          console.log(`[REPLY] Waiting ${delay}ms before sending to ${jid}...`);
          await randomDelay(3000, 8000);
          await sock.sendMessage(jid, { text: result.reply });
          console.log(`[SEND] → ${jid}: ${result.reply.slice(0, 60)}`);
        }
      } else {
        console.log(`[SKIP] No reply for ${jid} — ${result?.reason || 'no reason'}`);
      }
    }
  });

  return sock;
}

// ── Entry point ───────────────────────────────────────────────────────────────
connectToWhatsApp().catch((err) => {
  console.error('[ROUTE] Fatal:', err);
  process.exit(1);
});
