import test from 'node:test';
import assert from 'node:assert/strict';
import { subtotal, total } from '../src/cart.js';

test('小计按单价乘数量累加', () => {
  assert.equal(subtotal([{ price: 10, qty: 2 }, { price: 5, qty: 1 }]), 25);
});

test('没有券时总价等于小计', () => {
  assert.equal(total([{ price: 30, qty: 1 }]), 30);
});

test('不满门槛不减', () => {
  assert.equal(total([{ price: 50, qty: 1 }], { threshold: 10000, off: 2000 }), 50);
});
