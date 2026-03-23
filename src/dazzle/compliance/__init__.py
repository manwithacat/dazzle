"""Dazzle Compliance Compiler — generate audit documentation from DSL specifications.

Compiles framework taxonomies (ISO 27001, NIST CSF 2.0, SOC 2, etc.) against
DSL evidence (classify, permit, scope, transitions, processes, etc.) to produce
an AuditSpec IR that drives AI-powered document generation.

Modules:
    compiler    — Core compilation pipeline (taxonomy + evidence → AuditSpec)
    taxonomy    — Framework taxonomy loading and normalisation
    evidence    — DSL evidence extraction from AppSpec IR
    slicer      — AuditSpec slicing for per-document agent context
    citation    — Deterministic citation validation
    review      — Human-in-the-loop review data generation
    renderer    — Branded PDF rendering via WeasyPrint
    models      — Pydantic models for typed IR
    coordinator — Pipeline orchestration
"""
