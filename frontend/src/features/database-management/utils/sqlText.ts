const FORMAT_KEYWORDS = /\b(SELECT|FROM|WHERE|ORDER BY|GROUP BY|HAVING|LIMIT|INSERT INTO|UPDATE|DELETE FROM|CREATE TABLE)\b/gi;

function transformSql(source: string, formatted: boolean): string {
  let result = '';
  let code = '';
  let index = 0;
  const flush = () => {
    const normalized = code.replace(/\s+/g, ' ');
    result += formatted ? normalized.replace(FORMAT_KEYWORDS, '\n$1') : normalized;
    code = '';
  };
  while (index < source.length) {
    const char = source[index];
    const next = source[index + 1];
    if (char === "'" || char === '"' || char === '`' || char === '[') {
      flush();
      const closing = char === '[' ? ']' : char;
      let segment = char;
      index++;
      while (index < source.length) {
        const current = source[index];
        segment += current;
        index++;
        if (current === '\\' && index < source.length) {
          segment += source[index++];
        } else if (current === closing) {
          if (source[index] === closing) segment += source[index++];
          else break;
        }
      }
      result += segment;
      continue;
    }
    if (char === '-' && next === '-' || char === '/' && next === '*') {
      flush();
      const line = char === '-';
      const end = line ? source.indexOf('\n', index) : source.indexOf('*/', index + 2);
      const stop = end < 0 ? source.length : end + (line ? 1 : 2);
      result += source.slice(index, stop);
      index = stop;
      continue;
    }
    code += char;
    index++;
  }
  flush();
  return result.trim();
}

export const formatSqlText = (source: string) => transformSql(source, true);
export const compressSqlText = (source: string) => transformSql(source, false);
