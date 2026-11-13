// 催付提醒：下单超过 30 分钟还没付款的订单，给用户发一次提醒。

const REMIND_AFTER_MS = 30 * 60_000;

export function needsPayReminder(order, now) {
  return order.status === 'pending' && now - order.createdAt > REMIND_AFTER_MS;
}
