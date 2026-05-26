"""Output formatting: renders structured data as JSON or Rich tables."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table


def render_json(data: Any) -> None:
    """Print data as clean JSON to stdout."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    sys.stdout.write("\n")


def render_rich_table(
    title: str,
    columns: list[str],
    rows: list[list[str]],
) -> None:
    """Print a Rich table to stdout."""
    console = Console()
    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*row)
    console.print(table)
