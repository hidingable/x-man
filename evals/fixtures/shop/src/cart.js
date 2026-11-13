// 满减券的金额以「分」存储，与后台券系统一致：{ threshold: 10000, off: 2000 } 表示满 100 元减 20 元。
// 商品价格以「元」为单位。

export function subtotal(items) {
  return items.reduce((sum, item) => sum + item.price * item.qty, 0);
}

export function total(items, coupon) {
  const sum = subtotal(items);
  if (!coupon) return sum;
  if (sum >= coupon.threshold) {
    return sum - coupon.off / 100;
  }
  return sum;
}
