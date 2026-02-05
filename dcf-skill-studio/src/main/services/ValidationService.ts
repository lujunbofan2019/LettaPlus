import Ajv from 'ajv';
import type { SkillDefinition, ValidationError, ToolDefinition } from '../../shared/types.js';

// Simplified JSON Schema for skill validation
// In production, this would be loaded from skills_src/schemas/skill.authoring.schema.yaml
const skillSchema = {
  $schema: 'http://json-schema.org/draft-07/schema#',
  type: 'object',
  required: ['apiVersion', 'kind', 'metadata', 'permissions', 'directives', 'tools'],
  properties: {
    apiVersion: {
      type: 'string',
      pattern: '^skill/v\\d+$',
    },
    kind: {
      type: 'string',
      const: 'Skill',
    },
    metadata: {
      type: 'object',
      required: ['manifestId', 'name', 'version', 'description'],
      properties: {
        manifestId: {
          type: 'string',
          pattern: '^skill\\.[a-z][a-z0-9-]*\\.[a-z][a-z0-9-]*@\\d+\\.\\d+\\.\\d+$',
        },
        name: {
          type: 'string',
          minLength: 1,
          pattern: '^[a-z][a-z0-9-]*\\.[a-z][a-z0-9-]*$',
        },
        version: {
          type: 'string',
          pattern: '^\\d+\\.\\d+\\.\\d+$',
        },
        description: {
          type: 'string',
          minLength: 1,
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
        },
      },
    },
    permissions: {
      type: 'object',
      required: ['egress', 'secrets', 'riskLevel'],
      properties: {
        egress: { type: 'boolean' },
        secrets: { type: 'boolean' },
        riskLevel: {
          type: 'string',
          enum: ['low', 'medium', 'high'],
        },
      },
    },
    directives: {
      type: 'string',
      minLength: 1,
    },
    tools: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'server'],
        properties: {
          name: { type: 'string', minLength: 1 },
          server: { type: 'string', minLength: 1 },
          required: { type: 'boolean' },
        },
      },
    },
    dataSources: {
      type: 'array',
      items: {
        type: 'object',
        required: ['type'],
        properties: {
          type: {
            type: 'string',
            enum: ['file', 'url', 'memory_block'],
          },
          path: { type: 'string' },
          url: { type: 'string' },
          blockLabel: { type: 'string' },
        },
      },
    },
    tests: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'input'],
        properties: {
          name: { type: 'string' },
          input: { type: 'object' },
          expectedOutput: { type: 'object' },
        },
      },
    },
  },
};

export class ValidationService {
  private ajv: Ajv;
  private validateSchema: ReturnType<Ajv['compile']>;
  private toolsCatalog: Map<string, ToolDefinition> = new Map();

  constructor() {
    this.ajv = new Ajv({ allErrors: true, verbose: true });
    this.validateSchema = this.ajv.compile(skillSchema);
  }

  /**
   * Set the tools catalog for cross-reference validation
   */
  setToolsCatalog(tools: ToolDefinition[]): void {
    this.toolsCatalog.clear();
    for (const tool of tools) {
      const key = `${tool.server}:${tool.name}`;
      this.toolsCatalog.set(key, tool);
    }
  }

  /**
   * Validate a skill definition
   */
  validate(skill: SkillDefinition): ValidationError[] {
    const errors: ValidationError[] = [];

    // Schema validation
    const schemaValid = this.validateSchema(skill);
    if (!schemaValid && this.validateSchema.errors) {
      for (const err of this.validateSchema.errors) {
        errors.push({
          path: err.instancePath || '/',
          message: err.message || 'Schema validation error',
          severity: 'error',
        });
      }
    }

    // Static checks
    errors.push(...this.runStaticChecks(skill));

    // Cross-reference checks (only if tools catalog is set)
    if (this.toolsCatalog.size > 0) {
      errors.push(...this.runCrossReferenceChecks(skill));
    }

    return errors;
  }

  /**
   * Run static validation checks
   */
  private runStaticChecks(skill: SkillDefinition): ValidationError[] {
    const errors: ValidationError[] = [];

    // Check manifestId format matches name and version
    const expectedManifestId = `skill.${skill.metadata.name}@${skill.metadata.version}`;
    if (skill.metadata.manifestId !== expectedManifestId) {
      errors.push({
        path: '/metadata/manifestId',
        message: `manifestId should be "${expectedManifestId}" based on name and version`,
        severity: 'warning',
      });
    }

    // Check for duplicate tools
    const toolKeys = new Set<string>();
    for (let i = 0; i < skill.tools.length; i++) {
      const tool = skill.tools[i];
      const key = `${tool.server}:${tool.name}`;
      if (toolKeys.has(key)) {
        errors.push({
          path: `/tools/${i}`,
          message: `Duplicate tool reference: ${key}`,
          severity: 'error',
        });
      }
      toolKeys.add(key);
    }

    // Check data sources have required fields
    for (let i = 0; i < skill.dataSources.length; i++) {
      const ds = skill.dataSources[i];
      if (ds.type === 'file' && !ds.path) {
        errors.push({
          path: `/dataSources/${i}`,
          message: 'File data source requires "path" field',
          severity: 'error',
        });
      }
      if (ds.type === 'url' && !ds.url) {
        errors.push({
          path: `/dataSources/${i}`,
          message: 'URL data source requires "url" field',
          severity: 'error',
        });
      }
      if (ds.type === 'memory_block' && !ds.blockLabel) {
        errors.push({
          path: `/dataSources/${i}`,
          message: 'Memory block data source requires "blockLabel" field',
          severity: 'error',
        });
      }
    }

    // Check directives are not empty
    if (skill.directives.trim().length < 10) {
      errors.push({
        path: '/directives',
        message: 'Directives should provide meaningful instructions (at least 10 characters)',
        severity: 'warning',
      });
    }

    // Warn if no tags
    if (skill.metadata.tags.length === 0) {
      errors.push({
        path: '/metadata/tags',
        message: 'Consider adding tags for better skill discoverability',
        severity: 'warning',
      });
    }

    return errors;
  }

  /**
   * Run cross-reference validation against tools catalog
   */
  private runCrossReferenceChecks(skill: SkillDefinition): ValidationError[] {
    const errors: ValidationError[] = [];

    for (let i = 0; i < skill.tools.length; i++) {
      const tool = skill.tools[i];
      const key = `${tool.server}:${tool.name}`;
      if (!this.toolsCatalog.has(key)) {
        errors.push({
          path: `/tools/${i}`,
          message: `Tool "${tool.name}" from server "${tool.server}" not found in catalog`,
          severity: 'error',
        });
      }
    }

    return errors;
  }

  /**
   * Check if there are any errors (not just warnings)
   */
  hasErrors(errors: ValidationError[]): boolean {
    return errors.some((e) => e.severity === 'error');
  }

  /**
   * Get only errors (exclude warnings)
   */
  getErrors(errors: ValidationError[]): ValidationError[] {
    return errors.filter((e) => e.severity === 'error');
  }

  /**
   * Get only warnings
   */
  getWarnings(errors: ValidationError[]): ValidationError[] {
    return errors.filter((e) => e.severity === 'warning');
  }
}

// Singleton instance
export const validationService = new ValidationService();
