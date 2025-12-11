#!/usr/bin/env bun
/**
 * DAZZLE CLI Entry Point
 *
 * Fast, LLM-friendly command line interface for DAZZLE.
 */

import { run } from './cli'

// Must await the async run() to prevent early exit
await run()
