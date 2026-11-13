import test from 'node:test';
import assert from 'node:assert/strict';
import { formatPrice } from '../src/price.js';

test('保留两位小数', () => {
  assert.equal(formatPrice(12.5), '¥12.50');
});

test('负数金额把符号放在货币符号前', () => {
  assert.equal(formatPrice(-3), '-¥3.00');
});
