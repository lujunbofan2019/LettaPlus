import fs from 'fs/promises';
import { Stats } from 'fs';
import path from 'path';
import { glob } from 'glob';

export class FileService {
  /**
   * Check if a path exists
   */
  async exists(filePath: string): Promise<boolean> {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Read file contents as string
   */
  async readFile(filePath: string): Promise<string> {
    return fs.readFile(filePath, 'utf-8');
  }

  /**
   * Write string content to file
   */
  async writeFile(filePath: string, content: string): Promise<void> {
    // Ensure directory exists
    const dir = path.dirname(filePath);
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(filePath, content, 'utf-8');
  }

  /**
   * Delete a file
   */
  async deleteFile(filePath: string): Promise<void> {
    await fs.unlink(filePath);
  }

  /**
   * List files matching a glob pattern
   */
  async glob(pattern: string, cwd: string): Promise<string[]> {
    return glob(pattern, { cwd, absolute: false });
  }

  /**
   * List files matching a glob pattern with absolute paths
   */
  async globAbsolute(pattern: string, cwd: string): Promise<string[]> {
    return glob(pattern, { cwd, absolute: true });
  }

  /**
   * Get file stats
   */
  async stat(filePath: string): Promise<Stats> {
    return fs.stat(filePath);
  }

  /**
   * Create directory recursively
   */
  async mkdir(dirPath: string): Promise<void> {
    await fs.mkdir(dirPath, { recursive: true });
  }

  /**
   * Read directory contents
   */
  async readdir(dirPath: string): Promise<string[]> {
    return fs.readdir(dirPath);
  }

  /**
   * Copy file
   */
  async copyFile(src: string, dest: string): Promise<void> {
    const dir = path.dirname(dest);
    await fs.mkdir(dir, { recursive: true });
    await fs.copyFile(src, dest);
  }

  /**
   * Get relative path from base to target
   */
  relativePath(from: string, to: string): string {
    return path.relative(from, to);
  }

  /**
   * Join path segments
   */
  joinPath(...segments: string[]): string {
    return path.join(...segments);
  }

  /**
   * Get directory name
   */
  dirname(filePath: string): string {
    return path.dirname(filePath);
  }

  /**
   * Get base name
   */
  basename(filePath: string, ext?: string): string {
    return path.basename(filePath, ext);
  }

  /**
   * Get file extension
   */
  extname(filePath: string): string {
    return path.extname(filePath);
  }
}

// Singleton instance
export const fileService = new FileService();
