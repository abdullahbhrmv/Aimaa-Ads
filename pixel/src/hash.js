/**
 * AimaaPixel — advanced matching hash normalization.
 *
 * Bu dosya hem Node.js (backend parity testi için) hem de tarayıcıda
 * çalışacak şekilde yazılmıştır. Tarayıcıda `crypto.subtle.digest` asenkron
 * olduğu için `hash()` fonksiyonu Promise döner; Node'da da aynı Promise
 * dönüyor ki API şekli tutarlı kalsın.
 *
 * Kontrat: pixel/fixtures/hash_fixtures.json — JS ve Python implementasyonları
 * her vektör için birebir aynı `normalized` ve `hash` çıktısı üretmek
 * zorunda. Parity bozukluğu cross-device attribution'ı sessizce yıkar.
 *
 * Normalization kuralları:
 *   email  : trim + toLowerCase (default locale). No +tag / dot stripping.
 *   phone  : remove all non-ASCII-digit characters via /[^0-9]/g.
 *            Unicode digits (Arabic ٠, Bengali ৬, Devanagari १ vb.) KALDIRILIR.
 *   name   : trim + toLowerCase. Turkish İ → "i" + combining dot U+0307
 *            olması default davranıştır; toLocaleLowerCase('tr') KULLANMA —
 *            parity'yi bozar.
 *   external_id : trim yalnız; case KORUNUR.
 *
 * Boş input → boş hash (SHA-256(empty) DEĞİL). "Değer yok" sinyali.
 * NFC normalization hash'leme öncesi uygulanır.
 */

// Hot path: regex'i her çağrıda yeniden derleme.
const PHONE_STRIP_RE = /[^0-9]/g;

/**
 * @param {string} raw
 * @param {"email"|"phone"|"name"|"external_id"} kind
 * @returns {string}
 */
function normalize(raw, kind) {
    if (raw === undefined || raw === null || raw === '') return '';
    let s = String(raw);
    if (kind === 'email' || kind === 'name') {
        s = s.trim().toLowerCase();
    } else if (kind === 'phone') {
        s = s.replace(PHONE_STRIP_RE, '');
    } else if (kind === 'external_id') {
        s = s.trim();
    }
    // NFC: precomposed karakterler. Hem Node hem browser'da native destek.
    return s.normalize('NFC');
}

/**
 * UTF-8 encode → SHA-256 → lowercase hex. Node veya browser.
 * @param {string} text
 * @returns {Promise<string>}
 */
async function sha256Hex(text) {
    // Browser: globalThis.crypto.subtle, async.
    if (typeof globalThis !== 'undefined' && globalThis.crypto && globalThis.crypto.subtle) {
        const buf = new TextEncoder().encode(text);
        const digest = await globalThis.crypto.subtle.digest('SHA-256', buf);
        const arr = Array.from(new Uint8Array(digest));
        return arr.map(b => b.toString(16).padStart(2, '0')).join('');
    }
    // Node (<=18 or older): fallback to node:crypto.
    // `require` yalnız Node ortamında tanımlıdır; bundler browser'a gömmez
    // çünkü üstteki subtle branch her modern tarayıcıda true olacaktır.
    const nodeCrypto = require('node:crypto');
    return nodeCrypto.createHash('sha256').update(text, 'utf8').digest('hex');
}

/**
 * Normalize + hash. Parity tablosu ile doğrulanır.
 * @param {string} raw
 * @param {"email"|"phone"|"name"|"external_id"} kind
 * @returns {Promise<string>} 64-char lowercase hex, or "" if normalized empty.
 */
async function hash(raw, kind) {
    const n = normalize(raw, kind);
    if (!n) return '';
    return sha256Hex(n);
}

// Node (CommonJS) — backend parity testi için.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { normalize, hash, sha256Hex };
}

// Browser (ES module / global) — Adım 1'de SDK wrapper tarafından kullanılacak.
// UMD yerine minimal: aimaa-pixel.js build'i bu dosyayı import edecek ya da
// inline edecek (esbuild bundling).
if (typeof globalThis !== 'undefined') {
    globalThis.__aimaaPixelHash = { normalize, hash, sha256Hex };
}
