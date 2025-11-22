# DAZZLE Infra Backends Specification (LLM-Facing Implementation Brief)

This document provides clear, imperative instructions for an LLM operating as an expert Python developer responsible for implementing **Docker** and **Terraform** infra backends for the DAZZLE system.  
These backends must be driven by the **project-level TOML manifest** and the **DAZZLE IR**, not by DSL syntax.

Your job is to implement these backends exactly as described.

---

# 1. Core Objectives

1. Consume DAZZLE’s **AppSpec IR** and **dazzle.toml** manifest.  
2. Infer infrastructure needs (db/cache/queue/worker) from IR semantics.  
3. Generate local development infrastructure using **Docker**.  
4. Generate cloud-ready infrastructure using **Terraform**.  
5. Produce conventional, boring, easy-to-maintain artefacts.  
6. Keep the DSL clean—do **not** introduce new DSL grammar for infrastructure.  
7. Allow infra backends to be optional and modular.

---

# 2. Inputs You Must Use

## 2.1 AppSpec IR (from DSL)
Use the IR to infer required infrastructure:
- If entities exist → provision a database.
- If experiences or integrations require async work → provide queue + workers.
- If webhooks exist → expose endpoints.
- If services require outbound calls → supply env vars for credentials, endpoints, etc.

Do **not** require humans to specify infra manually inside the DSL.

## 2.2 dazzle.toml Manifest
Read infra configuration from:

```toml
[infra]
backends = ["docker", "terraform"]

[infra.docker]
variant = "compose"
image_name = "my_app_image"

[infra.terraform]
root_module = "./infra/terraform"
cloud_provider = "aws"
environments = ["dev", "staging", "prod"]
```

Implement:
- Backend selection
- Backend configuration
- Output folder locations

---

# 3. Docker Backend Specification

## 3.1 Tasks You Must Perform

1. Generate a standard Dockerfile:
   - Use python:3.11-slim or similar.
   - Copy app code.
   - Install dependencies.
   - Expose optional entrypoints from manifest.
   - Keep the file idiomatic and minimal.

2. Generate docker-compose / compose.yaml for local development.
   - Always include:
     - app service
     - database service (if IR contains entities)
     - redis service (if queue or async features exist)
     - worker service (if async work exists)
   - Wire dependencies correctly using environment variables.

3. Generate optional:
   - `.dockerignore`
   - `dev.env.example`
   - `README.md` explaining usage.

## 3.2 Output Structure

```
infra/
  docker/
    Dockerfile
    compose.yaml
    .dockerignore
    dev.env.example
    README.md
```

## 3.3 Rules
- Do not attempt production orchestration here.
- Docker backend is strictly for **local development**.
- Do not hard‑wire cloud assumptions.

---

# 4. Terraform Backend Specification

## 4.1 Tasks You Must Perform

1. Create a Terraform module structure that provisions:
   - compute resources for the app container(s)
   - managed database (Postgres)
   - managed cache (Redis)
   - managed queue/topic
   - networking basics (VPC/subnets/security groups)
   - secrets/variables wiring

2. Use IR semantics to decide what must exist.
   - Entities → DB
   - Integrations → queue + worker
   - Webhooks → inbound routing

3. Support multiple environments:
   - Create per-environment directories (dev/staging/prod).
   - Link modules with env‑specific variables.

4. Generate environment wrappers using:
   - main.tf
   - backend.tf
   - terraform.tfvars

## 4.2 Output Structure

```
infra/
  terraform/
    modules/
      app/
      db/
      cache/
      queue/
    envs/
      dev/
        main.tf
        backend.tf
        terraform.tfvars
      staging/
      prod/
```

## 4.3 Rules
- Terraform backend **must not** depend on Docker.
- Terraform backend assumes a **container image already exists** (provided through manifest fields or env vars).
- Keep modules small, overridable, and vendor-neutral.
- Do not attempt to support every cloud feature; generate minimal viable infra.

---

# 5. Interaction Model

Implement the following command pattern:

```
dazzle infra docker
dazzle infra terraform
dazzle infra all
```

Each command must:
- Load dazzle.toml
- Load IR
- Run selected backend(s)
- Write output to appropriate directories

---

# 6. Key Principles You Must Follow

1. **No infra syntax in the DSL.**  
   All infra configuration lives in TOML + IR inference.

2. **Backends must be independent.**  
   Docker is local-only. Terraform is cloud-only. Neither must rely on the other.

3. **Generated artefacts must be editable.**  
   Developers should feel free to modify anything produced by backends.

4. **DAZZLE IR drives infrastructure choices.**  
   Do not require humans to micromanage infra details.

5. **Minimize cognitive load.**  
   Always choose conventional defaults.

---

# 7. Deliverables You Must Generate (as code)

When building DAZZLE’s infra backends:
- Implement `dazzle/backends/infra_docker.py`
- Implement `dazzle/backends/infra_terraform.py`
- Implement CLI integration in `dazzle/cli.py`
- Create template scaffolds for all artefacts listed above
- Create unit tests validating file generation

---

# End of Specification
