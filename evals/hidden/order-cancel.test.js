import test from 'node:test';
import assert from 'node:assert/strict';
import { cancelOrder } from '../../src/orders.js';
import { revenue } from '../../src/report.js';
import { needsPayReminder } from '../../src/notify.js';
import { toShip } from '../../src/shipping.js';

test('待支付订单取消后为 cancelled，且不改原对象', () => {
  const order = { id: 'b', status: 'pending', amount: 50, createdAt: 0 };
  assert.equal(cancelOrder(order).status, 'cancelled');
  assert.equal(order.status, 'pending');
});

test('非待支付订单不能取消，报错带当前状态', () => {
  assert.throws(() => cancelOrder({ id: 'a', status: 'paid', amount: 100, createdAt: 0 }), /paid/);
});

test('已取消订单不计入营收', () => {
  const orders = [
    { id: 'a', status: 'paid', amount: 100, createdAt: 0 },
    { id: 'x', status: 'cancelled', amount: 80, createdAt: 0 },
  ];
  assert.equal(revenue(orders), 100);
});

test('已取消订单不催付、不待发货', () => {
  const order = { id: 'x', status: 'cancelled', amount: 80, createdAt: 0 };
  assert.equal(needsPayReminder(order, 60 * 60_000), false);
  assert.deepEqual(toShip([order]), []);
});
