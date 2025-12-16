// Mermaid diagram support for MkDocs Material
// Initializes Mermaid.js for rendering diagrams in documentation

if (window.mermaid) {
  window.mermaid.initialize({
    startOnLoad: true,
    theme: 'default',
    securityLevel: 'loose'
  });
}
