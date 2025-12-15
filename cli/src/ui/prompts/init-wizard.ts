/**
 * Interactive Init Wizard
 *
 * Uses @clack/prompts for a beautiful interactive project creation experience.
 */

import * as p from '@clack/prompts'
import pc from 'picocolors'

export interface InitWizardResult {
  name: string
  template: string
  description: string
  features: string[]
  git: boolean
  install: boolean
}

const TEMPLATES = [
  {
    value: 'blank',
    label: 'Blank',
    hint: 'Empty project with SPEC.md - recommended for new ideas',
  },
  {
    value: 'simple_task',
    label: 'Task Manager',
    hint: 'Basic task management app - great for learning',
  },
  {
    value: 'contact_manager',
    label: 'Contact Manager',
    hint: 'Contact management with categories and tags',
  },
  {
    value: 'saas',
    label: 'SaaS Starter',
    hint: 'Multi-tenant template with auth and billing',
  },
]

const FEATURES = [
  {
    value: 'auth',
    label: 'Authentication',
    hint: 'User login/signup with sessions',
  },
  {
    value: 'api',
    label: 'External APIs',
    hint: 'Integration with external services',
  },
  {
    value: 'queue',
    label: 'Background Jobs',
    hint: 'Async processing with queues',
  },
  {
    value: 'email',
    label: 'Email',
    hint: 'Transactional email support',
  },
]

export async function runInitWizard(defaultName?: string): Promise<InitWizardResult | null> {
  console.clear()

  p.intro(pc.bgCyan(pc.black(' DAZZLE ')))

  const project = await p.group(
    {
      name: () =>
        p.text({
          message: 'What is your project name?',
          placeholder: defaultName || 'my-awesome-app',
          defaultValue: defaultName,
          validate: (value) => {
            if (!value) return 'Project name is required'
            if (!/^[a-z0-9-_]+$/i.test(value)) {
              return 'Use only letters, numbers, hyphens, and underscores'
            }
            return undefined
          },
        }),

      description: () =>
        p.text({
          message: 'Describe your project in one line',
          placeholder: 'A platform for managing...',
        }),

      template: () =>
        p.select({
          message: 'Choose a starting template',
          options: TEMPLATES,
          initialValue: 'blank',
        }),

      features: ({ results }) => {
        // Skip features for non-blank templates
        if (results.template !== 'blank') {
          return Promise.resolve([])
        }
        return p.multiselect({
          message: 'Select features to include',
          options: FEATURES,
          required: false,
        })
      },

      git: () =>
        p.confirm({
          message: 'Initialize a git repository?',
          initialValue: true,
        }),

      install: () =>
        p.confirm({
          message: 'Install dependencies now?',
          initialValue: true,
        }),
    },
    {
      onCancel: () => {
        p.cancel('Project creation cancelled.')
        return null
      },
    }
  )

  if (!project.name) {
    return null
  }

  return {
    name: project.name as string,
    template: project.template as string,
    description: (project.description as string) || '',
    features: (project.features as string[]) || [],
    git: project.git as boolean,
    install: project.install as boolean,
  }
}

export async function showProgress(
  steps: { label: string; task: () => Promise<void> }[]
): Promise<void> {
  const s = p.spinner()

  for (const step of steps) {
    s.start(step.label)
    try {
      await step.task()
      s.stop(`${step.label} ✓`)
    } catch (err) {
      s.stop(`${step.label} ✗`)
      throw err
    }
  }
}

export function showSuccess(projectName: string, projectPath: string): void {
  p.note(
    `cd ${projectPath}\ndazzle dev`,
    'Next steps'
  )

  p.outro(pc.green(`Project "${projectName}" created successfully! 🎉`))
}

export function showError(message: string): void {
  p.log.error(pc.red(message))
}
