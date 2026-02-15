/**
 * Dazzle Site Page Script
 *
 * Handles theme toggling, Lucide icon initialization, and hash-based scrolling.
 * Section rendering is handled server-side by Jinja2 templates.
 */
(function() {
    'use strict';

    // ==========================================================================
    // Theme System (v0.16.0 - Issue #26)
    // ==========================================================================

    const STORAGE_KEY = 'dz-theme-variant';
    const THEME_LIGHT = 'light';
    const THEME_DARK = 'dark';

    function getSystemPreference() {
        if (typeof window === 'undefined') return THEME_LIGHT;
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        return mediaQuery.matches ? THEME_DARK : THEME_LIGHT;
    }

    function getStoredPreference() {
        if (typeof localStorage === 'undefined') return null;
        return localStorage.getItem(STORAGE_KEY);
    }

    function storePreference(variant) {
        if (typeof localStorage === 'undefined') return;
        localStorage.setItem(STORAGE_KEY, variant);
    }

    function applyTheme(variant) {
        const root = document.documentElement;
        root.setAttribute('data-theme', variant);
        root.style.colorScheme = variant;
        root.classList.remove('dz-theme-light', 'dz-theme-dark');
        root.classList.add('dz-theme-' + variant);
    }

    function initTheme() {
        const stored = getStoredPreference();
        const system = getSystemPreference();
        const variant = stored || system || THEME_LIGHT;
        applyTheme(variant);

        // Listen for system preference changes
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addEventListener('change', function(e) {
            if (!getStoredPreference()) {
                applyTheme(e.matches ? THEME_DARK : THEME_LIGHT);
            }
        });

        return variant;
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme') || THEME_LIGHT;
        const newVariant = current === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
        applyTheme(newVariant);
        storePreference(newVariant);
        return newVariant;
    }

    // Initialize theme immediately (before DOMContentLoaded)
    initTheme();

    // ==========================================================================
    // DOM Ready: Toggle Button + Lucide Icons + Hash Scroll
    // ==========================================================================

    document.addEventListener('DOMContentLoaded', function() {
        // Set up theme toggle button
        const toggleBtn = document.getElementById('dz-theme-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggleTheme);
        }

        // Initialize Lucide icons
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }

        // Scroll to hash fragment if present
        if (window.location.hash) {
            const target = document.getElementById(window.location.hash.slice(1));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        }
    });
})();
