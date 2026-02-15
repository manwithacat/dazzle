/**
 * Dazzle Site Page Renderer
 * Fetches page data from /_site/page/{route} and renders sections.
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

    // Set up toggle button
    document.addEventListener('DOMContentLoaded', function() {
        const toggleBtn = document.getElementById('dz-theme-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggleTheme);
        }
    });

    // ==========================================================================
    // Page Rendering
    // ==========================================================================

    const main = document.getElementById('dz-site-main');
    const route = main?.dataset.route || '/';

    // Slugify helper for auto-generating anchor IDs from headlines
    function slugify(text) {
        if (!text) return null;
        return text
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '');
    }

    // Get section ID: explicit id > auto-generated from headline > null
    function getSectionId(section) {
        if (section.id) return section.id;
        if (section.headline) return slugify(section.headline);
        return null;
    }

    // Generate id attribute string for section element
    function idAttr(section) {
        return section._computedId ? `id="${section._computedId}"` : '';
    }

    // Section renderers
    const renderers = {
        hero: renderHero,
        features: renderFeatures,
        feature_grid: renderFeatureGrid,
        cta: renderCTA,
        faq: renderFAQ,
        testimonials: renderTestimonials,
        stats: renderStats,
        steps: renderSteps,
        logo_cloud: renderLogoCloud,
        pricing: renderPricing,
        markdown: renderMarkdown,
        comparison: renderComparison,
        value_highlight: renderValueHighlight,
        split_content: renderSplitContent,
        card_grid: renderCardGrid,
        trust_bar: renderTrustBar,
    };

    function renderSectionHeader(section) {
        const headline = section.headline || '';
        const subhead = section.subhead || '';
        if (!headline && !subhead) return '';
        return `
            <div class="dz-section-header">
                ${headline ? `<h2>${headline}</h2>` : ''}
                ${subhead ? `<p class="dz-subhead">${subhead}</p>` : ''}
            </div>
        `;
    }

    function renderHero(section) {
        const headline = section.headline || '';
        const subhead = section.subhead || '';
        const primaryCta = section.primary_cta;
        const secondaryCta = section.secondary_cta;
        const media = section.media;

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml += `<a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a>`;
        }
        if (secondaryCta) {
            ctaHtml += `<a href="${secondaryCta.href || '#'}" class="btn btn-secondary btn-outline">${secondaryCta.label || 'Learn More'}</a>`;
        }

        let mediaHtml = '';
        if (media && media.kind === 'image' && media.src) {
            mediaHtml = `<div class="dz-hero-media"><img src="${media.src}" alt="${media.alt || ''}" class="dz-hero-image" /></div>`;
        }

        const hasMedia = mediaHtml ? 'dz-hero-with-media' : '';

        return `
            <section ${idAttr(section)} class="dz-section dz-section-hero ${hasMedia}">
                <div class="dz-section-content">
                    <div class="dz-hero-text">
                        <h1>${headline}</h1>
                        ${subhead ? `<p class="dz-subhead">${subhead}</p>` : ''}
                        ${ctaHtml ? `<div class="dz-cta-group">${ctaHtml}</div>` : ''}
                    </div>
                    ${mediaHtml}
                </div>
            </section>
        `;
    }

    function renderFeatures(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-feature-item">
                ${item.icon ? `<div class="dz-feature-icon"><i data-lucide="${item.icon}"></i></div>` : ''}
                <h3>${item.title || ''}</h3>
                <p>${item.body || ''}</p>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-features">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-features-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderFeatureGrid(section) {
        return renderFeatures(section);  // Same layout
    }

    function renderCTA(section) {
        const headline = section.headline || '';
        const body = section.body || section.subhead || '';
        const primaryCta = section.primary_cta;
        const secondaryCta = section.secondary_cta;

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml += `<a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a>`;
        }
        if (secondaryCta) {
            ctaHtml += `<a href="${secondaryCta.href || '#'}" class="btn btn-secondary btn-outline">${secondaryCta.label || 'Learn More'}</a>`;
        }

        return `
            <section ${idAttr(section)} class="dz-section dz-section-cta">
                <div class="dz-section-content">
                    <h2>${headline}</h2>
                    ${body ? `<p class="dz-subhead">${body}</p>` : ''}
                    ${ctaHtml ? `<div class="dz-cta-group">${ctaHtml}</div>` : ''}
                </div>
            </section>
        `;
    }

    function renderFAQ(section) {
        const headline = section.headline || 'Frequently Asked Questions';
        const items = section.items || [];
        const itemsHtml = items.map(item => `
            <details class="dz-faq-item">
                <summary>${item.question || ''}</summary>
                <p>${item.answer || ''}</p>
            </details>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-faq">
                <div class="dz-section-content">
                    <h2>${headline}</h2>
                    <div class="dz-faq-list">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderTestimonials(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-testimonial-item">
                <blockquote>"${item.quote || ''}"</blockquote>
                <div class="dz-testimonial-author">
                    ${item.avatar ? `<img src="${item.avatar}" alt="${item.author}" class="dz-avatar">` : ''}
                    <div>
                        <strong>${item.author || ''}</strong>
                        ${item.role ? `<span>${item.role}${item.company ? `, ${item.company}` : ''}</span>` : ''}
                    </div>
                </div>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-testimonials">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-testimonials-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderStats(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-stat-item">
                <span class="dz-stat-value">${item.value || ''}</span>
                <span class="dz-stat-label">${item.label || ''}</span>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-stats">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-stats-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderSteps(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-step-item">
                <span class="dz-step-number">${item.step || ''}</span>
                <div>
                    <h3>${item.title || ''}</h3>
                    <p>${item.body || ''}</p>
                </div>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-steps">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-steps-list">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderLogoCloud(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <a href="${item.href || '#'}" class="dz-logo-item" title="${item.name || ''}">
                <img src="${item.src || ''}" alt="${item.name || ''}">
            </a>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-logo-cloud">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-logos-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderPricing(section) {
        const tiers = section.tiers || [];
        const headerHtml = renderSectionHeader(section);
        const tiersHtml = tiers.map(tier => {
            const features = (tier.features || []).map(f => `<li>${f}</li>`).join('');
            const highlighted = tier.highlighted ? ' dz-pricing-highlighted' : '';
            const btnClass = tier.highlighted ? 'btn btn-secondary' : 'btn btn-primary';
            return `
                <div class="dz-pricing-tier${highlighted}">
                    <h3>${tier.name || ''}</h3>
                    <div class="dz-pricing-price">
                        <span class="dz-price">${tier.price || ''}</span>
                        ${tier.period ? `<span class="dz-period">/${tier.period}</span>` : ''}
                    </div>
                    ${tier.description ? `<p class="dz-pricing-description">${tier.description}</p>` : ''}
                    <ul class="dz-pricing-features">${features}</ul>
                    ${tier.cta ? `<a href="${tier.cta.href || '#'}" class="${btnClass}">${tier.cta.label || 'Get Started'}</a>` : ''}
                </div>
            `;
        }).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-pricing">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-pricing-grid">${tiersHtml}</div>
                </div>
            </section>
        `;
    }

    function renderMarkdown(section) {
        const content = section.content || '';
        return `
            <section ${idAttr(section)} class="dz-section dz-section-markdown">
                <div class="dz-section-content dz-prose">
                    ${content}
                </div>
            </section>
        `;
    }

    function renderComparison(section) {
        const columns = section.columns || [];
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);

        const thHtml = columns.map(col => {
            const cls = col.highlighted ? ' class="dz-comparison-highlighted"' : '';
            return `<th${cls}>${col.label || ''}</th>`;
        }).join('');

        const rowsHtml = items.map(row => {
            const cellsHtml = (row.cells || []).map((cell, i) => {
                const col = columns[i] || {};
                const cls = col.highlighted ? ' class="dz-comparison-highlighted"' : '';
                return `<td${cls}>${cell}</td>`;
            }).join('');
            return `<tr><td class="dz-comparison-feature">${row.feature || ''}</td>${cellsHtml}</tr>`;
        }).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-comparison">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-comparison-wrapper">
                        <table class="dz-comparison-table">
                            <thead><tr><th></th>${thHtml}</tr></thead>
                            <tbody>${rowsHtml}</tbody>
                        </table>
                    </div>
                </div>
            </section>
        `;
    }

    function renderValueHighlight(section) {
        const headline = section.headline || '';
        const subhead = section.subhead || '';
        const body = section.body || '';
        const primaryCta = section.primary_cta;

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml = `<div class="dz-cta-group"><a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a></div>`;
        }

        return `
            <section ${idAttr(section)} class="dz-section dz-section-value-highlight">
                <div class="dz-section-content">
                    <h2 class="dz-value-headline">${headline}</h2>
                    ${subhead ? `<p class="dz-subhead">${subhead}</p>` : ''}
                    ${body ? `<p class="dz-value-body">${body}</p>` : ''}
                    ${ctaHtml}
                </div>
            </section>
        `;
    }

    function renderSplitContent(section) {
        const headline = section.headline || '';
        const body = section.body || '';
        const media = section.media;
        const primaryCta = section.primary_cta;
        const alignment = section.alignment || 'left';

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml = `<div class="dz-cta-group dz-cta-group--left"><a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Learn More'}</a></div>`;
        }

        let mediaHtml = '';
        if (media && media.kind === 'image' && media.src) {
            mediaHtml = `<div class="dz-split-media"><img src="${media.src}" alt="${media.alt || ''}" /></div>`;
        }

        const orderCls = alignment === 'right' ? ' dz-split--reversed' : '';

        return `
            <section ${idAttr(section)} class="dz-section dz-section-split-content${orderCls}">
                <div class="dz-section-content dz-split-grid">
                    <div class="dz-split-text">
                        <h2>${headline}</h2>
                        ${body ? `<p>${body}</p>` : ''}
                        ${ctaHtml}
                    </div>
                    ${mediaHtml}
                </div>
            </section>
        `;
    }

    function renderCardGrid(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);

        const cardsHtml = items.map(item => {
            let ctaHtml = '';
            if (item.cta) {
                ctaHtml = `<a href="${item.cta.href || '#'}" class="btn btn-primary btn-sm">${item.cta.label || 'Learn More'}</a>`;
            }
            return `
                <div class="dz-card-item">
                    ${item.icon ? `<div class="dz-card-icon"><i data-lucide="${item.icon}"></i></div>` : ''}
                    <h3>${item.title || ''}</h3>
                    <p>${item.body || ''}</p>
                    ${ctaHtml}
                </div>
            `;
        }).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-card-grid">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-card-grid">${cardsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderTrustBar(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);

        const itemsHtml = items.map(item => `
            <div class="dz-trust-item">
                ${item.icon ? `<i data-lucide="${item.icon}"></i>` : ''}
                <span>${item.text || ''}</span>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-trust-bar">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-trust-strip">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderPage(pageData) {
        if (!main) return;

        const sections = pageData.sections || [];

        // Backward compat: if no sections but content exists,
        // synthesize a markdown section
        if (!sections.length && pageData.content) {
            sections.push({ type: 'markdown', content: pageData.content });
        }

        // Track used IDs to handle duplicates
        const usedIds = new Set();

        let html = '';

        for (const section of sections) {
            // Compute section ID (explicit > headline-based > null)
            let sectionId = getSectionId(section);

            // Handle duplicate IDs by appending a suffix
            if (sectionId && usedIds.has(sectionId)) {
                let suffix = 2;
                while (usedIds.has(`${sectionId}-${suffix}`)) {
                    suffix++;
                }
                sectionId = `${sectionId}-${suffix}`;
            }
            if (sectionId) {
                usedIds.add(sectionId);
            }

            // Inject computed ID into section for renderers to use
            section._computedId = sectionId;

            const renderer = renderers[section.type];
            if (renderer) {
                html += renderer(section);
            } else {
                console.warn(`Unknown section type: ${section.type}`);
            }
        }

        main.innerHTML = html || '<p>No content</p>';

        // Initialize Lucide icons after DOM update
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }

        // Scroll to fragment if present
        if (window.location.hash) {
            const target = document.getElementById(window.location.hash.slice(1));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        }
    }

    // Fetch and render page (skip if SSR content is already present)
    async function init() {
        // If the page was server-side rendered, content is already in the DOM.
        // Just initialize Lucide icons and handle hash scrolling.
        if (main && main.querySelector('.dz-section')) {
            if (typeof lucide !== 'undefined') { lucide.createIcons(); }
            if (window.location.hash) {
                const target = document.getElementById(window.location.hash.slice(1));
                if (target) { target.scrollIntoView({ behavior: 'smooth' }); }
            }
            return;
        }

        try {
            const apiRoute = route === '/' ? '' : route;
            const response = await fetch(`/_site/page${apiRoute}`);
            if (response.status === 404) {
                if (main) {
                    main.innerHTML = `
                        <section class="dz-section dz-section-hero">
                            <div class="dz-section-content dz-404-section">
                                <h1 class="dz-404-headline">404</h1>
                                <p class="dz-subhead">The page you&rsquo;re looking for doesn&rsquo;t exist.</p>
                                <div class="dz-cta-group dz-404-cta">
                                    <a href="/" class="btn btn-primary">Go Home</a>
                                </div>
                            </div>
                        </section>`;
                }
                return;
            }
            if (!response.ok) {
                throw new Error(`Failed to load page: ${response.status}`);
            }
            const pageData = await response.json();
            renderPage(pageData);
        } catch (error) {
            console.error('Error loading page:', error);
            if (main) {
                main.innerHTML = '<p class="dz-error">Failed to load page content.</p>';
            }
        }
    }

    init();
})();
