// Shared types between main and renderer processes

export interface SkillMetadata {
  manifestId: string;
  name: string;
  version: string;
  description: string;
  tags: string[];
}

export interface SkillPermissions {
  egress: boolean;
  secrets: boolean;
  riskLevel: 'low' | 'medium' | 'high';
}

export interface ToolReference {
  name: string;
  server: string;
  required: boolean;
}

export interface DataSource {
  type: 'file' | 'url' | 'memory_block';
  path?: string;
  url?: string;
  blockLabel?: string;
}

export interface SkillDefinition {
  apiVersion: string;
  kind: string;
  metadata: SkillMetadata;
  permissions: SkillPermissions;
  directives: string;
  tools: ToolReference[];
  dataSources: DataSource[];
  tests?: SkillTest[];
}

export interface SkillTest {
  name: string;
  input: Record<string, unknown>;
  expectedOutput?: Record<string, unknown>;
}

export interface SkillFile {
  path: string;
  relativePath: string;
  name: string;
  skill: SkillDefinition;
  validationErrors: ValidationError[];
  isDirty: boolean;
}

export interface ValidationError {
  path: string;
  message: string;
  severity: 'error' | 'warning';
}

export interface ToolDefinition {
  name: string;
  description: string;
  server: string;
  parameters?: Record<string, ToolParameter>;
  returns?: Record<string, unknown>;
}

export interface ToolParameter {
  type: string;
  description?: string;
  required?: boolean;
  default?: unknown;
}

export interface ToolsIndex {
  apiVersion: string;
  kind: string;
  files: string[];
}

export interface ToolsRegistry {
  apiVersion: string;
  kind: string;
  server: string;
  tools: ToolDefinition[];
}

export interface GenerationResult {
  status: 'success' | 'error';
  manifests_generated?: number;
  catalog_updated?: boolean;
  stub_config_updated?: boolean;
  error?: string;
  details?: string[];
}

export interface ProjectInfo {
  path: string;
  name: string;
  skillsCount: number;
  toolsCount: number;
  hasValidConfig: boolean;
}

// IPC Channel types
export type IpcChannels = {
  // Project
  'project:open': () => Promise<ProjectInfo | null>;
  'project:get-info': () => Promise<ProjectInfo | null>;
  'project:set-path': (path: string) => Promise<ProjectInfo | null>;

  // Skills
  'skills:list': () => Promise<SkillFile[]>;
  'skills:read': (path: string) => Promise<SkillFile>;
  'skills:save': (path: string, skill: SkillDefinition) => Promise<{ success: boolean; error?: string }>;
  'skills:create': (name: string, template?: string) => Promise<SkillFile>;
  'skills:delete': (path: string) => Promise<{ success: boolean; error?: string }>;

  // Tools
  'tools:list': () => Promise<ToolDefinition[]>;
  'tools:get-by-server': (server: string) => Promise<ToolDefinition[]>;

  // Validation
  'validation:validate-skill': (skill: SkillDefinition) => Promise<ValidationError[]>;
  'validation:validate-all': () => Promise<Map<string, ValidationError[]>>;

  // Generation
  'generation:generate-all': () => Promise<GenerationResult>;
  'generation:check-python': () => Promise<{ available: boolean; version?: string; error?: string }>;

  // Export
  'export:skill': (path: string, outputPath: string) => Promise<{ success: boolean; error?: string }>;
};
