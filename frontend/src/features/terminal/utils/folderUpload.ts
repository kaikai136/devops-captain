export function folderUploadItems(files: File[], contentsOnly: boolean) {
  return files.map((file) => {
    const relativePath = file.webkitRelativePath || file.name;
    const parts = relativePath.split('/');
    return { file, relativePath: contentsOnly && parts.length > 1 ? parts.slice(1).join('/') : relativePath };
  });
}
