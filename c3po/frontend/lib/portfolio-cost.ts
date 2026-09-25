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

/** Remove storage padding without changing the quantity of an existing holding. */
export function quantityInput(value: string): string {
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}
export function unitCostInput(value: string): string {
  const [whole, fraction = ''] = decimalInput(value).split('.');
  const scaled = BigInt(whole + fraction.padEnd(3, '0').slice(0, 3))
    + BigInt(Number((fraction[3] ?? '0') >= '5'));
  const digits = scaled.toString().padStart(4, '0');
  return `${digits.slice(0, -3)}.${digits.slice(-3)}`;
}

/** Brazilian editor syntax: dots group thousands, comma separates decimals. */
export function brazilianInput(value: string): string {
  const compact = value.trim();
  if (!/^(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,10})?$/.test(compact)) {
    throw new Error('Use ponto para milhares e vírgula para decimais. Exemplo: 243.175,50.');
  }
  return decimalInput(compact.replace(/\./g, '').replace(',', '.'));
}
export function brazilianDisplay(value: string, places?: number): string {
  if (!value) return '';
  const [whole, fraction = ''] = decimalInput(value).split('.');
  let integral = whole, decimals = fraction.replace(/0+$/, '');
  if (places !== undefined) {
    const scaled = BigInt(whole + fraction.padEnd(places, '0').slice(0, places))
      + BigInt(Number((fraction[places] ?? '0') >= '5'));
    const digits = scaled.toString().padStart(places + 1, '0');
    integral = places ? digits.slice(0, -places) : digits;
    decimals = places ? digits.slice(-places) : '';
  }
  return integral.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (decimals ? `,${decimals}` : '');
}
