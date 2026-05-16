/**
 * AimaaPixel SDK build script (esbuild).
 *
 * Entry: src/index.js. Output: dist/pixel.js (IIFE, minified, sourcemap).
 * Browser global: `window.aimaa` (snippet queue dispatcher) + `window.AimaaPixel`
 * (ergonomic alias). Backend serves the bundle at /api/pixel/p.js.
 *
 * Usage: `npm run build` veya `npm run build:watch`.
 */

const esbuild = require('esbuild');
const path = require('node:path');

const watch = process.argv.includes('--watch');

const config = {
    entryPoints: [path.join(__dirname, 'src', 'index.js')],
    outfile: path.join(__dirname, 'dist', 'pixel.js'),
    bundle: true,
    format: 'iife',
    globalName: 'AimaaPixelInternal',
    minify: true,
    sourcemap: true,
    target: 'es2017',
    platform: 'browser',
    // hash.js retains a Node fallback (require('node:crypto')) that is
    // statically reachable but runtime-unreachable in browsers — the
    // crypto.subtle branch returns first. Marking it external lets esbuild
    // emit the literal require() in the bundle without trying to resolve
    // node:crypto for the browser target.
    external: ['node:crypto'],
    legalComments: 'inline',
    banner: {
        js: '/*! AimaaPixel SDK v0.1.0 — https://aimaa.uz — © 2026 Aimaa Software */',
    },
    logLevel: 'info',
};

async function run() {
    if (watch) {
        const ctx = await esbuild.context(config);
        await ctx.watch();
        console.log('Watching for changes…');
    } else {
        await esbuild.build(config);
        console.log('Build complete:', path.relative(process.cwd(), config.outfile));
    }
}

run().catch((err) => {
    console.error('Build failed:', err);
    process.exit(1);
});
