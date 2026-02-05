import { create } from 'zustand';
import type { ProjectInfo, SkillFile, ToolDefinition, ValidationError } from '../../shared/types';

interface ProjectState {
  // Project info
  project: ProjectInfo | null;
  isLoading: boolean;
  error: string | null;

  // Skills
  skills: SkillFile[];
  selectedSkillPath: string | null;
  skillsLoading: boolean;

  // Tools catalog
  tools: ToolDefinition[];
  toolsLoading: boolean;

  // Python/generation status
  pythonAvailable: boolean;
  pythonVersion: string | null;
  pythonError: string | null;
  isGenerating: boolean;
  generationResult: { status: string; error?: string; details?: string[] } | null;

  // Actions
  openProject: () => Promise<void>;
  setProject: (project: ProjectInfo | null) => void;
  loadSkills: () => Promise<void>;
  selectSkill: (path: string | null) => void;
  updateSkill: (path: string, skill: SkillFile['skill']) => Promise<void>;
  refreshSkill: (path: string) => Promise<void>;
  createSkill: (name: string) => Promise<void>;
  deleteSkill: (path: string) => Promise<void>;
  loadTools: () => Promise<void>;
  checkPython: () => Promise<void>;
  generateAll: () => Promise<void>;
  validateSkill: (skill: SkillFile['skill']) => Promise<ValidationError[]>;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  // Initial state
  project: null,
  isLoading: false,
  error: null,
  skills: [],
  selectedSkillPath: null,
  skillsLoading: false,
  tools: [],
  toolsLoading: false,
  pythonAvailable: false,
  pythonVersion: null,
  pythonError: null,
  isGenerating: false,
  generationResult: null,

  // Actions
  openProject: async () => {
    set({ isLoading: true, error: null });
    try {
      const project = await window.electronAPI.project.open();
      set({ project, isLoading: false });

      if (project) {
        // Load skills and tools after opening project
        get().loadSkills();
        get().loadTools();
        get().checkPython();
      }
    } catch (err) {
      set({ isLoading: false, error: `${err}` });
    }
  },

  setProject: (project) => {
    set({ project });
  },

  loadSkills: async () => {
    set({ skillsLoading: true });
    try {
      const skills = await window.electronAPI.skills.list();
      set({ skills, skillsLoading: false });
    } catch (err) {
      set({ skillsLoading: false, error: `${err}` });
    }
  },

  selectSkill: (path) => {
    set({ selectedSkillPath: path });
  },

  updateSkill: async (path, skill) => {
    const result = await window.electronAPI.skills.save(path, skill);
    if (result.success) {
      // Refresh the skill from disk
      await get().refreshSkill(path);
    } else {
      set({ error: result.error });
    }
  },

  refreshSkill: async (path) => {
    try {
      const updatedSkill = await window.electronAPI.skills.read(path);
      set((state) => ({
        skills: state.skills.map((s) => (s.path === path ? updatedSkill : s)),
      }));
    } catch (err) {
      set({ error: `${err}` });
    }
  },

  createSkill: async (name) => {
    try {
      const newSkill = await window.electronAPI.skills.create(name);
      set((state) => ({
        skills: [...state.skills, newSkill].sort((a, b) =>
          a.name.localeCompare(b.name)
        ),
        selectedSkillPath: newSkill.path,
      }));
    } catch (err) {
      set({ error: `${err}` });
    }
  },

  deleteSkill: async (path) => {
    const result = await window.electronAPI.skills.delete(path);
    if (result.success) {
      set((state) => ({
        skills: state.skills.filter((s) => s.path !== path),
        selectedSkillPath:
          state.selectedSkillPath === path ? null : state.selectedSkillPath,
      }));
    } else {
      set({ error: result.error });
    }
  },

  loadTools: async () => {
    set({ toolsLoading: true });
    try {
      const tools = await window.electronAPI.tools.list();
      set({ tools, toolsLoading: false });
    } catch (err) {
      set({ toolsLoading: false, error: `${err}` });
    }
  },

  checkPython: async () => {
    try {
      const result = await window.electronAPI.generation.checkPython();
      set({
        pythonAvailable: result.available,
        pythonVersion: result.version || null,
        pythonError: result.error || null,
      });
    } catch (err) {
      set({
        pythonAvailable: false,
        pythonError: `${err}`,
      });
    }
  },

  generateAll: async () => {
    set({ isGenerating: true, generationResult: null });
    try {
      const result = await window.electronAPI.generation.generateAll();
      set({ isGenerating: false, generationResult: result });

      if (result.status === 'success') {
        // Reload tools catalog after generation
        get().loadTools();
      }
    } catch (err) {
      set({
        isGenerating: false,
        generationResult: { status: 'error', error: `${err}` },
      });
    }
  },

  validateSkill: async (skill) => {
    return window.electronAPI.validation.validateSkill(skill);
  },
}));
