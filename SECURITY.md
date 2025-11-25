# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x     | :white_check_mark: |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them via one of the following methods:

### Option 1: Private Vulnerability Reporting (Preferred)

Use GitHub's [private vulnerability reporting](https://github.com/manwithacat/dazzle/security/advisories/new) to submit a report directly.

### Option 2: Email

Send details to the repository owner via the email associated with their GitHub profile.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Resolution target**: Depends on severity

### Severity Levels

| Level    | Description                              | Target Resolution |
|----------|------------------------------------------|-------------------|
| Critical | RCE, data breach, auth bypass            | 24-48 hours       |
| High     | Significant security impact              | 1 week            |
| Medium   | Limited impact, requires specific conditions | 2-4 weeks      |
| Low      | Minimal impact                           | Next release      |

## Security Considerations for DAZZLE

Since DAZZLE generates code, consider these security aspects:

### Generated Code
- Review generated code before deploying to production
- Generated backends should be treated as starting points, not production-ready
- Always sanitize user inputs in generated applications

### DSL Files
- DSL files are parsed and may influence code generation
- Only use DSL files from trusted sources
- Validate DSL files in CI before merging

### Dependencies
- We use `pip-audit` in CI to check for vulnerable dependencies
- Report any dependency-related concerns through the same channels

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers in our release notes (unless anonymity is requested).
