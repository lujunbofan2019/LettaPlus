import { ipcMain } from 'electron';
import { IPC_CHANNELS } from '../../shared/ipc-channels.js';
import { validationService } from '../services/ValidationService.js';
import type { SkillDefinition, ValidationError } from '../../shared/types.js';

/**
 * Register validation IPC handlers
 */
export const registerValidationHandlers = (): void => {
  // Validate a single skill
  ipcMain.handle(
    IPC_CHANNELS.VALIDATION_VALIDATE_SKILL,
    async (_event, skill: SkillDefinition): Promise<ValidationError[]> => {
      return validationService.validate(skill);
    }
  );

  // Validate all skills
  ipcMain.handle(
    IPC_CHANNELS.VALIDATION_VALIDATE_ALL,
    async (): Promise<Map<string, ValidationError[]>> => {
      // This would iterate through all skills and validate each
      // For now, return empty map - full implementation would use skills service
      return new Map();
    }
  );
};
