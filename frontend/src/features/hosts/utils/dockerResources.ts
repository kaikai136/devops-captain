import type { DockerImage } from '../api/monitoring';

export function imageReferences(image: DockerImage) {
  if (image.references?.length) return image.references;
  const repositories = image.repositories ?? [];
  const tags = image.tags ?? [];
  if (repositories.length === 1 && tags.length) return tags.map((tag) => repositories[0] + ':' + tag);
  return repositories;
}

export function imageColumns(images: DockerImage[]) {
  return [
    { key: 'references', label: 'IMAGE', minWidth: 320 },
    { key: 'id', label: 'IMAGE ID', minWidth: 160 },
    { key: 'size', label: 'SIZE', minWidth: 140 },
    { key: 'createdAt', label: 'CREATED', minWidth: 200 },
    { key: 'contentSize', label: 'CONTENT SIZE', minWidth: 150 },
    { key: 'extra', label: 'EXTRA', minWidth: 120 },
  ].filter((column) => column.key === 'id' || images.some((image) => {
    if (column.key === 'references') return imageReferences(image).length > 0;
    return dockerField(imageValue(image, column.key)) !== '—';
  }));
}

export function imageValue(image: DockerImage, key: string) {
  if (key === 'size') return image.diskUsage?.trim() || image.size;
  return image[key as keyof DockerImage] as string | undefined;
}

export function shortDockerId(identifier: string) {
  return identifier.replace(/^sha256:/, '').slice(0, 12) || '—';
}

export function dockerField(value: string | null | undefined) {
  return value?.trim() || '—';
}
