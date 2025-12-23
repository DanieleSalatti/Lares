"""Obsidian vault tools.

Wraps the obsidian module for Letta tool usage.
Note: Requires OBSIDIAN_VAULT_PATH to be configured.
"""

from lares.obsidian import (
    add_journal_entry,
    append_to_note,
    list_notes,
    read_note,
    search_notes,
    write_note,
)

__all__ = [
    "read_note",
    "write_note",
    "append_to_note",
    "search_notes",
    "list_notes",
    "add_journal_entry",
]
