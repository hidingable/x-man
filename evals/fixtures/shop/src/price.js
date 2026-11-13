export function formatPrice(amount) {
  const sign = amount < 0 ? '-' : '';
  return `${sign}¥${Math.abs(amount).toFixed(2)}`;
}
