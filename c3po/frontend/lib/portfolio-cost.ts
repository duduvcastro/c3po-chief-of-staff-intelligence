/** The ledger always receives total cost, never a per-share price. */
export type CostMode = 'unit' | 'total';
export function decimalInput(value: string): string {
  const compact = value.trim().replace(/\s/g, '');
  const normalized = compact.replace(',', '.');
  if (!/^\d{1,18}(\.\d{1,10})?$/.test(normalized)) throw new Error('Use um número positivo, com até 10 casas decimais.');
  return normalized;
}
export function positionTotalCost(quantity: string, cost: string, mode: CostMode): string {
  const q = decimalInput(quantity), c = decimalInput(cost);
  if (mode === 'total') return c;
  const [qi, qf = ''] = q.split('.'), [ci, cf = ''] = c.split('.');
  let digits = BigInt(qi + qf) * BigInt(ci + cf);
  let scale = qf.length + cf.length;
  // Match the ledger's ten decimal places, without binary floating-point loss.
  if (scale > 10) {
    const divisor = BigInt(10) ** BigInt(scale - 10);
    digits = (digits + divisor / BigInt(2)) / divisor;
    scale = 10;
  }
  const raw = digits.toString().padStart(scale + 1, '0');
  const result = scale ? `${raw.slice(0, -scale)}.${raw.slice(-scale)}` : raw;
  return decimalInput(result);
}
