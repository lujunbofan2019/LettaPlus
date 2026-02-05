import { ipcMain } from 'electron';
import path from 'path';
import { IPC_CHANNELS } from '../../shared/ipc-channels.js';
import { fileService } from '../services/FileService.js';
import { yamlService } from '../services/YamlService.js';
import { validationService } from '../services/ValidationService.js';
import { getProjectPath } from './skills.js';
import type { ToolDefinition, ToolsIndex, ToolsRegistry } from '../../shared/types.js';

// Cached tools catalog
let toolsCache: ToolDefinition[] | null = null;

/**
 * Load tools from the index file
 */
const loadTools = async (): Promise<ToolDefinition[]> => {
  const projectPath = getProjectPath();
  if (!projectPath) {
    return [];
  }

  const toolsIndexPath = path.join(projectPath, 'skills_src', 'tools', '_index.yaml');

  // Check if index exists, fall back to legacy tools.yaml
  let toolFiles: string[];
  const toolsDir = path.join(projectPath, 'skills_src', 'tools');

  if (await fileService.exists(toolsIndexPath)) {
    const index = await yamlService.readToolsIndex(toolsIndexPath);
    toolFiles = index.files || [];
  } else {
    // Legacy: single tools.yaml file
    const legacyPath = path.join(projectPath, 'skills_src', 'tools.yaml');
    if (await fileService.exists(legacyPath)) {
      toolFiles = ['../tools.yaml'];
    } else {
      return [];
    }
  }

  const tools: ToolDefinition[] = [];

  for (const file of toolFiles) {
    const filePath = path.resolve(toolsDir, file);
    try {
      const registry = await yamlService.readToolsRegistry(filePath);

      if (registry.tools && Array.isArray(registry.tools)) {
        for (const tool of registry.tools) {
          tools.push({
            ...tool,
            server: registry.server || tool.server || 'unknown',
          });
        }
      }
    } catch (err) {
      console.error(`Failed to load tools from ${filePath}:`, err);
    }
  }

  // Update validation service with tools catalog
  validationService.setToolsCatalog(tools);

  return tools;
};

/**
 * Clear tools cache (call when project changes)
 */
export const clearToolsCache = (): void => {
  toolsCache = null;
};

/**
 * Get tools (cached)
 */
const getTools = async (): Promise<ToolDefinition[]> => {
  if (!toolsCache) {
    toolsCache = await loadTools();
  }
  return toolsCache;
};

/**
 * Register tools IPC handlers
 */
export const registerToolsHandlers = (): void => {
  // List all tools
  ipcMain.handle(IPC_CHANNELS.TOOLS_LIST, async (): Promise<ToolDefinition[]> => {
    return getTools();
  });

  // Get tools by server
  ipcMain.handle(
    IPC_CHANNELS.TOOLS_GET_BY_SERVER,
    async (_event, server: string): Promise<ToolDefinition[]> => {
      const tools = await getTools();
      return tools.filter((t) => t.server === server);
    }
  );
};
