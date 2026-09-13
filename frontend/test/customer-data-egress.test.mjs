import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const rootLayout = readFileSync(
  new URL('../app/layout.tsx', import.meta.url),
  'utf8',
)

test('authenticated product root does not mount third-party analytics', () => {
  assert.doesNotMatch(rootLayout, /@vercel\/analytics/)
  assert.doesNotMatch(rootLayout, /<Analytics\b/)
  assert.doesNotMatch(rootLayout, /tenant_id|incident_id|snapshot_id|analysis_id/)
})
