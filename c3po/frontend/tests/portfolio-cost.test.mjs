import assert from 'node:assert/strict';
import test from 'node:test';
import { positionTotalCost, quantityInput, unitCostInput, brazilianInput, brazilianDisplay } from '../lib/portfolio-cost.ts';
test('AMZN uses 2250 times the per-share cost, not one share as the total basis', () => {
  assert.equal(positionTotalCost('2250', '108.078', 'unit'), '243175.500');
  assert.equal(positionTotalCost('2250', '108,078', 'unit'), '243175.500');
});
test('existing total costs are not multiplied again', () => {
  assert.equal(positionTotalCost('2250', '243175.50', 'total'), '243175.50');
  assert.equal(positionTotalCost('2250', '108.078', 'total'), '108.078');
});
test('fractional quantities and decimal multiplication remain exact', () => {
  assert.equal(positionTotalCost('0.1', '0.2', 'unit'), '0.02');
  assert.equal(positionTotalCost('1.0000000001', '0.5', 'unit'), '0.5000000001');
  assert.equal(positionTotalCost('0', '108.078', 'unit'), '0.000');
});
test('invalid and overflowing amounts cannot become ledger totals', () => {
  for (const input of ['', '-1', 'NaN', '1e3', '1,2,3', '1.000,20']) assert.throws(() => positionTotalCost('2250', input, 'unit'));
  assert.throws(() => positionTotalCost('999999999999999999', '10', 'unit'));
});

test('quantity storage padding is removed without truncating existing fractional holdings', () => {
  assert.equal(quantityInput('2250.0000000000'), '2250');
  assert.equal(quantityInput('0.5000000000'), '0.5');
});
test('per-share input has exactly three decimals and preserves the AMZN total', () => {
  assert.equal(unitCostInput('108.0780000000'), '108.078');
  assert.equal(unitCostInput('108,1'), '108.100');
  assert.equal(unitCostInput('108.9999'), '109.000');
  assert.equal(positionTotalCost('2250', unitCostInput('108.078'), 'unit'), '243175.500');
});

test('Brazilian editor round-trips grouped quantity and two-decimal total', () => {
  assert.equal(brazilianDisplay('2250.0000000000'), '2.250');
  assert.equal(brazilianDisplay('243175.5000000000', 2), '243.175,50');
  assert.equal(brazilianDisplay('108.078', 3), '108,078');
  assert.equal(brazilianInput('2.250'), '2250');
  assert.equal(brazilianInput('243.175,50'), '243175.50');
  assert.equal(positionTotalCost(brazilianInput('2.250'), brazilianInput('108,078'), 'unit'), '243175.500');
  assert.equal(brazilianDisplay('999.999', 2), '1.000,00');
  assert.equal(brazilianInput('1.000.000,00'), '1000000.00');
  for (const invalid of ['24.31,50', '243175.50', '1,2,3']) assert.throws(() => brazilianInput(invalid));
});
