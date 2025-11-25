"""
Configuration file generator for Next.js Onebox.

Generates:
- package.json
- tsconfig.json
- next.config.ts
- tailwind.config.ts
- postcss.config.js
- .env.example
- .gitignore
- README.md
"""

import json
from pathlib import Path

from ....core import ir
from ...base.generator import Generator, GeneratorResult


class ConfigGenerator(Generator):
    """Generates configuration files for Next.js project."""

    def generate(self) -> GeneratorResult:
        """Generate all configuration files."""
        result = GeneratorResult()

        # Generate each config file
        self._generate_package_json(result)
        self._generate_tsconfig(result)
        self._generate_next_config(result)
        self._generate_tailwind_config(result)
        self._generate_postcss_config(result)
        self._generate_env_example(result)
        self._generate_gitignore(result)
        self._generate_readme(result)

        return result

    def _generate_package_json(self, result: GeneratorResult) -> None:
        """Generate package.json."""
        package = {
            "name": self.spec.name.lower().replace(" ", "-"),
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "start": "next start",
                "lint": "next lint",
                "db:generate": "prisma generate",
                "db:push": "prisma db push",
                "db:migrate": "prisma migrate dev",
                "db:studio": "prisma studio",
            },
            "dependencies": {
                "next": "^14.2.0",
                "react": "^18.3.0",
                "react-dom": "^18.3.0",
                "@prisma/client": "^5.19.0",
                "@mantine/core": "^7.12.0",
                "@mantine/hooks": "^7.12.0",
                "mantine-datatable": "^7.12.0",
                "@radix-ui/react-slot": "^1.1.0",
                "lucide-react": "^0.447.0",
                "bcryptjs": "^2.4.3",
                "jose": "^5.9.0",
                "clsx": "^2.1.1",
                "tailwind-merge": "^2.5.0",
            },
            "devDependencies": {
                "typescript": "^5.6.0",
                "@types/node": "^22.0.0",
                "@types/react": "^18.3.0",
                "@types/react-dom": "^18.3.0",
                "@types/bcryptjs": "^2.4.6",
                "prisma": "^5.19.0",
                "tailwindcss": "^3.4.0",
                "postcss": "^8.4.0",
                "autoprefixer": "^10.4.0",
                "eslint": "^8.57.0",
                "eslint-config-next": "^14.2.0",
            },
        }

        path = self.output_dir / "package.json"
        self._write_file(path, json.dumps(package, indent=2))
        result.add_file(path)

    def _generate_tsconfig(self, result: GeneratorResult) -> None:
        """Generate tsconfig.json."""
        tsconfig = {
            "compilerOptions": {
                "lib": ["dom", "dom.iterable", "esnext"],
                "allowJs": True,
                "skipLibCheck": True,
                "strict": True,
                "noEmit": True,
                "esModuleInterop": True,
                "module": "esnext",
                "moduleResolution": "bundler",
                "resolveJsonModule": True,
                "isolatedModules": True,
                "jsx": "preserve",
                "incremental": True,
                "plugins": [{"name": "next"}],
                "paths": {
                    "@/*": ["./src/*"],
                },
            },
            "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
            "exclude": ["node_modules"],
        }

        path = self.output_dir / "tsconfig.json"
        self._write_file(path, json.dumps(tsconfig, indent=2))
        result.add_file(path)

    def _generate_next_config(self, result: GeneratorResult) -> None:
        """Generate next.config.mjs (Next.js 14 requires .mjs, not .ts)."""
        content = '''/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable React strict mode
  reactStrictMode: true,

  // Standalone output for Docker
  output: "standalone",

  // Suppress source map warnings from node_modules (e.g., Mantine)
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.ignoreWarnings = [
        { module: /node_modules/ },
      ];
    }
    return config;
  },
};

export default nextConfig;
'''
        path = self.output_dir / "next.config.mjs"
        self._write_file(path, content)
        result.add_file(path)

    def _generate_tailwind_config(self, result: GeneratorResult) -> None:
        """Generate tailwind.config.ts."""
        content = '''import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // CSS variable-based colors (matches globals.css)
        background: "rgb(var(--background) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)",
        card: {
          DEFAULT: "rgb(var(--card) / <alpha-value>)",
          foreground: "rgb(var(--card-foreground) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          foreground: "rgb(var(--primary-foreground) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "rgb(var(--secondary) / <alpha-value>)",
          foreground: "rgb(var(--secondary-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "rgb(var(--muted) / <alpha-value>)",
          foreground: "rgb(var(--muted-foreground) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          foreground: "rgb(var(--accent-foreground) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "rgb(var(--destructive) / <alpha-value>)",
          foreground: "rgb(var(--destructive-foreground) / <alpha-value>)",
        },
        border: "rgb(var(--border) / <alpha-value>)",
        input: "rgb(var(--input) / <alpha-value>)",
        ring: "rgb(var(--ring) / <alpha-value>)",
        // Custom colors for attention signals
        attention: {
          critical: {
            bg: "#fef2f2",
            border: "#ef4444",
            text: "#991b1b",
          },
          warning: {
            bg: "#fffbeb",
            border: "#f59e0b",
            text: "#92400e",
          },
          notice: {
            bg: "#eff6ff",
            border: "#3b82f6",
            text: "#1e40af",
          },
          info: {
            bg: "#f8fafc",
            border: "#cbd5e1",
            text: "#475569",
          },
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};

export default config;
'''
        path = self.output_dir / "tailwind.config.ts"
        self._write_file(path, content)
        result.add_file(path)

    def _generate_postcss_config(self, result: GeneratorResult) -> None:
        """Generate postcss.config.js."""
        content = '''module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
'''
        path = self.output_dir / "postcss.config.js"
        self._write_file(path, content)
        result.add_file(path)

    def _generate_env_example(self, result: GeneratorResult) -> None:
        """Generate .env.example."""
        content = '''# Database
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/app?schema=public"

# Auth
JWT_SECRET="your-super-secret-jwt-key-change-in-production"
SESSION_SECRET="your-session-secret-change-in-production"

# App
NEXT_PUBLIC_APP_URL="http://localhost:3000"
'''
        path = self.output_dir / ".env.example"
        self._write_file(path, content)
        result.add_file(path)

        # Also create .env for local development
        env_path = self.output_dir / ".env"
        self._write_file(env_path, content)
        result.add_file(env_path)

    def _generate_gitignore(self, result: GeneratorResult) -> None:
        """Generate .gitignore."""
        content = '''# Dependencies
node_modules/
.pnpm-store/

# Next.js
.next/
out/

# Production
build/
dist/

# Environment
.env
.env.local
.env.*.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# Debug
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Testing
coverage/

# Misc
.DS_Store
*.pem
Thumbs.db

# Prisma
prisma/migrations/

# Docker
.docker/
'''
        path = self.output_dir / ".gitignore"
        self._write_file(path, content)
        result.add_file(path)

    def _generate_readme(self, result: GeneratorResult) -> None:
        """Generate README.md."""
        app_title = self.spec.title or self.spec.name
        entities = [e.name for e in self.spec.domain.entities]
        surfaces = [s.name for s in self.spec.surfaces]
        workspaces = [w.name for w in self.spec.workspaces]

        content = f'''# {app_title}

Generated with DAZZLE - Next.js Onebox Stack

## Quick Start

```bash
# Install dependencies
npm install

# Generate Prisma client
npm run db:generate

# Run database migrations
npm run db:push

# Start development server
npm run dev
```

Visit http://localhost:3000

## Docker

```bash
# Build and run with Docker
docker build -t {self.spec.name} .
docker run -p 3000:3000 -p 5432:5432 {self.spec.name}
```

## Features

### Entities
{chr(10).join(f"- {e}" for e in entities)}

### Surfaces
{chr(10).join(f"- {s}" for s in surfaces)}

### Workspaces
{chr(10).join(f"- {w}" for w in workspaces) if workspaces else "- None defined"}

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Database**: PostgreSQL with Prisma ORM
- **Styling**: Tailwind CSS
- **Data Tables**: Mantine DataTable
- **Icons**: Lucide React
- **Auth**: Built-in session-based auth

## Project Structure

```
src/
├── app/              # Next.js App Router pages
├── components/       # React components
├── actions/          # Server Actions
├── lib/              # Utilities (db, auth, etc.)
├── providers/        # React context providers
└── types/            # TypeScript types
```

---

Generated with [DAZZLE](https://github.com/manwithacat/dazzle)
'''
        path = self.output_dir / "README.md"
        self._write_file(path, content)
        result.add_file(path)
