/**
 * AimaaPixel SDK entry point.
 *
 * Two public surfaces, same dispatch:
 *   1. window.aimaa(method, ...args)        — Meta Pixel queue pattern.
 *      Backend snippet seeds `window._aq` with init+PageView; SDK flushes.
 *   2. window.AimaaPixel.{init,track}(...)  — Ergonomic alias.
 *
 * Payload contract (backend pixel.services.record_event):
 *   - event_name      (required) e.g. "PageView", "Purchase", "Lead"
 *   - event_id        (required) UUID; SDK generates if absent
 *   - pixel_id        (required) — set by init()
 *   - url, referrer   (auto from location/document)
 *   - client_ts       (ms epoch)
 *   - value, currency, click_id, utm_*  (optional)
 *   - custom_params   (object — unknown params bucketed here)
 *   - advanced_matching { em_hash, ph_hash, fn_hash, ln_hash,
 *                         external_id_hash } — derived from raw PII
 *                         via src/hash.js (NEVER send raw).
 *
 * Hash logic is imported verbatim from src/hash.js — DO NOT INLINE/DUPLICATE.
 * Parity test (29 vectors) is the contract with backend Python.
 */

const { hash } = require('./hash.js');

const PII_KEYS = new Set([
    'email', 'phone', 'first_name', 'last_name', 'external_id',
]);
const TOP_LEVEL_KEYS = new Set([
    'event_id', 'value', 'currency', 'click_id',
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
]);

const state = {
    pixelId: null,
    endpoint: null,
    debug: false,
    initialized: false,
};

function log(...args) {
    if (state.debug && typeof console !== 'undefined') {
        console.log('[AimaaPixel]', ...args);
    }
}

function warn(...args) {
    if (typeof console !== 'undefined') {
        console.warn('[AimaaPixel]', ...args);
    }
}

function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // RFC4122 v4 fallback for older browsers.
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : ((r & 0x3) | 0x8);
        return v.toString(16);
    });
}

function detectEndpoint() {
    // The script tag from which the SDK loaded; backend snippet sets
    // script.src = `${origin}/api/pixel/p.js`, so reuse that origin.
    const scripts = document.getElementsByTagName('script');
    for (const s of scripts) {
        const src = s.src || '';
        if (src.indexOf('/api/pixel/p.js') !== -1) {
            try {
                const u = new URL(src);
                return u.origin + '/api/pixel/event/';
            } catch (e) { /* fall through */ }
        }
    }
    // Last resort: same origin as the page.
    return window.location.origin + '/api/pixel/event/';
}

function init(pixelId, options) {
    if (state.initialized) {
        log('init() ignored — already initialized');
        return;
    }
    if (!pixelId) {
        warn('init: pixel_id required');
        return;
    }
    state.pixelId = String(pixelId);
    state.endpoint = (options && options.endpoint) || detectEndpoint();
    state.debug = !!(options && options.debug);
    state.initialized = true;
    log('initialized', { pixelId: state.pixelId, endpoint: state.endpoint });
}

async function buildPayload(eventName, params) {
    params = params || {};

    const payload = {
        pixel_id: state.pixelId,
        event_name: String(eventName),
        event_id: params.event_id || generateUUID(),
        client_ts: Date.now(),
        url: (typeof window !== 'undefined' && window.location) ? window.location.href : '',
        referrer: (typeof document !== 'undefined') ? document.referrer || '' : '',
    };

    for (const key of TOP_LEVEL_KEYS) {
        if (params[key] !== undefined && params[key] !== null && key !== 'event_id') {
            payload[key] = params[key];
        }
    }

    // Advanced matching: hash raw PII client-side. Backend never sees plain values.
    const adv = {};
    if (params.email)        adv.em_hash = await hash(params.email, 'email');
    if (params.phone)        adv.ph_hash = await hash(params.phone, 'phone');
    if (params.first_name)   adv.fn_hash = await hash(params.first_name, 'name');
    if (params.last_name)    adv.ln_hash = await hash(params.last_name, 'name');
    if (params.external_id)  adv.external_id_hash = await hash(params.external_id, 'external_id');
    if (Object.keys(adv).length) payload.advanced_matching = adv;

    // Everything else (not top-level, not PII) → custom_params.
    const customParams = {};
    for (const k of Object.keys(params)) {
        if (k === 'event_id') continue;
        if (TOP_LEVEL_KEYS.has(k)) continue;
        if (PII_KEYS.has(k)) continue;
        customParams[k] = params[k];
    }
    if (Object.keys(customParams).length) payload.custom_params = customParams;

    return payload;
}

async function track(eventName, params) {
    if (!state.initialized) {
        // Snippet may queue track() calls before SDK loads. The seed snippet
        // uses w._aq for that. Once SDK installs the real dispatcher and
        // flushes the queue, every track() reaches this path post-init.
        warn('track called before init — queueing not available in direct call');
        return;
    }
    if (!eventName) {
        warn('track: event_name required');
        return;
    }

    let payload;
    try {
        payload = await buildPayload(eventName, params);
    } catch (e) {
        warn('track: failed to build payload', e);
        return;
    }

    log('track →', eventName, payload);

    // pixel_id is also embedded in the body, but the CORS preflight (OPTIONS)
    // arrives before the body — backend resolves the pixel from the query
    // string at that stage to decide whether to echo Access-Control-Allow-
    // Origin. Without the query parameter the preflight returns 200 with no
    // CORS headers, and the browser silently drops the POST.
    const url = state.endpoint
        + (state.endpoint.indexOf('?') === -1 ? '?' : '&')
        + 'pixel_id=' + encodeURIComponent(state.pixelId);

    try {
        // Prefer fetch with keepalive so events sent during unload still fly.
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            credentials: 'omit',
            mode: 'cors',
            keepalive: true,
        });
    } catch (e) {
        warn('track: network error', e);
    }
}

function dispatch(method, ...args) {
    if (method === 'init')        return init(args[0], args[1]);
    if (method === 'track')       return track(args[0], args[1]);
    if (method === 'trackCustom') return track(args[0], args[1]);
    warn('unknown method:', method);
}

function flushQueue() {
    const q = window._aq;
    if (!Array.isArray(q)) return;
    const items = q.slice();
    q.length = 0;
    for (const argv of items) {
        try {
            dispatch.apply(null, argv);
        } catch (e) {
            warn('queue flush error', e);
        }
    }
}

// Replace the queue stub with the real dispatcher. From this point on every
// call to window.aimaa(method, ...args) hits dispatch() directly. Subsequent
// pushes to _aq (rare race condition) are caught by a Proxy-like overload
// below — but a plain assignment is enough for the snippet's pattern.
window.aimaa = function () {
    return dispatch.apply(null, arguments);
};

// Ergonomic alias for sites that prefer a typed surface.
window.AimaaPixel = { init, track, _state: state };

// Flush whatever the inline snippet queued before this bundle landed.
flushQueue();

// Standalone use without the inline snippet: a single <script
// src=".../pixel.js" data-pixel-id="UUID"> tag triggers init + auto-PageView.
(function () {
    if (state.initialized) return;
    const self = document.currentScript
        || document.querySelector('script[data-pixel-id]');
    if (!self) return;
    const pid = self.getAttribute('data-pixel-id');
    if (!pid) return;
    const debug = self.hasAttribute('data-aimaa-debug');
    init(pid, { debug });
    track('PageView');
})();
