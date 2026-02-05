import { ipcMain, dialog, BrowserWindow } from 'electron';
import path from 'path';
import archiver from 'archiver';
import { createWriteStream } from 'fs';
import { IPC_CHANNELS } from '../../shared/ipc-channels.js';
import { fileService } from '../services/FileService.js';
import { yamlService } from '../services/YamlService.js';
import { getProjectPath } from './skills.js';

/**
 * Register export IPC handlers
 */
export const registerExportHandlers = (): void => {
  // Export skill as zip
  ipcMain.handle(
    IPC_CHANNELS.EXPORT_SKILL,
    async (
      _event,
      skillPath: string,
      outputPath?: string
    ): Promise<{ success: boolean; error?: string }> => {
      try {
        const skill = await yamlService.readSkillFile(skillPath);
        const projectPath = getProjectPath();

        // If no output path provided, show save dialog
        if (!outputPath) {
          const result = await dialog.showSaveDialog(
            BrowserWindow.getFocusedWindow()!,
            {
              title: 'Export Skill',
              defaultPath: `${skill.metadata.name}-${skill.metadata.version}.zip`,
              filters: [{ name: 'ZIP Archives', extensions: ['zip'] }],
            }
          );

          if (result.canceled || !result.filePath) {
            return { success: false, error: 'Export cancelled' };
          }

          outputPath = result.filePath;
        }

        // Create zip archive
        const output = createWriteStream(outputPath);
        const archive = archiver('zip', { zlib: { level: 9 } });

        return new Promise((resolve) => {
          output.on('close', () => {
            resolve({ success: true });
          });

          archive.on('error', (err) => {
            resolve({ success: false, error: err.message });
          });

          archive.pipe(output);

          // Add skill YAML file
          archive.file(skillPath, { name: path.basename(skillPath) });

          // Add generated manifest if it exists
          if (projectPath) {
            const manifestName = `skill.${skill.metadata.name}-${skill.metadata.version}.json`;
            const manifestPath = path.join(
              projectPath,
              'generated',
              'manifests',
              manifestName
            );

            fileService.exists(manifestPath).then((exists) => {
              if (exists) {
                archive.file(manifestPath, { name: `manifest/${manifestName}` });
              }
            });
          }

          // Add README with skill documentation
          const readme = generateReadme(skill);
          archive.append(readme, { name: 'README.md' });

          archive.finalize();
        });
      } catch (err) {
        return { success: false, error: `${err}` };
      }
    }
  );
};

/**
 * Generate README content for a skill
 */
const generateReadme = (skill: {
  metadata: {
    name: string;
    version: string;
    description: string;
    tags: string[];
    manifestId: string;
  };
  permissions: {
    egress: boolean;
    secrets: boolean;
    riskLevel: string;
  };
  directives: string;
  tools: Array<{ name: string; server: string }>;
}): string => {
  const toolsList = skill.tools
    .map((t) => `- \`${t.name}\` (${t.server})`)
    .join('\n');

  return `# ${skill.metadata.name}

**Version:** ${skill.metadata.version}

**Manifest ID:** \`${skill.metadata.manifestId}\`

## Description

${skill.metadata.description}

## Tags

${skill.metadata.tags.map((t) => `\`${t}\``).join(', ') || 'None'}

## Permissions

| Permission | Value |
|------------|-------|
| Egress | ${skill.permissions.egress ? 'Yes' : 'No'} |
| Secrets | ${skill.permissions.secrets ? 'Yes' : 'No'} |
| Risk Level | ${skill.permissions.riskLevel} |

## Tools

${toolsList || 'No tools required'}

## Directives

\`\`\`
${skill.directives}
\`\`\`

---

*Exported from DCF Skill Studio*
`;
};
