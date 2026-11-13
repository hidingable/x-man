// 营收报表：只统计真正收到钱、且没有退回去的订单。

export function revenue(orders) {
  return orders
    .filter((order) => order.status !== 'pending' && order.status !== 'refunded')
    .reduce((sum, order) => sum + order.amount, 0);
}
