/**
 * Node.js Filesystem Adapter
 *
 * Production implementation of FileSystem using Node's fs module.
 * This adapter wraps Node's filesystem operations in the FileSystem interface,
 * allowing the core logic to be tested with mock implementations.
 */

import * as fs from 'fs';
import type { FileSystem } from '../core/pythonDiscovery';

/**
 * Production filesystem adapter using Node.js fs module.
 */
export const nodeFileSystem: FileSystem = {
    exists(path: string): boolean {
        try {
            return fs.existsSync(path);
        } catch {
            return false;
        }
    },

    readFile(path: string): string | null {
        try {
            return fs.readFileSync(path, 'utf8');
        } catch {
            return null;
        }
    },

    readDir(path: string): string[] {
        try {
            return fs.readdirSync(path);
        } catch {
            return [];
        }
    },
};

/**
 * In-memory filesystem for testing.
 */
export class MockFileSystem implements FileSystem {
    private files: Map<string, string> = new Map();
    private directories: Set<string> = new Set();

    constructor(initialState?: { files?: Record<string, string>; directories?: string[] }) {
        if (initialState?.files) {
            for (const [path, content] of Object.entries(initialState.files)) {
                this.files.set(path, content);
            }
        }
        if (initialState?.directories) {
            for (const dir of initialState.directories) {
                this.directories.add(dir);
            }
        }
    }

    /**
     * Add a file to the mock filesystem.
     */
    addFile(path: string, content: string): this {
        this.files.set(path, content);
        return this;
    }

    /**
     * Add a directory to the mock filesystem.
     */
    addDirectory(path: string, entries: string[] = []): this {
        this.directories.add(path);
        // Store directory entries as a special file
        this.files.set(`__dir__:${path}`, entries.join('\n'));
        return this;
    }

    /**
     * Add a file that just needs to exist (empty content).
     */
    addExisting(path: string): this {
        this.files.set(path, '');
        return this;
    }

    exists(path: string): boolean {
        return this.files.has(path) || this.directories.has(path);
    }

    readFile(path: string): string | null {
        return this.files.get(path) ?? null;
    }

    readDir(path: string): string[] {
        const entries = this.files.get(`__dir__:${path}`);
        if (entries === undefined) {
            return [];
        }
        return entries ? entries.split('\n') : [];
    }
}

/**
 * Create a mock filesystem with common Homebrew dazzle installation.
 */
export function createHomebrewMockFs(version: string = '0.12.0'): MockFileSystem {
    const fs = new MockFileSystem();

    // Homebrew wrapper script
    fs.addFile('/opt/homebrew/bin/dazzle', `#!/bin/bash
export DAZZLE_PYTHON="/opt/homebrew/Cellar/dazzle/${version}/libexec/bin/python"
export PYTHONPATH="/opt/homebrew/Cellar/dazzle/${version}/libexec/lib/python3.12/site-packages:$PYTHONPATH"
exec "/opt/homebrew/bin/dazzle-bin" "$@"
`);

    // Cellar structure
    fs.addDirectory('/opt/homebrew/Cellar/dazzle', [version]);
    fs.addExisting(`/opt/homebrew/Cellar/dazzle/${version}/libexec/bin/python`);

    return fs;
}

/**
 * Create a mock filesystem with pyenv setup.
 */
export function createPyenvMockFs(homeDir: string = '/Users/testuser'): MockFileSystem {
    const fs = new MockFileSystem();

    fs.addExisting(`${homeDir}/.pyenv/shims/python3`);
    fs.addExisting(`${homeDir}/.pyenv/shims/python`);

    return fs;
}

/**
 * Create a mock filesystem with a workspace virtual environment.
 */
export function createWorkspaceVenvMockFs(workspaceRoot: string): MockFileSystem {
    const fs = new MockFileSystem();

    fs.addExisting(`${workspaceRoot}/.venv/bin/python`);
    fs.addExisting(`${workspaceRoot}/.venv/bin/python3`);

    return fs;
}
