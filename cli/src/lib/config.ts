/**
 * Configuration loading for DAZZLE CLI
 *
 * Handles dazzle.toml parsing and project detection.
 */

import type { DazzleConfig } from '../types/commands'

/**
 * Find dazzle.toml in current or parent directories
 */
export async function findConfigPath(startDir: string = process.cwd()): Promise<string | null> {
  let dir = startDir

  while (true) {
    const configPath = `${dir}/dazzle.toml`
    const file = Bun.file(configPath)

    if (await file.exists()) {
      return configPath
    }

    const parent = dir.substring(0, dir.lastIndexOf('/'))
    if (parent === dir || parent === '') {
      return null
    }
    dir = parent
  }
}

/**
 * Parse TOML file (simple implementation for dazzle.toml)
 *
 * Note: This is a simplified TOML parser that handles the dazzle.toml format.
 * For complex TOML, consider using a full parser.
 */
function parseToml(content: string): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  let currentSection = result

  const lines = content.split('\n')

  for (const line of lines) {
    const trimmed = line.trim()

    // Skip comments and empty lines
    if (trimmed.startsWith('#') || trimmed === '') continue

    // Section header
    if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
      const section = trimmed.slice(1, -1)
      const parts = section.split('.')

      currentSection = result
      for (const part of parts) {
        if (!(part in currentSection)) {
          ;(currentSection as Record<string, unknown>)[part] = {}
        }
        currentSection = (currentSection as Record<string, Record<string, unknown>>)[part]
      }
      continue
    }

    // Key-value pair
    const eqIndex = trimmed.indexOf('=')
    if (eqIndex === -1) continue

    const key = trimmed.slice(0, eqIndex).trim()
    let value = trimmed.slice(eqIndex + 1).trim()

    // Parse value
    if (value.startsWith('"') && value.endsWith('"')) {
      // String
      value = value.slice(1, -1)
      ;(currentSection as Record<string, unknown>)[key] = value
    } else if (value.startsWith('[') && value.endsWith(']')) {
      // Array (simple, single-line)
      const items = value
        .slice(1, -1)
        .split(',')
        .map((s) => s.trim())
        .filter((s) => s)
        .map((s) => (s.startsWith('"') && s.endsWith('"') ? s.slice(1, -1) : s))
      ;(currentSection as Record<string, unknown>)[key] = items
    } else if (value === 'true') {
      ;(currentSection as Record<string, unknown>)[key] = true
    } else if (value === 'false') {
      ;(currentSection as Record<string, unknown>)[key] = false
    } else if (!isNaN(Number(value))) {
      ;(currentSection as Record<string, unknown>)[key] = Number(value)
    } else {
      ;(currentSection as Record<string, unknown>)[key] = value
    }
  }

  return result
}

/**
 * Load dazzle.toml configuration
 */
export async function loadConfig(configPath: string): Promise<DazzleConfig | null> {
  try {
    const file = Bun.file(configPath)
    const content = await file.text()
    const parsed = parseToml(content)

    // Extract project info from [project] section or root
    const project = (parsed.project as Record<string, unknown>) || parsed

    return {
      name: String(project.name || 'unnamed'),
      version: String(project.version || '0.0.0'),
      modules: (project.modules as string[]) || [],
      ...parsed,
    }
  } catch (err) {
    return null
  }
}

/**
 * Get project root directory from config path
 */
export function getProjectRoot(configPath: string): string {
  return configPath.substring(0, configPath.lastIndexOf('/'))
}

/**
 * Check if we're in a DAZZLE project
 */
export async function isInProject(): Promise<boolean> {
  const configPath = await findConfigPath()
  return configPath !== null
}
