"""
Rich interactive UI components for DAZZLE CLI.

Provides cursor-navigable selection menus with colors and styling.
"""

import sys
from dataclasses import dataclass
from typing import TypeVar, Generic

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich import box

# Check if we're in a TTY for interactive features
IS_TTY = sys.stdin.isatty() and sys.stdout.isatty()

console = Console()

T = TypeVar("T")


@dataclass
class SelectOption(Generic[T]):
    """An option in a selection menu."""

    value: T
    label: str
    description: str = ""
    badge: str = ""  # e.g., "NEW", "RECOMMENDED"
    badge_style: str = "bold green"


# Style definitions
STYLES = {
    "title": Style(color="bright_cyan", bold=True),
    "subtitle": Style(color="bright_black"),
    "selected": Style(color="bright_white", bgcolor="blue", bold=True),
    "unselected": Style(color="white"),
    "description": Style(color="bright_black"),
    "badge_new": Style(color="green", bold=True),
    "badge_recommended": Style(color="yellow", bold=True),
    "success": Style(color="green", bold=True),
    "error": Style(color="red", bold=True),
    "warning": Style(color="yellow"),
    "info": Style(color="cyan"),
    "muted": Style(color="bright_black"),
    "highlight": Style(color="bright_cyan"),
}


def print_header(title: str, subtitle: str = "") -> None:
    """Print a styled header."""
    console.print()
    console.print(Text(title, style=STYLES["title"]))
    if subtitle:
        console.print(Text(subtitle, style=STYLES["subtitle"]))
    console.print()


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(Text(f"✓ {message}", style=STYLES["success"]))


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(Text(f"✗ {message}", style=STYLES["error"]))


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(Text(f"⚠ {message}", style=STYLES["warning"]))


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(Text(f"ℹ {message}", style=STYLES["info"]))


def select_interactive(
    options: list[SelectOption[T]],
    title: str = "Select an option",
    subtitle: str = "",
) -> T | None:
    """
    Interactive selection with keyboard navigation.

    Uses arrow keys for navigation and Enter to select.
    Falls back to numbered input if not in a TTY.

    Args:
        options: List of SelectOption items
        title: Title shown above the menu
        subtitle: Optional subtitle

    Returns:
        Selected value or None if cancelled
    """
    if not options:
        return None

    if not IS_TTY:
        # Fallback to simple numbered selection
        return _select_simple(options, title, subtitle)

    try:
        return _select_with_keyboard(options, title, subtitle)
    except (ImportError, Exception):
        # Fallback if keyboard input fails
        return _select_simple(options, title, subtitle)


def _select_with_keyboard(
    options: list[SelectOption[T]],
    title: str,
    subtitle: str,
) -> T | None:
    """Keyboard-navigable selection menu."""
    import termios
    import tty

    selected_idx = 0

    def render_menu() -> None:
        """Render the selection menu."""
        # Clear screen and move cursor to top
        console.print("\033[2J\033[H", end="")

        # Header
        print_header(title, subtitle)

        # Options
        for i, opt in enumerate(options):
            is_selected = i == selected_idx

            # Build the line
            prefix = "› " if is_selected else "  "
            label_style = STYLES["selected"] if is_selected else STYLES["unselected"]

            line = Text()
            line.append(prefix, style=STYLES["highlight"] if is_selected else STYLES["muted"])
            line.append(f"{opt.label}", style=label_style)

            if opt.badge:
                badge_style = STYLES.get(f"badge_{opt.badge.lower()}", STYLES["badge_new"])
                line.append(f" [{opt.badge}]", style=badge_style)

            console.print(line)

            # Description on next line if selected
            if is_selected and opt.description:
                console.print(Text(f"    {opt.description}", style=STYLES["description"]))

        console.print()
        console.print(Text("↑/↓ Navigate  Enter Select  q Cancel", style=STYLES["muted"]))

    def get_key() -> str:
        """Get a single keypress."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            # Handle escape sequences (arrow keys)
            if ch == "\x1b":
                ch += sys.stdin.read(2)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    try:
        while True:
            render_menu()
            key = get_key()

            if key == "\x1b[A":  # Up arrow
                selected_idx = (selected_idx - 1) % len(options)
            elif key == "\x1b[B":  # Down arrow
                selected_idx = (selected_idx + 1) % len(options)
            elif key in ("\r", "\n"):  # Enter
                # Clear and return
                console.print("\033[2J\033[H", end="")
                return options[selected_idx].value
            elif key in ("q", "Q", "\x03"):  # q or Ctrl+C
                console.print("\033[2J\033[H", end="")
                return None
            elif key.isdigit():
                # Direct number selection
                idx = int(key) - 1
                if 0 <= idx < len(options):
                    console.print("\033[2J\033[H", end="")
                    return options[idx].value

    except KeyboardInterrupt:
        console.print("\033[2J\033[H", end="")
        return None


def _select_simple(
    options: list[SelectOption[T]],
    title: str,
    subtitle: str,
) -> T | None:
    """Simple numbered selection (fallback for non-TTY)."""
    print_header(title, subtitle)

    # Create a table for options
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Num", style="cyan", width=4)
    table.add_column("Name", style="white")
    table.add_column("Badge", style="green")
    table.add_column("Description", style="bright_black")

    for i, opt in enumerate(options, 1):
        badge = f"[{opt.badge}]" if opt.badge else ""
        table.add_row(
            f"{i}.",
            opt.label,
            badge,
            opt.description[:50] + "..." if len(opt.description) > 50 else opt.description,
        )

    console.print(table)
    console.print()

    while True:
        try:
            choice = console.input(Text("Enter number or name: ", style=STYLES["info"]))

            if not choice or choice.lower() in ("q", "quit", "cancel"):
                return None

            # Try as number
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx].value
            except ValueError:
                pass

            # Try as name (case-insensitive partial match)
            choice_lower = choice.lower()
            for opt in options:
                if opt.label.lower() == choice_lower or opt.label.lower().startswith(choice_lower):
                    return opt.value

            console.print(
                Text(f"Invalid choice. Enter 1-{len(options)} or option name.", style=STYLES["error"])
            )

        except (KeyboardInterrupt, EOFError):
            console.print()
            return None


def display_options_table(
    options: list[SelectOption],
    title: str = "",
    show_numbers: bool = True,
) -> None:
    """Display options in a formatted table (non-interactive)."""
    if title:
        print_header(title)

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")

    if show_numbers:
        table.add_column("#", style="dim", width=4)

    table.add_column("Name", style="white bold")
    table.add_column("Description", style="bright_black")

    for i, opt in enumerate(options, 1):
        badge_text = f" [{opt.badge}]" if opt.badge else ""
        name_with_badge = f"{opt.label}{badge_text}"

        if show_numbers:
            table.add_row(str(i), name_with_badge, opt.description)
        else:
            table.add_row(name_with_badge, opt.description)

    console.print(table)
    console.print()


def confirm(message: str, default: bool = True) -> bool:
    """Ask for confirmation with Y/n prompt."""
    suffix = " [Y/n]" if default else " [y/N]"
    prompt = Text(message + suffix + " ", style=STYLES["info"])

    try:
        response = console.input(prompt).strip().lower()

        if not response:
            return default

        return response in ("y", "yes")

    except (KeyboardInterrupt, EOFError):
        console.print()
        return False


def print_step(step_num: int, total: int, message: str) -> None:
    """Print a step indicator."""
    console.print(
        Text(f"[{step_num}/{total}] ", style=STYLES["muted"]) +
        Text(message, style=STYLES["info"])
    )


def print_divider(char: str = "─", width: int = 60) -> None:
    """Print a divider line."""
    console.print(Text(char * width, style=STYLES["muted"]))


def create_panel(content: str, title: str = "", style: str = "cyan") -> Panel:
    """Create a styled panel."""
    return Panel(
        content,
        title=title,
        title_align="left",
        border_style=style,
        padding=(1, 2),
    )
