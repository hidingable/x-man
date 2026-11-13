// 待发货列表：已支付、还没发货的订单。

export function toShip(orders) {
  return orders.filter((order) => order.status === 'paid');
}
