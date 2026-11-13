export function formatPrice(amount) {
  const [int, dec] = amount.toFixed(2).split('.');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `¥${grouped}.${dec}`;
}
