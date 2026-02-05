import { contextBridge, ipcRenderer } from 'electron';
import { IPC_CHANNELS } from '../shared/ipc-channels.js';
import type {
  SkillFile,
  SkillDefinition,
  ToolDefinition,
  ValidationError,
  GenerationResult,
  ProjectInfo,
} from '../shared/types.js';

// Type-safe API exposed to renderer
const electronAPI = {
  // Project management
  project: {
    open: (): Promise<ProjectInfo | null> =>
      ipcRenderer.invoke(IPC_CHANNELS.PROJECT_OPEN),
    getInfo: (): Promise<ProjectInfo | null> =>
      ipcRenderer.invoke(IPC_CHANNELS.PROJECT_GET_INFO),
    setPath: (path: string): Promise<ProjectInfo | null> =>
      ipcRenderer.invoke(IPC_CHANNELS.PROJECT_SET_PATH, path),
  },

  // Skills CRUD
  skills: {
    list: (): Promise<SkillFile[]> =>
      ipcRenderer.invoke(IPC_CHANNELS.SKILLS_LIST),
    read: (path: string): Promise<SkillFile> =>
      ipcRenderer.invoke(IPC_CHANNELS.SKILLS_READ, path),
    save: (
      path: string,
      skill: SkillDefinition
    ): Promise<{ success: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC_CHANNELS.SKILLS_SAVE, path, skill),
    create: (name: string, template?: string): Promise<SkillFile> =>
      ipcRenderer.invoke(IPC_CHANNELS.SKILLS_CREATE, name, template),
    delete: (path: string): Promise<{ success: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC_CHANNELS.SKILLS_DELETE, path),
  },

  // Tools catalog
  tools: {
    list: (): Promise<ToolDefinition[]> =>
      ipcRenderer.invoke(IPC_CHANNELS.TOOLS_LIST),
    getByServer: (server: string): Promise<ToolDefinition[]> =>
      ipcRenderer.invoke(IPC_CHANNELS.TOOLS_GET_BY_SERVER, server),
  },

  // Validation
  validation: {
    validateSkill: (skill: SkillDefinition): Promise<ValidationError[]> =>
      ipcRenderer.invoke(IPC_CHANNELS.VALIDATION_VALIDATE_SKILL, skill),
    validateAll: (): Promise<Map<string, ValidationError[]>> =>
      ipcRenderer.invoke(IPC_CHANNELS.VALIDATION_VALIDATE_ALL),
  },

  // Generation
  generation: {
    generateAll: (): Promise<GenerationResult> =>
      ipcRenderer.invoke(IPC_CHANNELS.GENERATION_GENERATE_ALL),
    checkPython: (): Promise<{
      available: boolean;
      version?: string;
      error?: string;
    }> => ipcRenderer.invoke(IPC_CHANNELS.GENERATION_CHECK_PYTHON),
  },

  // Export
  export: {
    skill: (
      skillPath: string,
      outputPath: string
    ): Promise<{ success: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC_CHANNELS.EXPORT_SKILL, skillPath, outputPath),
  },

  // File watching events
  onSkillChanged: (callback: (path: string) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, path: string) =>
      callback(path);
    ipcRenderer.on(IPC_CHANNELS.WATCH_SKILL_CHANGED, listener);
    return () =>
      ipcRenderer.removeListener(IPC_CHANNELS.WATCH_SKILL_CHANGED, listener);
  },
  onSkillAdded: (callback: (path: string) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, path: string) =>
      callback(path);
    ipcRenderer.on(IPC_CHANNELS.WATCH_SKILL_ADDED, listener);
    return () =>
      ipcRenderer.removeListener(IPC_CHANNELS.WATCH_SKILL_ADDED, listener);
  },
  onSkillRemoved: (callback: (path: string) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, path: string) =>
      callback(path);
    ipcRenderer.on(IPC_CHANNELS.WATCH_SKILL_REMOVED, listener);
    return () =>
      ipcRenderer.removeListener(IPC_CHANNELS.WATCH_SKILL_REMOVED, listener);
  },
};

// Expose to renderer via contextBridge
contextBridge.exposeInMainWorld('electronAPI', electronAPI);

// Type declaration for renderer
export type ElectronAPI = typeof electronAPI;
