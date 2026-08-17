DELETE FROM ir_valuation_queue
WHERE market = 'B3' AND symbol ~ '[0-9]F$';

DELETE FROM ir_security_map
WHERE market = 'B3' AND symbol ~ '[0-9]F$';
