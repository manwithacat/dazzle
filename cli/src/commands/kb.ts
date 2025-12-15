/**
 * kb command - Interactive knowledgebase browser
 *
 * Browse DSL concepts, patterns, and API packs.
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error } from '../lib/output'

const KbArgs = z.object({
  focus: z
    .enum(['concepts', 'patterns', 'api_packs'])
    .optional()
    .describe('Start focused on a specific section'),
  query: z
    .string()
    .optional()
    .describe('Search query to filter results'),
})

interface Concept {
  name: string
  description: string
  syntax?: string
  example?: string
}

interface Pattern {
  name: string
  description: string
  use_case: string
}

interface ApiPack {
  name: string
  provider: string
  category: string
  description: string
}

// DSL concepts with descriptions
const DSL_CONCEPTS: Concept[] = [
  {
    name: 'entity',
    description: 'Defines a data model with fields, constraints, and relationships.',
    syntax: 'entity Name "Label":\n  field: type modifiers',
    example: 'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n  completed: bool=false',
  },
  {
    name: 'surface',
    description: 'Defines a UI view for an entity (list, detail, create, edit).',
    syntax: 'surface name "Label":\n  uses entity Entity\n  mode: list|view|create|edit',
    example: 'surface task_list "Tasks":\n  uses entity Task\n  mode: list',
  },
  {
    name: 'workspace',
    description: 'Groups surfaces into a navigation structure for personas.',
    syntax: 'workspace name "Label":\n  persona PersonaName\n  nav: surface1, surface2',
    example: 'workspace admin_portal "Admin":\n  persona Admin\n  nav: user_list, task_list',
  },
  {
    name: 'persona',
    description: 'Defines a user role with goals and permissions.',
    syntax: 'persona Name "Label":\n  goal: "what they want to achieve"',
    example: 'persona Manager "Team Manager":\n  goal: "Oversee team tasks"',
  },
  {
    name: 'service',
    description: 'Defines business logic or API integration.',
    syntax: 'service name:\n  action action_name(params) -> ReturnType',
    example: 'service notifications:\n  action send_email(to, subject, body) -> bool',
  },
  {
    name: 'foreign_model',
    description: 'References external data models from API integrations.',
    syntax: 'foreign_model Name from "provider":\n  field: type',
    example: 'foreign_model StripeCustomer from "stripe":\n  id: str\n  email: email',
  },
  {
    name: 'integration',
    description: 'Connects entities with external services via sync or actions.',
    syntax: 'integration name:\n  connect Entity <-> Service',
    example: 'integration stripe_sync:\n  connect Customer <-> stripe.customers',
  },
  {
    name: 'state_machine',
    description: 'Defines allowed transitions between entity states.',
    syntax: 'state_machine for Entity.status:\n  state1 -> state2, state3',
    example: 'state_machine for Task.status:\n  pending -> in_progress\n  in_progress -> completed, pending',
  },
  {
    name: 'attention',
    description: 'Highlights important fields for personas using signals like badge or alert.',
    syntax: 'attention:\n  persona Persona:\n    signal badge on field when condition',
    example: 'attention:\n  persona Manager:\n    signal badge on overdue when due_date < now()',
  },
  {
    name: 'computed',
    description: 'Defines calculated fields based on other field values.',
    syntax: 'field_name: type computed "expression"',
    example: 'total: decimal computed "quantity * unit_price"',
  },
]

// Common patterns
const PATTERNS: Pattern[] = [
  {
    name: 'crud',
    description: 'Complete Create-Read-Update-Delete flow for an entity with list, detail, create, and edit surfaces.',
    use_case: 'Use when you need full lifecycle management for an entity.',
  },
  {
    name: 'dashboard',
    description: 'Overview page with metrics, charts, and quick actions for monitoring.',
    use_case: 'Use for admin portals or status overview screens.',
  },
  {
    name: 'kanban_board',
    description: 'Drag-and-drop board organized by status columns.',
    use_case: 'Use for task management, project tracking, or pipeline views.',
  },
  {
    name: 'role_based_access',
    description: 'Different views and permissions based on user persona.',
    use_case: 'Use when different users need different capabilities.',
  },
  {
    name: 'wizard_flow',
    description: 'Multi-step form with validation at each stage.',
    use_case: 'Use for complex data entry or onboarding processes.',
  },
  {
    name: 'master_detail',
    description: 'List on one side, selected item detail on the other.',
    use_case: 'Use for email clients, file browsers, or settings pages.',
  },
  {
    name: 'search_filter',
    description: 'Searchable and filterable list with facets.',
    use_case: 'Use for catalogs, directories, or large data sets.',
  },
  {
    name: 'audit_log',
    description: 'Track changes to entities with timestamps and user info.',
    use_case: 'Use for compliance, debugging, or activity feeds.',
  },
]

// Available API packs
const API_PACKS: ApiPack[] = [
  {
    name: 'stripe_payments',
    provider: 'Stripe',
    category: 'payments',
    description: 'Payment processing, subscriptions, and invoicing.',
  },
  {
    name: 'stripe_connect',
    provider: 'Stripe',
    category: 'payments',
    description: 'Marketplace payments and platform payouts.',
  },
  {
    name: 'hmrc_mtd_vat',
    provider: 'HMRC',
    category: 'tax',
    description: 'UK VAT returns and Making Tax Digital compliance.',
  },
  {
    name: 'xero_accounting',
    provider: 'Xero',
    category: 'accounting',
    description: 'Invoices, contacts, and financial reports.',
  },
  {
    name: 'companies_house',
    provider: 'Companies House',
    category: 'business_data',
    description: 'UK company information and filings.',
  },
  {
    name: 'sendgrid_email',
    provider: 'SendGrid',
    category: 'email',
    description: 'Transactional email delivery and templates.',
  },
  {
    name: 'twilio_sms',
    provider: 'Twilio',
    category: 'messaging',
    description: 'SMS and voice communications.',
  },
  {
    name: 'aws_s3',
    provider: 'AWS',
    category: 'storage',
    description: 'Object storage for files and media.',
  },
  {
    name: 'google_maps',
    provider: 'Google',
    category: 'location',
    description: 'Geocoding, directions, and place search.',
  },
  {
    name: 'openai',
    provider: 'OpenAI',
    category: 'ai',
    description: 'GPT models for text generation and embeddings.',
  },
]

export const kb: CommandDefinition<typeof KbArgs> = {
  name: 'kb',
  description: 'Browse the DAZZLE knowledgebase',
  help: `
Opens an interactive browser for DSL concepts, patterns, and API packs.

Use this to learn about DAZZLE features and find examples.

Sections:
  concepts   - DSL constructs (entity, surface, workspace, etc.)
  patterns   - Common UI/UX patterns (CRUD, dashboard, kanban, etc.)
  api_packs  - External service integrations (Stripe, HMRC, etc.)
`,
  examples: [
    'dazzle kb',
    'dazzle kb --focus patterns',
    'dazzle kb --query stripe',
  ],
  args: KbArgs,

  async run(args, _ctx) {
    // Filter by query if provided
    let concepts = DSL_CONCEPTS
    let patterns = PATTERNS
    let apiPacks = API_PACKS

    if (args.query) {
      const q = args.query.toLowerCase()
      concepts = concepts.filter(
        (c) => c.name.includes(q) || c.description.toLowerCase().includes(q)
      )
      patterns = patterns.filter(
        (p) => p.name.includes(q) || p.description.toLowerCase().includes(q)
      )
      apiPacks = apiPacks.filter(
        (a) =>
          a.name.includes(q) ||
          a.provider.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q)
      )
    }

    // Check if TTY is available for interactive mode
    if (!process.stdin.isTTY) {
      // Non-interactive: output as JSON
      return success({
        concepts: concepts.map((c) => ({ name: c.name, description: c.description })),
        patterns: patterns.map((p) => ({ name: p.name, description: p.description })),
        api_packs: apiPacks.map((a) => ({
          name: a.name,
          provider: a.provider,
          category: a.category,
        })),
        hint: 'Run in an interactive terminal for the full browser UI',
      })
    }

    // Dynamic import to avoid loading React/Ink for non-interactive commands
    const { render } = await import('ink')
    const React = await import('react')
    const { KnowledgeBrowser } = await import('../ui/components/KnowledgeBrowser')

    // Render the browser
    const { waitUntilExit } = render(
      React.createElement(KnowledgeBrowser, {
        concepts,
        patterns,
        apiPacks,
        initialTab: args.focus,
      })
    )

    await waitUntilExit()

    return success({ browsed: true }, { silent: true })
  },
}
