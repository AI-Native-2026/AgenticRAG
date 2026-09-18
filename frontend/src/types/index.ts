export interface User {
  username: string
  tenant: string
  role: 'admin' | 'member' | string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Datasource {
  ds_id: string
  name: string
  type: 'file' | 'database' | 'web' | string
  subtype: string
  tenant: string
  kb_id?: string | null
  config: Record<string, any>
  status: string
  resource_count: number
  chunk_count: number
  last_sync_at?: number | null
  created_at?: number
  has_credentials?: boolean
}

export interface Job {
  job_id: string
  datasource_id: string
  tenant: string
  mode: string
  status: 'pending' | 'running' | 'success' | 'failed' | string
  progress?: number | null
  total: number
  processed: number
  chunks: number
  skipped: number
  failed: number
  error?: string | null
  created_at: number
  started_at?: number | null
  finished_at?: number | null
  stats?: Record<string, any>
}

export interface KnowledgeBase {
  kb_id: string
  name: string
  slug: string
  description: string
  tenant: string
  datasource_ids: string[]
  datasource_count?: number
  chunk_count?: number
  status: string
}

export interface DocumentItem {
  ref_doc_id: string
  doc_name: string
  doc_type: string
  source_type: string
  datasource_id?: string
  doc_version: number
  chunks: number
}

export interface Chunk {
  node_id: string
  chunk_idx: number
  text: string
  metadata: Record<string, any>
  datasource_id?: string
  source_type?: string
}

export interface RetrievalResult {
  rank: number
  node_id: string
  text: string
  doc_name: string
  source_type: string
  datasource_id: string
  modality?: string
  media_path?: string
  table?: string
  page?: number | string
  vector_score?: number
  bm25_score?: number
  rrf_score?: number
  rerank_score?: number
}

export interface TableSchema {
  table: string
  columns: { name: string; type: string; nullable?: boolean; pk?: boolean }[]
  ddl: string
  sample_rows: Record<string, any>[]
  row_count: number
}

export interface ChatStep {
  event: string
  data: Record<string, any>
}
