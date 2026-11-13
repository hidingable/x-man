import test from 'node:test';
import assert from 'node:assert/strict';
import { revenue } from '../src/report.js';
import { needsPayReminder } from '../src/notify.js';
import { toShip } from '../src/shipping.js';

const orders = [
  { id: 'a', status: 'paid', amount: 100, createdAt: 0 },
  { id: 'b', status: 'pending', amount: 50, createdAt: 0 },
  { id: 'c', status: 'shipped', amount: 30, createdAt: 0 },
  { id: 'd', status: 'refunded', amount: 20, createdAt: 0 },
];

test('营收不含待支付和已退款订单', () => {
  assert.equal(revenue(orders), 130);
});

test('待支付超过 30 分钟才提醒', () => {
  assert.equal(needsPayReminder(orders[1], 31 * 60_000), true);
  assert.equal(needsPayReminder(orders[1], 10 * 60_000), false);
  assert.equal(needsPayReminder(orders[0], 31 * 60_000), false);
});

test('待发货只包含已支付订单', () => {
  assert.deepEqual(toShip(orders).map((o) => o.id), ['a']);
});
