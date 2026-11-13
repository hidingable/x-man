import test from 'node:test';
import assert from 'node:assert/strict';
import { total } from '../../src/cart.js';

const coupon = { threshold: 10000, off: 2000 };

test('满 100 减 20：买 120 元应付 100 元', () => {
  assert.equal(total([{ price: 120, qty: 1 }], coupon), 100);
});

test('正好 100 元也满足门槛', () => {
  assert.equal(total([{ price: 50, qty: 2 }], coupon), 80);
});

test('99.99 元不满足门槛', () => {
  assert.equal(total([{ price: 99.99, qty: 1 }], coupon), 99.99);
});
