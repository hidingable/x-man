// 订单状态：pending（待支付）、paid（已支付）、shipped（已发货）、refunded（已退款）

export function listOrders(orders) {
  return [...orders].sort((a, b) => b.createdAt - a.createdAt);
}

export function findOrder(orders, id) {
  return orders.find((order) => order.id === id) ?? null;
}

// 退款：把订单标记为已退款，并把退款金额记入账户余额。
export function refund(order, account) {
  order.status = 'refunded';
  account.balance += order.amount;
  return order;
}
