import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { chewieLogoSources } from '../lib/chewie-company-logo.ts';
const root = new URL('../public/', import.meta.url);
const catalog = JSON.parse(readFileSync(new URL('company-marks/b3-catalog.json', root)));
const sources = JSON.parse(readFileSync(new URL('company-marks/b3-catalog-sources.json', root)));
test('all 103 current constituents have local assets matching recorded hashes', () => {
  assert.equal(Object.keys(catalog).length,103);
  for(const item of sources) {
    assert.equal(catalog[item.symbol],item.path);
    const bytes=readFileSync(new URL('.'+item.path,root));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),item.sha256);
    assert.equal(chewieLogoSources('B3',item.symbol,'https://icons.brapi.dev/icons/BRAPI.svg')[0],item.path);
  }
});
test('reported issuers use distinct company identities',()=>{
  assert.equal(chewieLogoSources('B3','ITSA4')[0],'/company-marks/itausa.png');
  assert.equal(chewieLogoSources('B3','AXIA7')[0],'/company-marks/axia.svg');
  assert.equal(chewieLogoSources('B3','EMBJ3')[0],'/company-marks/embraer.svg');
  assert.deepEqual(chewieLogoSources(' b3 ',' itsa4.sa '),chewieLogoSources('B3','ITSA4'));
});
test('new B3 companies resolve through two-source backend, independent of snapshot placeholders',()=>{
  for(const value of [null,'','https://icons.brapi.dev/icons/BRAPI.svg'])
    assert.deepEqual(chewieLogoSources('B3','NEWA3',value),['/api/v1/chewie-fundamentals/B3/NEWA3/logo']);
});
test('existing assets have an automatic recovery source',()=>{
  assert.equal(chewieLogoSources('B3','ABEV3')[1],'/api/v1/chewie-fundamentals/B3/ABEV3/logo');
});
test('market identity and unsafe URL handling remain isolated',()=>{
  assert.deepEqual(chewieLogoSources('NASDAQ','ITSA4'),[]);
  assert.deepEqual(chewieLogoSources('NASDAQ','ABC','/img/logos/US/abc.png'),['https://eodhd.com/img/logos/US/abc.png']);
  for(const value of ['javascript:alert(1)','data:image/svg+xml,x','http://example.com/logo.png','https://user:pass@example.com/logo.png']) assert.deepEqual(chewieLogoSources('NYSE','ABC',value),[]);
});
