import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import path from 'path';
import { registerSkillsHandlers, setProjectPath } from './ipc/skills.js';
import { registerToolsHandlers } from './ipc/tools.js';
import { registerValidationHandlers } from './ipc/validation.js';
import { registerGenerationHandlers } from './ipc/generation.js';
import { registerExportHandlers } from './ipc/export.js';
import { IPC_CHANNELS } from '../shared/ipc-channels.js';
import type { ProjectInfo } from '../shared/types.js';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
// Electron Forge adds this module during packaging
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const squirrelStartup = require('electron-squirrel-startup');
  if (squirrelStartup) {
    app.quit();
  }
} catch {
  // Module not available in dev mode
}

let mainWindow: BrowserWindow | null = null;
let currentProjectPath: string | null = null;

const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    title: 'DCF Skill Studio',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // Required for some Node.js APIs in preload
    },
  });

  // Load the renderer
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`)
    );
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
};

// Project management IPC handlers
const registerProjectHandlers = () => {
  ipcMain.handle(IPC_CHANNELS.PROJECT_OPEN, async (): Promise<ProjectInfo | null> => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openDirectory'],
      title: 'Select LettaPlus Project Directory',
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    currentProjectPath = result.filePaths[0];
    setProjectPath(currentProjectPath);
    return getProjectInfo(currentProjectPath);
  });

  ipcMain.handle(IPC_CHANNELS.PROJECT_GET_INFO, async (): Promise<ProjectInfo | null> => {
    if (!currentProjectPath) return null;
    return getProjectInfo(currentProjectPath);
  });

  ipcMain.handle(
    IPC_CHANNELS.PROJECT_SET_PATH,
    async (_event, projectPath: string): Promise<ProjectInfo | null> => {
      currentProjectPath = projectPath;
      setProjectPath(projectPath);
      return getProjectInfo(projectPath);
    }
  );
};

const getProjectInfo = async (projectPath: string): Promise<ProjectInfo> => {
  const fs = await import('fs/promises');
  const { glob } = await import('glob');

  const name = path.basename(projectPath);
  const skillsSrcPath = path.join(projectPath, 'skills_src');

  let skillsCount = 0;
  let toolsCount = 0;
  let hasValidConfig = false;

  try {
    await fs.access(skillsSrcPath);
    hasValidConfig = true;

    // Count skills
    const skillFiles = await glob('**/*.skill.yaml', { cwd: skillsSrcPath });
    skillsCount = skillFiles.length;

    // Check for tools index
    const toolsIndexPath = path.join(skillsSrcPath, 'tools', '_index.yaml');
    try {
      await fs.access(toolsIndexPath);
      // Could parse and count tools here
      toolsCount = 0; // Will be populated by tools service
    } catch {
      // No tools index
    }
  } catch {
    hasValidConfig = false;
  }

  return {
    path: projectPath,
    name,
    skillsCount,
    toolsCount,
    hasValidConfig,
  };
};

// Get current project path (for other handlers)
export const getCurrentProjectPath = (): string | null => currentProjectPath;

app.whenReady().then(() => {
  createWindow();

  // Register all IPC handlers
  registerProjectHandlers();
  registerSkillsHandlers();
  registerToolsHandlers();
  registerValidationHandlers();
  registerGenerationHandlers();
  registerExportHandlers();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Declare global types for Vite
declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;
