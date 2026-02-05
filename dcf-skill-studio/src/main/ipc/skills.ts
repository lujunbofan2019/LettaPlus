import { ipcMain } from 'electron';
import path from 'path';
import { IPC_CHANNELS } from '../../shared/ipc-channels.js';
import { fileService } from '../services/FileService.js';
import { yamlService } from '../services/YamlService.js';
import { validationService } from '../services/ValidationService.js';
import { watcherService } from '../services/WatcherService.js';
import type { SkillFile, SkillDefinition } from '../../shared/types.js';

let currentProjectPath: string | null = null;

/**
 * Set the current project path (called from main process)
 */
export const setProjectPath = (projectPath: string | null): void => {
  currentProjectPath = projectPath;
  if (projectPath) {
    watcherService.start(projectPath);
  } else {
    watcherService.stop();
  }
};

/**
 * Get the current project path
 */
export const getProjectPath = (): string | null => currentProjectPath;

/**
 * Register skills IPC handlers
 */
export const registerSkillsHandlers = (): void => {
  // List all skills in project
  ipcMain.handle(IPC_CHANNELS.SKILLS_LIST, async (): Promise<SkillFile[]> => {
    if (!currentProjectPath) {
      return [];
    }

    const skillsSrcPath = path.join(currentProjectPath, 'skills_src');
    const skillFiles = await fileService.glob('**/*.skill.yaml', skillsSrcPath);

    const skills: SkillFile[] = [];

    for (const relativePath of skillFiles) {
      const fullPath = path.join(skillsSrcPath, relativePath);
      try {
        const skill = await yamlService.readSkillFile(fullPath);
        const validationErrors = validationService.validate(skill);

        skills.push({
          path: fullPath,
          relativePath,
          name: skill.metadata.name,
          skill,
          validationErrors,
          isDirty: false,
        });
      } catch (err) {
        // Include file with parse error
        skills.push({
          path: fullPath,
          relativePath,
          name: path.basename(relativePath, '.skill.yaml'),
          skill: createEmptySkill(),
          validationErrors: [
            {
              path: '/',
              message: `Failed to parse: ${err}`,
              severity: 'error',
            },
          ],
          isDirty: false,
        });
      }
    }

    // Sort by name
    skills.sort((a, b) => a.name.localeCompare(b.name));

    return skills;
  });

  // Read a single skill
  ipcMain.handle(
    IPC_CHANNELS.SKILLS_READ,
    async (_event, skillPath: string): Promise<SkillFile> => {
      const skill = await yamlService.readSkillFile(skillPath);
      const validationErrors = validationService.validate(skill);

      const relativePath = currentProjectPath
        ? path.relative(path.join(currentProjectPath, 'skills_src'), skillPath)
        : skillPath;

      return {
        path: skillPath,
        relativePath,
        name: skill.metadata.name,
        skill,
        validationErrors,
        isDirty: false,
      };
    }
  );

  // Save a skill
  ipcMain.handle(
    IPC_CHANNELS.SKILLS_SAVE,
    async (
      _event,
      skillPath: string,
      skill: SkillDefinition
    ): Promise<{ success: boolean; error?: string }> => {
      try {
        await yamlService.writeSkillFile(skillPath, skill);
        return { success: true };
      } catch (err) {
        return { success: false, error: `${err}` };
      }
    }
  );

  // Create a new skill
  ipcMain.handle(
    IPC_CHANNELS.SKILLS_CREATE,
    async (
      _event,
      name: string,
      template?: string
    ): Promise<SkillFile> => {
      if (!currentProjectPath) {
        throw new Error('No project open');
      }

      // Parse name to determine category and skill name
      const parts = name.split('.');
      let category = 'misc';
      let skillName = name;

      if (parts.length === 2) {
        category = parts[0];
        skillName = parts[1];
      }

      const skillsSrcPath = path.join(currentProjectPath, 'skills_src', 'skills', category);
      const fileName = `${skillName}.skill.yaml`;
      const fullPath = path.join(skillsSrcPath, fileName);

      // Check if file already exists
      if (await fileService.exists(fullPath)) {
        throw new Error(`Skill file already exists: ${fullPath}`);
      }

      // Create skill from template or default
      const skill = template
        ? await loadTemplate(template)
        : createDefaultSkill(name);

      // Ensure directory exists and write file
      await yamlService.writeSkillFile(fullPath, skill);

      const validationErrors = validationService.validate(skill);

      return {
        path: fullPath,
        relativePath: path.join('skills', category, fileName),
        name: skill.metadata.name,
        skill,
        validationErrors,
        isDirty: false,
      };
    }
  );

  // Delete a skill
  ipcMain.handle(
    IPC_CHANNELS.SKILLS_DELETE,
    async (
      _event,
      skillPath: string
    ): Promise<{ success: boolean; error?: string }> => {
      try {
        await fileService.deleteFile(skillPath);
        return { success: true };
      } catch (err) {
        return { success: false, error: `${err}` };
      }
    }
  );
};

/**
 * Create an empty skill definition
 */
const createEmptySkill = (): SkillDefinition => ({
  apiVersion: 'skill/v1',
  kind: 'Skill',
  metadata: {
    manifestId: '',
    name: '',
    version: '0.1.0',
    description: '',
    tags: [],
  },
  permissions: {
    egress: false,
    secrets: false,
    riskLevel: 'low',
  },
  directives: '',
  tools: [],
  dataSources: [],
  tests: [],
});

/**
 * Create a default skill with given name
 */
const createDefaultSkill = (name: string): SkillDefinition => ({
  apiVersion: 'skill/v1',
  kind: 'Skill',
  metadata: {
    manifestId: `skill.${name}@0.1.0`,
    name,
    version: '0.1.0',
    description: `Description for ${name} skill`,
    tags: [],
  },
  permissions: {
    egress: false,
    secrets: false,
    riskLevel: 'low',
  },
  directives: `# ${name} Skill\n\nProvide clear instructions for using this skill.`,
  tools: [],
  dataSources: [],
  tests: [],
});

/**
 * Load a skill template
 */
const loadTemplate = async (templateName: string): Promise<SkillDefinition> => {
  // Templates would be loaded from resources/templates
  // For now, return default skill
  return createDefaultSkill(templateName);
};
