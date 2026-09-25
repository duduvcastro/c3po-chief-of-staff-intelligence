import assert from 'node:assert/strict';
import test from 'node:test';
import { positionTotalCost } from '../lib/portfolio-cost.ts';
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
