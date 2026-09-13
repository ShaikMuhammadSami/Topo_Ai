import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const frontend = new URL('..', import.meta.url)

function sourcesUnder(relative) {
  const root = fileURLToPath(new URL(`${relative}/`, frontend))
  const files = []

  function visit(path) {
    for (const name of readdirSync(path)) {
      const target = join(path, name)
      if (statSync(target).isDirectory()) {
        visit(target)
      } else if (/\.(?:ts|tsx|js|jsx|mjs)$/.test(name)) {
        files.push(readFileSync(target, 'utf8'))
      }
    }
  }

  visit(root)
  return files.join('\n')
}

test('authenticated product has no analytics mount or alternate customer-data sink', () => {
  const product = [sourcesUnder('app'), sourcesUnder('components'), sourcesUnder('lib')].join('\n')

  for (const marker of [
    /@vercel\/analytics/i,
    /<Analytics\b/,
    /analytics\.track\s*\(/i,
    /mixpanel/i,
    /posthog/i,
    /amplitude/i,
    /gtag\s*\(/i,
  ]) {
    assert.doesNotMatch(product, marker)
  }
})

test('browser egress remains the single same-origin Topo API helper', () => {
  const product = [sourcesUnder('app'), sourcesUnder('components'), sourcesUnder('lib')].join('\n')
  const helper = readFileSync(new URL('../lib/topo-api.ts', import.meta.url), 'utf8')
  const fetchCount = (product.match(/\bfetch\s*\(/g) ?? []).length

  assert.equal(fetchCount, 1)
  assert.match(helper, /fetch\s*\(/)
  assert.doesNotMatch(helper, /vercel|segment|mixpanel|posthog|amplitude/i)
})
