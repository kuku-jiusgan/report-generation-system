import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldResetProtocolConfig } from '../src/fieldRuleOptions.ts'

test('opening an existing protocol rule retains its extraction settings', () => {
  assert.equal(shouldResetProtocolConfig('PROTOCOL', undefined), false)
  assert.equal(shouldResetProtocolConfig('PROTOCOL', 'PROTOCOL'), false)
})

test('switching to or from protocol clears conditions of the previous source', () => {
  assert.equal(shouldResetProtocolConfig('PROTOCOL', 'LIMS'), true)
  assert.equal(shouldResetProtocolConfig('LIMS', 'PROTOCOL'), true)
  assert.equal(shouldResetProtocolConfig('PDF', 'LIMS'), false)
})
