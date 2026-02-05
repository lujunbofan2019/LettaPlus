import { ipcMain } from 'electron';
import path from 'path';
import { IPC_CHANNELS } from '../../shared/ipc-channels.js';
import { generatorBridge } from '../services/GeneratorBridge.js';
import { getProjectPath } from './skills.js';
import { clearToolsCache } from './tools.js';
import type { GenerationResult } from '../../shared/types.js';

/**
 * Register generation IPC handlers
 */
export const registerGenerationHandlers = (): void => {
  // Check Python availability
  ipcMain.handle(
    IPC_CHANNELS.GENERATION_CHECK_PYTHON,
    async (): Promise<{ available: boolean; version?: string; error?: string }> => {
      return generatorBridge.checkPython();
    }
  );

  // Generate all artifacts
  ipcMain.handle(
    IPC_CHANNELS.GENERATION_GENERATE_ALL,
    async (): Promise<GenerationResult> => {
      const projectPath = getProjectPath();
      if (!projectPath) {
        return {
          status: 'error',
          error: 'No project open',
        };
      }

      const skillsSrcDir = path.join(projectPath, 'skills_src');
      const generatedDir = path.join(projectPath, 'generated');

      const result = await generatorBridge.generateAll(skillsSrcDir, generatedDir);

      // Clear tools cache so it reloads from fresh generated files
      if (result.status === 'success') {
        clearToolsCache();
      }

      return result;
    }
  );
};
