import { describe, expect, it } from 'vitest';

import { compressSqlText, formatSqlText } from '../utils/sqlText';

describe('SQL text commands', () => {
  it('formats clauses without changing quoted values or identifiers', () => {
    const source = "select  'ORDER   BY' as \"from name\", `where field`, [select key]  from  users where note = 'it''s  here' order by id";
    const formatted = formatSqlText(source);

    expect(formatted).toContain("'ORDER   BY'");
    expect(formatted).toContain('"from name"');
    expect(formatted).toContain('`where field`');
    expect(formatted).toContain('[select key]');
    expect(formatted).toContain("'it''s  here'");
    expect(formatted).toMatch(/\nfrom users\s+\nwhere note/iu);
    expect(formatted).toMatch(/\norder by id$/iu);
  });

  it('compresses whitespace outside literals and comments only', () => {
    const source = "SELECT  'a  b'  AS value  /* keep  FROM */\nFROM  items -- keep  WHERE\nWHERE  id = 1";
    const compressed = compressSqlText(source);

    expect(compressed).toContain("'a  b'");
    expect(compressed).toContain('/* keep  FROM */');
    expect(compressed).toContain('-- keep  WHERE\n');
    expect(compressed).toContain('FROM items');
    expect(compressed).toContain('WHERE id = 1');
  });

  it('preserves escaped quotes and keyword-like text in strings', () => {
    const source = String.raw`SELECT  'from \'  where' , "order "" by"  FROM  logs`;

    for (const result of [formatSqlText(source), compressSqlText(source)]) {
      expect(result).toContain(String.raw`'from \'  where'`);
      expect(result).toContain('"order "" by"');
    }
  });
});
