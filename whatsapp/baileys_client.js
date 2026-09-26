'use strict';

/**
 * whatsapp/baileys_client.js
 * ---------------------------
 * Baileys WhatsApp Web client — CommonJS, @whiskeysockets/baileys.
 *
 * Changes from Session 4.1:
 *   1. DRY_RUN constant removed — read fresh from config/settings.json per message
 *   2. kill_switch.flag check added — skips all processing if file exists
 *   3. enforceAllowlist() — independent Node-side allowlist check before sendMessage
 *   4. Delay range read from settings (min_delay_seconds / max_delay_seconds)
 *   5. [DRY_RUN] log behaviour preserved when dry_run = true
 */

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
const fs     = require('fs');

// ── Config ────────────────────────────────────────────────────────────────────
const BRIDGE_URL          = `http://127.0.0.1:${process.env.AGENT_BRIDGE_PORT || 5001}/process`;
const AUTH_DIR            = path.resolve(__dirname, '../auth_info_baileys');
const SETTINGS_PATH       = path.resolve(__dirname, '../config/settings.json');
const RELATIONSHIP_MAP    = path.resolve(__dirname, '../config/relationship_map.json');
const KILL_SWITCH_PATH    = path.resolve(__dirname, '../kill_switch.flag');

// ── Safe defaults — used when settings.json is missing or fails to parse ──────
const SETTINGS_DEFAULTS = {
  dry_run:           true,
  min_delay_seconds: 3,
  max_delay_seconds: 12,
};

// ── Logger — silent, no pino key dumps ───────────────────────────────────────
const logger = pino({ level: 'silent' }).child({});
logger.level = 'silent';


// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Read config/settings.json fresh on every call.
 * Falls back to SETTINGS_DEFAULTS if the file is missing or fails to parse.
 * Never throws.
 */
function readSettings() {
  try {
    const raw  = fs.readFileSync(SETTINGS_PATH, 'utf-8');
    const data = JSON.parse(raw);
    return { ...SETTINGS_DEFAULTS, ...data };
  } catch (_) {
    return { ...SETTINGS_DEFAULTS };
  }
}

/**
 * Check whether kill_switch.flag exists in the repo root.
 * Returns true (kill switch active) or false.
 */
function isKillSwitchActive() {
  return fs.existsSync(KILL_SWITCH_PATH);
}

/**
 * Independent Node-side allowlist check.
 * Reads config/relationship_map.json directly, strips the JID suffix the same
 * way agent/router.py does, and returns true only if that number's mapped
 * relationship is not "unknown" and not missing entirely.
 *
 * Called immediately before sock.sendMessage — even if the bridge said
 * should_reply=true — as a final safety gate.
 */
function enforceAllowlist(jid) {
  if (!jid || typeof jid !== 'string') return false;

  // Strip "@..." suffix — same as router.py
  const atPos  = jid.indexOf('@');
  const number = atPos !== -1 ? jid.slice(0, atPos) : jid;
  if (!number) return false;

  try {
    const raw    = fs.readFileSync(RELATIONSHIP_MAP, 'utf-8');
    const relMap = JSON.parse(raw);
    const rel    = relMap[number];
    // Must exist and must not be "unknown"
    return typeof rel === 'string' && rel !== 'unknown';
  } catch (_) {
    return false;
  }
}

/**
 * Extract plain text from a Baileys message object.
 */
function extractText(msg) {
  if (!msg) return '';
  return (
    msg.conversation              ||
    msg.extendedTextMessage?.text ||
    msg.imageMessage?.caption     ||
    msg.videoMessage?.caption     ||
    msg.audioMessage?.caption     ||
    ''
  );
}

/**
 * Determine message_type string: "text" | "image" | "video" | "audio" | "other"
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
 * Random delay between min and max seconds (converted to ms).
 */
const randomDelay = (minSec, maxSec) => {
  const ms = Math.floor(Math.random() * ((maxSec - minSec) * 1000 + 1)) + minSec * 1000;
  return new Promise((res) => setTimeout(res, ms));
};


// ── Core connection ───────────────────────────────────────────────────────────

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version }          = await fetchLatestBaileysVersion();

  console.log(`[ROUTE] Baileys version: ${version.join('.')}`);
  console.log(`[ROUTE] Bridge  = ${BRIDGE_URL}`);
  console.log(`[ROUTE] Settings read fresh per message from ${SETTINGS_PATH}`);

  const sock = makeWASocket({
    version,
    logger,
    auth:              state,
    printQRInTerminal: false,
    browser:           ['WhatsApp Persona Automation', 'Chrome', '1.0.0'],
    syncFullHistory:   false,
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
    if (type !== 'notify') return;   // skip history sync silently

    for (const message of messages) {
      if (message.key.remoteJid === 'status@broadcast') continue;

      const jid     = message.key.remoteJid;
      const from_me = message.key.fromMe;

      if (from_me) {
        console.log(`[SKIP] own message (${jid})`);
        continue;
      }

      // ── 1. Read settings fresh for this message ───────────────────────────
      const settings       = readSettings();
      const dryRun         = settings.dry_run;
      const minDelaySec    = settings.min_delay_seconds;
      const maxDelaySec    = settings.max_delay_seconds;

      // ── 2. Kill switch check ──────────────────────────────────────────────
      if (isKillSwitchActive()) {
        console.log(`[KILL SWITCH] active, skipping all processing for ${jid}`);
        continue;
      }

      const inner       = message.message;
      const text        = extractText(inner);
      const messageType = extractType(inner);
      const isForwarded = extractIsForwarded(inner);

      console.log(`[ROUTE] ← ${jid} | type=${messageType} | dry_run=${dryRun} | text=${text.slice(0, 60)}`);

      // Build payload for agent bridge
      const payload = { jid, text, message_type: messageType, is_forwarded: isForwarded, from_me };

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

      // ── 3. Send reply if approved ─────────────────────────────────────────
      if (result?.should_reply && result?.reply) {
        if (dryRun) {
          // DRY RUN — log only, do NOT send
          console.log(`[DRY_RUN] would reply to ${jid}: ${result.reply}`);
        } else {
          // ── 4. Independent allowlist check before sending ─────────────────
          if (!enforceAllowlist(jid)) {
            console.log(`[BLOCKED] failed independent allowlist check for ${jid} — skipping send`);
            continue;
          }

          // ── 5. Random human-like delay from settings ──────────────────────
          console.log(`[REPLY] Waiting ${minDelaySec}–${maxDelaySec}s before sending to ${jid}...`);
          await randomDelay(minDelaySec, maxDelaySec);

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
