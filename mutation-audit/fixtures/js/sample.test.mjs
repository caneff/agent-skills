import test from 'node:test';
import assert from 'node:assert/strict';
import { isAdult, clamp } from './sample.mjs';

test('isAdult at and around its boundary', () => {
  assert.equal(isAdult(17), false);
  assert.equal(isAdult(18), true);
  assert.equal(isAdult(19), true);
});

test('clamp in range only', () => {
  assert.equal(clamp(5, 0, 10), 5);
});
