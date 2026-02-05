// IPC channel names - shared between main and renderer
export const IPC_CHANNELS = {
  // Project management
  PROJECT_OPEN: 'project:open',
  PROJECT_GET_INFO: 'project:get-info',
  PROJECT_SET_PATH: 'project:set-path',

  // Skills CRUD
  SKILLS_LIST: 'skills:list',
  SKILLS_READ: 'skills:read',
  SKILLS_SAVE: 'skills:save',
  SKILLS_CREATE: 'skills:create',
  SKILLS_DELETE: 'skills:delete',

  // Tools catalog
  TOOLS_LIST: 'tools:list',
  TOOLS_GET_BY_SERVER: 'tools:get-by-server',

  // Validation
  VALIDATION_VALIDATE_SKILL: 'validation:validate-skill',
  VALIDATION_VALIDATE_ALL: 'validation:validate-all',

  // Generation
  GENERATION_GENERATE_ALL: 'generation:generate-all',
  GENERATION_CHECK_PYTHON: 'generation:check-python',

  // Export
  EXPORT_SKILL: 'export:skill',

  // File watching events (main -> renderer)
  WATCH_SKILL_CHANGED: 'watch:skill-changed',
  WATCH_SKILL_ADDED: 'watch:skill-added',
  WATCH_SKILL_REMOVED: 'watch:skill-removed',
} as const;

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS];
