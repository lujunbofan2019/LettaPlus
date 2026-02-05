import { spawn } from 'child_process';
import type { GenerationResult } from '../../shared/types.js';

export class GeneratorBridge {
  private pythonPath: string | null = null;
  private pythonVersion: string | null = null;

  /**
   * Check if Python is available and get version
   */
  async checkPython(): Promise<{
    available: boolean;
    version?: string;
    error?: string;
  }> {
    // Try different Python commands
    const pythonCommands = ['python3', 'python'];

    for (const cmd of pythonCommands) {
      try {
        const result = await this.runCommand(cmd, ['--version']);
        if (result.exitCode === 0) {
          const version = result.stdout.trim().replace('Python ', '');
          const [major, minor] = version.split('.').map(Number);

          if (major >= 3 && minor >= 9) {
            this.pythonPath = cmd;
            this.pythonVersion = version;
            return { available: true, version };
          } else {
            return {
              available: false,
              version,
              error: `Python ${version} found, but 3.9+ required`,
            };
          }
        }
      } catch {
        // Try next command
      }
    }

    return {
      available: false,
      error: 'Python not found in PATH. Please install Python 3.9+',
    };
  }

  /**
   * Check if dcf_mcp package is installed
   */
  async checkDcfMcp(): Promise<boolean> {
    if (!this.pythonPath) {
      await this.checkPython();
    }

    if (!this.pythonPath) return false;

    try {
      const result = await this.runCommand(this.pythonPath, [
        '-c',
        'import dcf_mcp; print("ok")',
      ]);
      return result.exitCode === 0 && result.stdout.includes('ok');
    } catch {
      return false;
    }
  }

  /**
   * Run generate_all from dcf_mcp
   */
  async generateAll(
    skillsSrcDir: string,
    generatedDir: string
  ): Promise<GenerationResult> {
    if (!this.pythonPath) {
      const check = await this.checkPython();
      if (!check.available) {
        return {
          status: 'error',
          error: check.error || 'Python not available',
        };
      }
    }

    const script = `
import json
import sys
try:
    from dcf_mcp.tools.dcf.generate import generate_all
    result = generate_all(
        skills_src_dir='${skillsSrcDir.replace(/\\/g, '\\\\')}',
        generated_dir='${generatedDir.replace(/\\/g, '\\\\')}'
    )
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({"status": "error", "error": str(e)}))
    sys.exit(1)
`;

    try {
      const result = await this.runCommand(this.pythonPath!, ['-c', script]);

      if (result.exitCode !== 0) {
        return {
          status: 'error',
          error: result.stderr || 'Generation failed',
        };
      }

      try {
        return JSON.parse(result.stdout) as GenerationResult;
      } catch {
        return {
          status: 'error',
          error: `Failed to parse output: ${result.stdout}`,
        };
      }
    } catch (err) {
      return {
        status: 'error',
        error: `Execution error: ${err}`,
      };
    }
  }

  /**
   * Run a command and capture output
   */
  private runCommand(
    command: string,
    args: string[]
  ): Promise<{ exitCode: number; stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      const proc = spawn(command, args, {
        shell: process.platform === 'win32',
        env: { ...process.env },
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      proc.on('close', (code) => {
        resolve({
          exitCode: code ?? 1,
          stdout,
          stderr,
        });
      });

      proc.on('error', (err) => {
        reject(err);
      });
    });
  }

  /**
   * Get Python path
   */
  getPythonPath(): string | null {
    return this.pythonPath;
  }

  /**
   * Get Python version
   */
  getPythonVersion(): string | null {
    return this.pythonVersion;
  }
}

// Singleton instance
export const generatorBridge = new GeneratorBridge();
