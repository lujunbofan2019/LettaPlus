import yaml from 'js-yaml';
import { fileService } from './FileService.js';
import type { SkillDefinition, ToolsIndex, ToolsRegistry } from '../../shared/types.js';

// YAML schema types that map to our TypeScript types
interface SkillYaml {
  apiVersion: string;
  kind: string;
  metadata: {
    manifestId: string;
    name: string;
    version: string;
    description: string;
    tags: string[];
  };
  permissions: {
    egress: boolean;
    secrets: boolean;
    riskLevel: 'low' | 'medium' | 'high';
  };
  directives: string;
  tools: Array<{
    name: string;
    server: string;
    required?: boolean;
  }>;
  dataSources?: Array<{
    type: 'file' | 'url' | 'memory_block';
    path?: string;
    url?: string;
    blockLabel?: string;
  }>;
  tests?: Array<{
    name: string;
    input: Record<string, unknown>;
    expectedOutput?: Record<string, unknown>;
  }>;
}

export class YamlService {
  /**
   * Parse YAML string to object
   */
  parse<T = unknown>(yamlStr: string): T {
    return yaml.load(yamlStr) as T;
  }

  /**
   * Serialize object to YAML string
   */
  stringify(obj: unknown): string {
    return yaml.dump(obj, {
      indent: 2,
      lineWidth: 120,
      noRefs: true,
      sortKeys: false,
      quotingType: '"',
      forceQuotes: false,
    });
  }

  /**
   * Read and parse a YAML file
   */
  async readYamlFile<T = unknown>(filePath: string): Promise<T> {
    const content = await fileService.readFile(filePath);
    return this.parse<T>(content);
  }

  /**
   * Write object to YAML file
   */
  async writeYamlFile(filePath: string, obj: unknown): Promise<void> {
    const yamlStr = this.stringify(obj);
    await fileService.writeFile(filePath, yamlStr);
  }

  /**
   * Parse skill YAML to SkillDefinition
   */
  parseSkill(yamlStr: string): SkillDefinition {
    const parsed = this.parse<SkillYaml>(yamlStr);
    return this.yamlToSkillDefinition(parsed);
  }

  /**
   * Convert SkillDefinition to YAML-compatible object
   */
  skillToYaml(skill: SkillDefinition): SkillYaml {
    return {
      apiVersion: skill.apiVersion,
      kind: skill.kind,
      metadata: {
        manifestId: skill.metadata.manifestId,
        name: skill.metadata.name,
        version: skill.metadata.version,
        description: skill.metadata.description,
        tags: skill.metadata.tags,
      },
      permissions: {
        egress: skill.permissions.egress,
        secrets: skill.permissions.secrets,
        riskLevel: skill.permissions.riskLevel,
      },
      directives: skill.directives,
      tools: skill.tools.map((t) => ({
        name: t.name,
        server: t.server,
        ...(t.required !== true ? { required: t.required } : {}),
      })),
      ...(skill.dataSources.length > 0 ? { dataSources: skill.dataSources } : {}),
      ...(skill.tests && skill.tests.length > 0 ? { tests: skill.tests } : {}),
    };
  }

  /**
   * Read skill definition from file
   */
  async readSkillFile(filePath: string): Promise<SkillDefinition> {
    const content = await fileService.readFile(filePath);
    return this.parseSkill(content);
  }

  /**
   * Write skill definition to file
   */
  async writeSkillFile(filePath: string, skill: SkillDefinition): Promise<void> {
    const yamlObj = this.skillToYaml(skill);
    await this.writeYamlFile(filePath, yamlObj);
  }

  /**
   * Read tools index file
   */
  async readToolsIndex(filePath: string): Promise<ToolsIndex> {
    return this.readYamlFile<ToolsIndex>(filePath);
  }

  /**
   * Read tools registry file
   */
  async readToolsRegistry(filePath: string): Promise<ToolsRegistry> {
    return this.readYamlFile<ToolsRegistry>(filePath);
  }

  /**
   * Convert parsed YAML to SkillDefinition
   */
  private yamlToSkillDefinition(parsed: SkillYaml): SkillDefinition {
    return {
      apiVersion: parsed.apiVersion || 'skill/v1',
      kind: parsed.kind || 'Skill',
      metadata: {
        manifestId: parsed.metadata?.manifestId || '',
        name: parsed.metadata?.name || '',
        version: parsed.metadata?.version || '0.1.0',
        description: parsed.metadata?.description || '',
        tags: parsed.metadata?.tags || [],
      },
      permissions: {
        egress: parsed.permissions?.egress ?? false,
        secrets: parsed.permissions?.secrets ?? false,
        riskLevel: parsed.permissions?.riskLevel || 'low',
      },
      directives: parsed.directives || '',
      tools: (parsed.tools || []).map((t) => ({
        name: t.name,
        server: t.server,
        required: t.required ?? true,
      })),
      dataSources: parsed.dataSources || [],
      tests: parsed.tests || [],
    };
  }
}

// Singleton instance
export const yamlService = new YamlService();
