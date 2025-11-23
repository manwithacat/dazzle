"""
Static files generator for Django Micro backend.

Generates CSS and other static files.
"""

from pathlib import Path

from ...base import Generator, GeneratorResult


class StaticGenerator(Generator):
    """
    Generate static files (CSS, JS).

    Creates:
    - app/static/css/style.css - Main stylesheet
    """

    def __init__(self, spec, output_dir: Path, app_name: str = "app"):
        """
        Initialize static generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate static files."""
        result = GeneratorResult()

        # Create static directory structure in app directory
        static_dir = self.output_dir / self.app_name / "static" / "css"
        self._ensure_dir(static_dir)

        # Generate CSS
        css_content = self._generate_css()
        css_path = static_dir / "style.css"
        self._write_file(css_path, css_content)
        result.add_file(css_path)

        return result

    def _generate_css(self) -> str:
        """Generate main CSS file."""
        return """/* DAZZLE Generated Styles */

:root {
    --primary-color: #4a90e2;
    --secondary-color: #6c757d;
    --danger-color: #dc3545;
    --success-color: #28a745;
    --border-color: #ddd;
    --bg-gray: #f8f9fa;
}

* {
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 0;
}

header {
    background: var(--primary-color);
    color: white;
    padding: 1rem 2rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

header h1 {
    margin: 0;
    font-size: 1.5rem;
}

header h1 a {
    color: white;
    text-decoration: none;
}

header nav ul {
    margin: 0.5rem 0 0 0;
}

header nav a {
    color: white;
    text-decoration: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    transition: background 0.2s;
}

header nav a:hover {
    background: rgba(255, 255, 255, 0.1);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

h2 {
    color: #333;
    margin-bottom: 1rem;
}

/* Buttons */
.btn {
    display: inline-block;
    padding: 0.5rem 1rem;
    background: var(--primary-color);
    color: white;
    text-decoration: none;
    border-radius: 4px;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    transition: background 0.2s;
}

.btn:hover {
    background: #3a7bc8;
}

.btn-secondary {
    background: var(--secondary-color);
}

.btn-secondary:hover {
    background: #5a6268;
}

.btn-danger {
    background: var(--danger-color);
}

.btn-danger:hover {
    background: #c82333;
}

/* Cards */
.card {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.card h2 {
    margin-top: 0;
    color: var(--primary-color);
}

.card p {
    color: #666;
    margin-bottom: 1rem;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

table th,
table td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

table th {
    background: var(--bg-gray);
    font-weight: 600;
    color: #555;
}

table tbody tr:hover {
    background: var(--bg-gray);
}

table a {
    color: var(--primary-color);
    text-decoration: none;
}

table a:hover {
    text-decoration: underline;
}

/* Forms */
form {
    max-width: 600px;
}

form p {
    margin-bottom: 1rem;
}

form label {
    display: block;
    margin-bottom: 0.25rem;
    font-weight: 500;
    color: #555;
}

form input[type="text"],
form input[type="email"],
form input[type="number"],
form input[type="date"],
form input[type="datetime-local"],
form select,
form textarea {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 1rem;
    font-family: inherit;
}

form textarea {
    resize: vertical;
}

form input:focus,
form select:focus,
form textarea:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
}

.errorlist {
    list-style: none;
    padding: 0;
    margin: 0.5rem 0;
    color: var(--danger-color);
}

/* Messages */
.messages {
    list-style: none;
    padding: 0;
    margin: 0 0 1.5rem 0;
}

.messages li {
    padding: 1rem;
    margin-bottom: 0.5rem;
    border-radius: 4px;
    border-left: 4px solid;
}

.messages .success {
    background: #d4edda;
    border-color: var(--success-color);
    color: #155724;
}

.messages .error {
    background: #f8d7da;
    border-color: var(--danger-color);
    color: #721c24;
}

.messages .info {
    background: #d1ecf1;
    border-color: #17a2b8;
    color: #0c5460;
}

.messages .warning {
    background: #fff3cd;
    border-color: #ffc107;
    color: #856404;
}

/* Pagination */
.pagination {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}

.pagination a {
    padding: 0.5rem 0.75rem;
    background: white;
    border: 1px solid var(--border-color);
    color: var(--primary-color);
    text-decoration: none;
    border-radius: 4px;
}

.pagination a:hover {
    background: var(--bg-gray);
}

.pagination span {
    color: #666;
}

/* Responsive */
@media (max-width: 768px) {
    .container {
        padding: 1rem;
    }

    header {
        padding: 1rem;
    }

    header nav ul {
        flex-direction: column;
        gap: 0.5rem !important;
    }

    table {
        font-size: 0.875rem;
    }

    table th,
    table td {
        padding: 0.5rem;
    }
}
"""
