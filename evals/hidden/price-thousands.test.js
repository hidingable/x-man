import test from 'node:test';
import assert from 'node:assert/strict';
import { formatPrice } from '../../src/price.js';

test('整数部分加千分位', () => {
  assert.equal(formatPrice(1234567.5), '¥1,234,567.50');
});

test('不足四位不加分隔符', () => {
  assert.equal(formatPrice(999), '¥999.00');
});

test('负数保留原有的符号位置', () => {
  assert.equal(formatPrice(-1234), '-¥1,234.00');
});
