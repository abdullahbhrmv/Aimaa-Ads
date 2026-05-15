/**
 * Hash contract parity testi (Adım 0).
 *
 * pixel/fixtures/hash_fixtures.json'daki her vektör için:
 *   - src/hash.js::normalize(raw, kind) çıktısı fixture.normalized ile eşit
 *   - src/hash.js::hash(raw, kind) çıktısı fixture.hash ile eşit
 *
 * Herhangi bir vektörde sapma varsa exit code 1; CI fail, Adım 2 durdurulur.
 *
 * Test framework yok — Node built-in assert. Bağımlılık minimum.
 * Çalıştırma: `npm test` veya `node test/hash.test.js`.
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { normalize, hash, sha256Hex } = require('../src/hash');

const FIXTURE_PATH = path.join(__dirname, '..', 'fixtures', 'hash_fixtures.json');
const fixture = JSON.parse(fs.readFileSync(FIXTURE_PATH, 'utf8'));

async function main() {
    let passed = 0;
    const failures = [];

    for (const [kind, cases] of Object.entries(fixture.cases)) {
        for (const c of cases) {
            const tag = `${kind}/${c.name}`;

            // normalize
            let actualNorm;
            try {
                actualNorm = normalize(c.raw, kind);
                assert.equal(actualNorm, c.normalized,
                    `normalize mismatch: expected ${JSON.stringify(c.normalized)}, got ${JSON.stringify(actualNorm)}`);
            } catch (e) {
                failures.push({ tag, stage: 'normalize', error: e.message, raw: c.raw });
                continue;
            }

            // hash
            let actualHash;
            try {
                actualHash = await hash(c.raw, kind);
                assert.equal(actualHash, c.hash,
                    `hash mismatch: expected ${c.hash || '(empty)'}, got ${actualHash || '(empty)'}`);
            } catch (e) {
                failures.push({ tag, stage: 'hash', error: e.message, raw: c.raw });
                continue;
            }

            passed++;
        }
    }

    // Independent sanity: NFC idempotency. Fixture bunu garanti etmeli ama
    // çifte kontrol — NFD→NFC ve NFC kendisi aynı hash vermeli.
    const nfcHash = await hash('Café', 'name');
    const nfdHash = await hash('cafe\u0301', 'name');
    assert.equal(nfcHash, nfdHash, 'NFC normalization broken: NFD input produced different hash');

    // Independent sanity: phone digit stripping — unicode digitler ASCII'ye düşmez.
    const uzbekHash = await hash('998901234567', 'phone');
    const mixedHash = await hash('+998-901-234-567\u0660', 'phone');
    assert.equal(uzbekHash, mixedHash, 'phone strip failed to remove separators + unicode digit');

    const total = passed + failures.length;
    console.log(`\n${passed}/${total} hash parity vectors passed`);

    if (failures.length) {
        console.error('\nFAILURES:');
        for (const f of failures) {
            console.error(`  ${f.tag} [${f.stage}]: ${f.error}`);
            console.error(`    raw=${JSON.stringify(f.raw)}`);
        }
        process.exit(1);
    }
    console.log('All parity vectors and sanity checks passed.');
}

main().catch(err => {
    console.error('Unexpected error:', err);
    process.exit(2);
});
