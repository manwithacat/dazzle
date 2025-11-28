"""
Configuration file generators for Next.js stack.

Generates:
- package.json with dependencies
- next.config.js
- tsconfig.json
- tailwind.config.ts
"""

import json
from pathlib import Path

from ....core import ir


class PackageJsonGenerator:
    """Generate package.json with Next.js dependencies."""

    def __init__(self, spec: ir.AppSpec, project_path: Path, project_name: str):
        self.spec = spec
        self.project_path = project_path
        self.project_name = project_name

    def generate(self) -> None:
        """Generate package.json."""
        package_json = {
            "name": self.project_name,
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "start": "next start",
                "lint": "next lint",
                "type-check": "tsc --noEmit",
            },
            "dependencies": {
                "next": "^14.2.0",
                "react": "^18.3.0",
                "react-dom": "^18.3.0",
                "clsx": "^2.1.0",
                "tailwind-merge": "^2.2.0",
            },
            "devDependencies": {
                "@types/node": "^20.11.0",
                "@types/react": "^18.3.0",
                "@types/react-dom": "^18.3.0",
                "typescript": "^5.3.0",
                "tailwindcss": "^3.4.0",
                "postcss": "^8.4.0",
                "autoprefixer": "^10.4.0",
                "eslint": "^8.56.0",
                "eslint-config-next": "^14.2.0",
            },
        }

        output_path = self.project_path / "package.json"
        with open(output_path, "w") as f:
            json.dump(package_json, f, indent=2)


class ConfigGenerator:
    """Generate Next.js and TypeScript configuration files."""

    def __init__(self, spec: ir.AppSpec, project_path: Path):
        self.spec = spec
        self.project_path = project_path

    def generate(self) -> None:
        """Generate all config files."""
        self._generate_next_config()
        self._generate_tsconfig()
        self._generate_postcss_config()
        self._generate_eslint_config()
        self._generate_gitignore()

    def _generate_next_config(self) -> None:
        """Generate next.config.js."""
        content = '''/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    typedRoutes: true,
  },
}

module.exports = nextConfig
'''
        output_path = self.project_path / "next.config.js"
        output_path.write_text(content)

    def _generate_tsconfig(self) -> None:
        """Generate tsconfig.json."""
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020",
                "lib": ["dom", "dom.iterable", "esnext"],
                "allowJs": True,
                "skipLibCheck": True,
                "strict": True,
                "forceConsistentCasingInFileNames": True,
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

        output_path = self.project_path / "tsconfig.json"
        with open(output_path, "w") as f:
            json.dump(tsconfig, f, indent=2)

    def _generate_postcss_config(self) -> None:
        """Generate postcss.config.js."""
        content = '''module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
'''
        output_path = self.project_path / "postcss.config.js"
        output_path.write_text(content)

    def _generate_eslint_config(self) -> None:
        """Generate .eslintrc.json."""
        eslint_config = {"extends": "next/core-web-vitals"}

        output_path = self.project_path / ".eslintrc.json"
        with open(output_path, "w") as f:
            json.dump(eslint_config, f, indent=2)

    def _generate_gitignore(self) -> None:
        """Generate .gitignore."""
        content = '''# dependencies
/node_modules
/.pnp
.pnp.js

# testing
/coverage

# next.js
/.next/
/out/

# production
/build

# misc
.DS_Store
*.pem

# debug
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# local env files
.env*.local

# vercel
.vercel

# typescript
*.tsbuildinfo
next-env.d.ts
'''
        output_path = self.project_path / ".gitignore"
        output_path.write_text(content)


class TailwindConfigGenerator:
    """Generate Tailwind CSS configuration."""

    def __init__(self, spec: ir.AppSpec, project_path: Path):
        self.spec = spec
        self.project_path = project_path

    def generate(self) -> None:
        """Generate tailwind.config.ts and globals.css."""
        self._generate_tailwind_config()
        self._generate_globals_css()

    def _generate_tailwind_config(self) -> None:
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
        background: "var(--background)",
        foreground: "var(--foreground)",
      },
    },
  },
  plugins: [],
};

export default config;
'''
        output_path = self.project_path / "tailwind.config.ts"
        output_path.write_text(content)

    def _generate_globals_css(self) -> None:
        """Generate globals.css with Tailwind imports."""
        content = '''@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #ffffff;
  --foreground: #171717;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #0a0a0a;
    --foreground: #ededed;
  }
}

body {
  color: var(--foreground);
  background: var(--background);
  font-family: Arial, Helvetica, sans-serif;
}

@layer utilities {
  .text-balance {
    text-wrap: balance;
  }
}
'''
        (self.project_path / "src" / "app").mkdir(parents=True, exist_ok=True)
        output_path = self.project_path / "src" / "app" / "globals.css"
        output_path.write_text(content)


__all__ = ["PackageJsonGenerator", "ConfigGenerator", "TailwindConfigGenerator"]
