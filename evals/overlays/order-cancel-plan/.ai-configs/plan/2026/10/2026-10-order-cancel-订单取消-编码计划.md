# 订单取消 编码计划

**依据**：.ai-configs/analysis/2026/10/2026-10-order-cancel-订单取消-需求分析.md

## 成功标准

待支付订单可以取消为 `cancelled`；非待支付订单取消时报错并带上当前状态；已取消订单不计入营收、不收催付提醒、不进入待发货列表。

## 实施依据与边界

- 状态取值以 `src/orders.js` 顶部注释为准，本次新增 `cancelled`。
- 本次修改范围：`src/orders.js` 和对应测试。

## 实施步骤

### 让待支付订单可以取消

- [ ] **新增 cancelOrder**
  - 交付行为：调用 `cancelOrder(order)` 后，待支付订单变为已取消；其他状态报错。
  - 修改：`src/orders.js`
  - 做法：新增并导出 `cancelOrder(order)`。`order.status` 为 `pending` 时返回 `{ ...order, status: 'cancelled' }`，不修改传入对象；否则抛出 `Error`，信息包含当前状态。顶部状态注释补上 `cancelled（已取消）`。
  - 验证：在 `test/orders.test.js` 补充待支付取消成功、已支付取消报错、原对象未被修改三类用例，`npm test` 全部通过。
  - 依赖：无
