export interface UserProfile {
  id: number | null;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  expires_at: string;
}

export interface Citation {
  document_title: string;
  chunk_id: string;
}

export interface SourceInfo {
  document_id: number;
  document_title: string;
  chunk_id: string | number;
  section?: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: SourceInfo[];
  citations: Citation[];
  retrieval_mode: 'hybrid' | 'vector' | 'keyword';
  documents_searched: number;
  prompt_access_level: 'guest' | 'system';
}

export interface SessionDocument {
  document_id: number;
  filename: string;
  chunks_created: number;
  created_at: string;
}

export interface PermissionItem {
  code: string;
  category: string;
  label: string;
  description: string;
}

export interface RoleItem {
  id: number;
  name: string;
  description: string;
  is_system: boolean;
  permissions: string[];
}

export interface AdminUserItem {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  role_id: number;
  role_name: string;
}
