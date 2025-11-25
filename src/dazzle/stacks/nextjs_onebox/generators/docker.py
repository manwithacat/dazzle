"""
Docker configuration generator for Next.js Onebox.

Generates:
- Dockerfile (single container with Node.js + PostgreSQL)
- scripts/init-db.sh
- scripts/start.sh
"""

from ...base.generator import Generator, GeneratorResult


class DockerGenerator(Generator):
    """Generates Docker configuration for single-container deployment."""

    def generate(self) -> GeneratorResult:
        """Generate Docker files."""
        result = GeneratorResult()

        self._generate_dockerfile(result)
        self._generate_init_script(result)
        self._generate_start_script(result)
        self._generate_supervisord_config(result)

        return result

    def _generate_dockerfile(self, result: GeneratorResult) -> None:
        """Generate Dockerfile for single container."""
        content = """# DAZZLE Next.js Onebox - Single Container
# Contains both Next.js app and PostgreSQL

FROM node:20-alpine

# Install PostgreSQL and Supervisor
RUN apk add --no-cache postgresql postgresql-contrib supervisor

# Create postgres user directory
RUN mkdir -p /var/lib/postgresql/data && \\
    chown -R postgres:postgres /var/lib/postgresql

# Create app directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy Prisma schema
COPY prisma ./prisma/

# Generate Prisma client
RUN npx prisma generate

# Copy application code
COPY . .

# Build Next.js app
RUN npm run build

# Copy scripts
COPY scripts/init-db.sh /usr/local/bin/init-db.sh
COPY scripts/start.sh /usr/local/bin/start.sh
COPY supervisord.conf /etc/supervisord.conf

RUN chmod +x /usr/local/bin/init-db.sh /usr/local/bin/start.sh

# Expose ports
EXPOSE 3000 5432

# Set environment variables
ENV NODE_ENV=production
ENV DATABASE_URL=postgresql://postgres:postgres@localhost:5432/app?schema=public

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \\
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

# Start services
CMD ["/usr/local/bin/start.sh"]
"""
        path = self.output_dir / "Dockerfile"
        self._write_file(path, content)
        result.add_file(path)

    def _generate_init_script(self, result: GeneratorResult) -> None:
        """Generate database initialization script."""
        content = """#!/bin/sh
set -e

# Initialize PostgreSQL if needed
if [ ! -f /var/lib/postgresql/data/PG_VERSION ]; then
    echo "Initializing PostgreSQL database..."
    su postgres -c "initdb -D /var/lib/postgresql/data"

    # Start PostgreSQL temporarily
    su postgres -c "pg_ctl start -D /var/lib/postgresql/data -l /var/log/postgresql.log"
    sleep 3

    # Create database and user
    su postgres -c "createdb app"
    su postgres -c "psql -c \\"ALTER USER postgres PASSWORD 'postgres';\\""

    # Run Prisma migrations
    cd /app && npx prisma db push

    # Stop PostgreSQL (supervisor will start it)
    su postgres -c "pg_ctl stop -D /var/lib/postgresql/data"

    echo "Database initialized successfully."
else
    echo "Database already initialized."
fi
"""
        path = self.output_dir / "scripts" / "init-db.sh"
        self._write_file(path, content)
        result.add_file(path)

    def _generate_start_script(self, result: GeneratorResult) -> None:
        """Generate startup script."""
        content = """#!/bin/sh
set -e

# Initialize database if needed
/usr/local/bin/init-db.sh

# Start supervisor (manages both PostgreSQL and Next.js)
exec /usr/bin/supervisord -c /etc/supervisord.conf
"""
        path = self.output_dir / "scripts" / "start.sh"
        self._write_file(path, content)
        result.add_file(path)

    def _generate_supervisord_config(self, result: GeneratorResult) -> None:
        """Generate supervisord configuration."""
        content = """[supervisord]
nodaemon=true
logfile=/var/log/supervisord.log
pidfile=/var/run/supervisord.pid

[program:postgresql]
command=/usr/bin/postgres -D /var/lib/postgresql/data
user=postgres
autostart=true
autorestart=true
priority=1
stdout_logfile=/var/log/postgresql-stdout.log
stderr_logfile=/var/log/postgresql-stderr.log

[program:nextjs]
command=npm start
directory=/app
autostart=true
autorestart=true
priority=10
startsecs=10
startretries=3
stdout_logfile=/var/log/nextjs-stdout.log
stderr_logfile=/var/log/nextjs-stderr.log
environment=NODE_ENV="production",DATABASE_URL="postgresql://postgres:postgres@localhost:5432/app?schema=public"
"""
        path = self.output_dir / "supervisord.conf"
        self._write_file(path, content)
        result.add_file(path)
