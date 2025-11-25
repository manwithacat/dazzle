# STACK LADDER SPECIFICATION (IMPERATIVE INSTRUCTIONS FOR LLM)

## OBJECTIVE
Define a logical progression of increasingly sophisticated technical stacks. Present each level as a clear upgrade path that an expert developer can scaffold, generate, or deploy. Maintain parallel Django (Python) and JavaScript (Node/Next.js) tracks.

---

## LEVEL 0 — MICRO DEV-ONLY STACKS

### 0A — Django Micro
- Initialize a Django project using the built-in development server.
- Configure SQLite as the database backend.
- Run a single process with no background workers.
- Execute locally without any deployment infrastructure.
- Use only minimal project structure for rapid prototyping.

### 0B — Express Micro
- Initialize a Node.js project using Express.
- Configure SQLite or an in-memory data layer.
- Run a single process.
- Execute locally with no deployment infrastructure.
- Mirror Django Micro’s simplicity for JavaScript developers.

---

## LEVEL 1 — ONEBOX STACKS

### 1A — Django Onebox
- Replace the development server with gunicorn or uvicorn.
- Add a Dockerfile and docker-compose configuration.
- Use Postgres via Docker or continue with SQLite.
- Serve static and media files directly or via Nginx inside the same compose stack.
- Deploy to a single host (e.g., EC2, VPS, local server) with `docker-compose up -d`.
- Configure application settings via environment variables.

### 1B — Next.js Onebox
- Create a fullstack Next.js application with API routes.
- Use SQLite or Postgres via Drizzle or Prisma.
- Package the app as a single Docker container.
- Include both UI and backend logic in one deployable unit.
- Deploy on a single host using docker-compose.

---

## LEVEL 2 — ONEBOX WITH CACHE + WORKER

### 2A — Django + Redis + Celery
- Upgrade the DB to Postgres inside Docker; discontinue SQLite.
- Add Redis as a broker and cache inside docker-compose.
- Add a Celery worker container for background tasks.
- Add an optional Celery beat container for scheduled tasks.
- Maintain a single physical host but multiple services via docker-compose.
- Use Redis for caching and task queueing.
- Offload long-running operations (e.g., DSL compilation) to Celery.

### 2B — Node + Redis + Worker
- Use Next.js or Express for the web container.
- Add Bull/BullMQ as the Redis-backed worker system.
- Add Redis and Postgres containers.
- Maintain the same one-host docker-compose architecture.

---

## LEVEL 3 — SMALL CLOUD WITH TERRAFORM

### 3A — Django on AWS (Managed Services)
- Replace containerized Postgres with RDS Postgres.
- Replace Redis container with ElastiCache Redis.
- Store static/media assets in S3 and serve via CloudFront.
- Deploy the web app via ECS Fargate or a managed EC2 instance.
- Deploy Celery workers as a second ECS service or a second EC2 process.
- Provision all infrastructure using Terraform:
  - VPC
  - Subnets and routing
  - RDS
  - ElastiCache
  - ECS or EC2
  - S3 + CloudFront
  - IAM roles

### 3B — Node on AWS (Managed Services)
- Deploy Next.js or Express as ECS/EC2 service(s).
- Deploy Node workers as ECS/EC2 worker processes.
- Use the same RDS, ElastiCache, S3, CloudFront, and Terraform layout.

---

## LEVEL 4 — MULTI-SERVICE DISTRIBUTED ARCHITECTURE

### Core Services
- Deploy the frontend separately:
  - Vercel or
  - S3 + CloudFront
- Deploy a Django REST or GraphQL API on ECS Fargate.
- Deploy Celery workers as a scalable ECS Fargate cluster.
- Use Redis or RabbitMQ as the broker (RabbitMQ via AWS MQ or self-managed).
- Use multi-AZ RDS Postgres.
- Add optional search (OpenSearch/Elastic) only if required.
- Implement CI/CD (GitHub Actions or equivalent) to:
  - Build and push Docker images
  - Plan/apply Terraform
  - Deploy services automatically

### JavaScript Equivalent
- Replace Django API with Express or NestJS.
- Replace Celery with Redis-backed Node worker system.
- Maintain identical AWS architecture components.

---

## LEVEL 5 — OPTIONAL ENHANCEMENTS

- Add centralized logging and metrics (CloudWatch, Prometheus, Grafana).
- Add Parameter Store or Secrets Manager for configuration.
- Add ALB and custom domains for multi-tenant routing.
- Add SNS/SQS for event-driven extensions.

---

## HOW TO OPERATIONALIZE THE LADDER

- Create templates for each level:
  - `django_template/level_X/`
  - `node_template/level_X/`
- For any given project, specify `stack_level` in configuration or spec.
- Generate code, infra, and deployment scaffolding based on the declared level.

END OF SPEC
