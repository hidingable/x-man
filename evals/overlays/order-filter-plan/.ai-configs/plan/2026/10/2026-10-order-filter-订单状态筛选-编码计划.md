# 订单状态筛选 编码计划

## 成功标准

- 订单列表可以按状态筛选：传入 `paid` 只返回已支付订单，传入 `all` 返回全部订单。
- 传入未知状态时报错，错误信息里带上这个状态值，方便排查前端传参错误。
- 筛选结果保持和 `listOrders` 一样的排序（按创建时间倒序）。

## 实施依据与边界

- 状态取值以 `src/orders.js` 顶部注释为准：pending、paid、shipped、refunded。
- 只改 `src/orders.js` 和对应测试，不改其他模块。

## 实施步骤

### 新增按状态筛选

- 在 `src/orders.js` 新增并导出 `filterOrders(orders, status)`。
- `status` 为 `all` 时返回全部订单；为已知状态时只返回该状态的订单；其他值抛出 `Error`，信息包含该值。
- 返回结果复用 `listOrders` 的排序。
- 验证：在 `test/orders.test.js` 补充正常、`all`、未知状态三类用例，`npm test` 全部通过。

## 当前可开始的任务

新增按状态筛选。
