import chokidar, { FSWatcher } from 'chokidar';
import path from 'path';
import { BrowserWindow } from 'electron';
import { IPC_CHANNELS } from '../../shared/ipc-channels.js';

export class WatcherService {
  private watcher: FSWatcher | null = null;
  private projectPath: string | null = null;

  /**
   * Start watching a project directory for skill file changes
   */
  start(projectPath: string): void {
    this.stop(); // Stop any existing watcher

    this.projectPath = projectPath;
    const skillsPattern = path.join(projectPath, 'skills_src', '**', '*.skill.yaml');

    this.watcher = chokidar.watch(skillsPattern, {
      persistent: true,
      ignoreInitial: true,
      awaitWriteFinish: {
        stabilityThreshold: 300,
        pollInterval: 100,
      },
    });

    this.watcher
      .on('change', (filePath) => {
        this.notifyRenderer(IPC_CHANNELS.WATCH_SKILL_CHANGED, filePath);
      })
      .on('add', (filePath) => {
        this.notifyRenderer(IPC_CHANNELS.WATCH_SKILL_ADDED, filePath);
      })
      .on('unlink', (filePath) => {
        this.notifyRenderer(IPC_CHANNELS.WATCH_SKILL_REMOVED, filePath);
      })
      .on('error', (error) => {
        console.error('Watcher error:', error);
      });
  }

  /**
   * Stop watching
   */
  stop(): void {
    if (this.watcher) {
      this.watcher.close();
      this.watcher = null;
    }
    this.projectPath = null;
  }

  /**
   * Get current project path
   */
  getProjectPath(): string | null {
    return this.projectPath;
  }

  /**
   * Check if watcher is active
   */
  isActive(): boolean {
    return this.watcher !== null;
  }

  /**
   * Notify all renderer windows of a file event
   */
  private notifyRenderer(channel: string, filePath: string): void {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      if (!win.isDestroyed()) {
        win.webContents.send(channel, filePath);
      }
    }
  }
}

// Singleton instance
export const watcherService = new WatcherService();
