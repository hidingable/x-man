import test from 'node:test';
import assert from 'node:assert/strict';
import { filterOrders } from '../../src/orders.js';

const orders = [
  { id: 'a', status: 'paid', createdAt: 1 },
  { id: 'b', status: 'pending', createdAt: 3 },
  { id: 'c', status: 'paid', createdAt: 2 },
];

test('按状态筛选并保持倒序', () => {
  assert.deepEqual(filterOrders(orders, 'paid').map((o) => o.id), ['c', 'a']);
});

test('all 返回全部订单', () => {
  assert.equal(filterOrders(orders, 'all').length, 3);
});

test('未知状态报错并带上状态值', () => {
  assert.throws(() => filterOrders(orders, 'cancelled'), /cancelled/);
});
