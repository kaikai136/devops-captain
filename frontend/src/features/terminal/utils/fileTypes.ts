export function terminalFileImageMime(filename: string): string {
  const extension = filename.toLowerCase().split('.').pop() || '';
  const types: Record<string, string> = {
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp',
    svg: 'image/svg+xml', bmp: 'image/bmp', ico: 'image/x-icon', avif: 'image/avif',
  };
  return types[extension] || 'application/octet-stream';
}
