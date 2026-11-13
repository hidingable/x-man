import test from 'node:test';
import assert from 'node:assert/strict';
import { listOrders, findOrder } from '../src/orders.js';

const orders = [
  { id: 'a', status: 'paid', createdAt: 1 },
  { id: 'b', status: 'pending', createdAt: 3 },
  { id: 'c', status: 'shipped', createdAt: 2 },
];

test('订单按创建时间倒序', () => {
  assert.deepEqual(listOrders(orders).map((o) => o.id), ['b', 'c', 'a']);
});

test('按 id 查找订单，找不到返回 null', () => {
  assert.equal(findOrder(orders, 'c').status, 'shipped');
  assert.equal(findOrder(orders, 'x'), null);
});
