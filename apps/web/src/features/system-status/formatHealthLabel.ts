const labels: Record<string, string> = {
  database: '数据库',
  data_directories: '数据目录',
  master_key: '主密钥',
}

export function formatHealthLabel(name: string): string {
  return labels[name] ?? name
}
