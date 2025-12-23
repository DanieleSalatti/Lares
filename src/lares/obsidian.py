"""Obsidian vault integration for Lares.

Provides tools to read, write, search, and manage notes in an Obsidian vault.
Designed to work with a git-synced vault for safety and version control.
"""

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger()


def _get_vault_path() -> Path:
    """Get the configured vault path from environment or default."""
    # OBSIDIAN_VAULT_PATH is required - no hardcoded default
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    if vault_path:
        return Path(vault_path)
    # Fall back to ~/obsidian as a reasonable default
    return Path.home() / "obsidian"


def _ensure_vault_exists() -> bool:
    """Check if the vault directory exists."""
    vault = _get_vault_path()
    if not vault.exists():
        log.warning("obsidian_vault_not_found", path=str(vault))
        return False
    return True


def read_note(path: str) -> str:
    """
    Read a note from the Obsidian vault.

    Args:
        path: Relative path within the vault (e.g., "Journal/2024-12-24.md")
              Can omit .md extension.

    Returns:
        The note content, or an error message if not found.
    """
    if not _ensure_vault_exists():
        return "Error: Obsidian vault not found. Set OBSIDIAN_VAULT_PATH env var."

    vault = _get_vault_path()

    # Add .md extension if not present
    if not path.endswith(".md"):
        path = f"{path}.md"

    note_path = vault / path

    if not note_path.exists():
        return f"Note not found: {path}"

    try:
        content = note_path.read_text(encoding="utf-8")
        log.info("obsidian_note_read", path=path, size=len(content))
        return content
    except Exception as e:
        log.error("obsidian_read_error", path=path, error=str(e))
        return f"Error reading note: {e}"


def write_note(path: str, content: str, overwrite: bool = False) -> str:
    """
    Write or create a note in the Obsidian vault.

    Args:
        path: Relative path within the vault (e.g., "Journal/2024-12-24.md")
        content: The markdown content to write
        overwrite: If False, will not overwrite existing notes

    Returns:
        Success message or error description.
    """
    if not _ensure_vault_exists():
        return "Error: Obsidian vault not found. Set OBSIDIAN_VAULT_PATH env var."

    vault = _get_vault_path()

    # Add .md extension if not present
    if not path.endswith(".md"):
        path = f"{path}.md"

    note_path = vault / path

    # Check if note exists and we're not overwriting
    if note_path.exists() and not overwrite:
        return f"Note already exists: {path}. Use overwrite=True to replace."

    try:
        # Create parent directories if needed
        note_path.parent.mkdir(parents=True, exist_ok=True)

        note_path.write_text(content, encoding="utf-8")
        log.info("obsidian_note_written", path=path, size=len(content))
        return f"Successfully wrote note: {path}"
    except Exception as e:
        log.error("obsidian_write_error", path=path, error=str(e))
        return f"Error writing note: {e}"


def append_to_note(path: str, content: str, separator: str = "\n\n") -> str:
    """
    Append content to an existing note, or create it if it doesn't exist.

    Useful for journal entries where you want to add to the day's note.

    Args:
        path: Relative path within the vault
        content: Content to append
        separator: String to put between existing content and new content

    Returns:
        Success message or error description.
    """
    if not _ensure_vault_exists():
        return "Error: Obsidian vault not found. Set OBSIDIAN_VAULT_PATH env var."

    vault = _get_vault_path()

    if not path.endswith(".md"):
        path = f"{path}.md"

    note_path = vault / path

    try:
        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            new_content = existing.rstrip() + separator + content
        else:
            note_path.parent.mkdir(parents=True, exist_ok=True)
            new_content = content

        note_path.write_text(new_content, encoding="utf-8")
        log.info("obsidian_note_appended", path=path)
        return f"Successfully appended to note: {path}"
    except Exception as e:
        log.error("obsidian_append_error", path=path, error=str(e))
        return f"Error appending to note: {e}"


def search_notes(query: str, max_results: int = 10) -> str:
    """
    Search for notes containing the query string.

    Performs a simple case-insensitive text search across all markdown files.

    Args:
        query: Text to search for
        max_results: Maximum number of results to return

    Returns:
        Formatted string with matching notes and snippets.
    """
    if not _ensure_vault_exists():
        return "Error: Obsidian vault not found. Set OBSIDIAN_VAULT_PATH env var."

    vault = _get_vault_path()
    query_lower = query.lower()
    results = []

    try:
        for md_file in vault.rglob("*.md"):
            # Skip hidden files/folders
            if any(part.startswith(".") for part in md_file.parts):
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    # Get relative path
                    rel_path = md_file.relative_to(vault)

                    # Find snippet around match
                    idx = content.lower().find(query_lower)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(query) + 50)
                    snippet = content[start:end].replace("\n", " ").strip()
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(content):
                        snippet = snippet + "..."

                    results.append(f"- **{rel_path}**: {snippet}")

                    if len(results) >= max_results:
                        break
            except Exception:
                continue  # Skip files that can't be read

        if not results:
            return f"No notes found matching: {query}"

        return f"Found {len(results)} note(s) matching '{query}':\n\n" + "\n".join(results)

    except Exception as e:
        log.error("obsidian_search_error", query=query, error=str(e))
        return f"Error searching notes: {e}"


def list_notes(directory: str = "", include_subdirs: bool = False) -> str:
    """
    List notes in a directory of the vault.

    Args:
        directory: Relative path to list (empty string for vault root)
        include_subdirs: If True, include notes in subdirectories

    Returns:
        Formatted list of notes.
    """
    if not _ensure_vault_exists():
        return "Error: Obsidian vault not found. Set OBSIDIAN_VAULT_PATH env var."

    vault = _get_vault_path()
    target = vault / directory if directory else vault

    if not target.exists():
        return f"Directory not found: {directory or '(vault root)'}"

    try:
        notes = []
        folders = []

        if include_subdirs:
            for md_file in target.rglob("*.md"):
                if not any(part.startswith(".") for part in md_file.parts):
                    notes.append(str(md_file.relative_to(vault)))
        else:
            for item in sorted(target.iterdir()):
                if item.name.startswith("."):
                    continue
                if item.is_dir():
                    folders.append(f"📁 {item.name}/")
                elif item.suffix == ".md":
                    notes.append(f"📝 {item.name}")

        result_parts = []
        if directory:
            result_parts.append(f"Contents of {directory}/:\n")
        else:
            result_parts.append("Vault contents:\n")

        if folders:
            result_parts.append("Folders:\n" + "\n".join(folders))
        if notes:
            result_parts.append("Notes:\n" + "\n".join(sorted(notes)))

        if not folders and not notes:
            result_parts.append("(empty)")

        return "\n\n".join(result_parts)

    except Exception as e:
        log.error("obsidian_list_error", directory=directory, error=str(e))
        return f"Error listing notes: {e}"


def get_journal_path(
    user_timezone: str = "America/Los_Angeles",
    journal_folder: str = "Journal",
) -> str:
    """
    Get the path for today's journal entry.

    Args:
        user_timezone: Timezone to determine "today"
        journal_folder: Folder where journal entries live

    Returns:
        Path like "Journal/2024-12-24.md"
    """
    now = datetime.now(ZoneInfo(user_timezone))
    date_str = now.strftime("%Y-%m-%d")
    return f"{journal_folder}/{date_str}.md"


def add_journal_entry(
    entry: str,
    user_timezone: str = "America/Los_Angeles",
    journal_folder: str = "Journal",
    entry_time: bool = True,
) -> str:
    """
    Add an entry to today's journal.

    Args:
        entry: The journal entry text
        user_timezone: Timezone to determine "today" and entry time
        journal_folder: Folder where journal entries live
        entry_time: Whether to prefix entry with timestamp

    Returns:
        Success message or error description.
    """
    now = datetime.now(ZoneInfo(user_timezone))
    journal_path = get_journal_path(user_timezone, journal_folder)

    if entry_time:
        time_str = now.strftime("%I:%M %p")
        formatted_entry = f"### {time_str}\n\n{entry}"
    else:
        formatted_entry = entry

    # Check if this is a new journal file - add date header if so
    vault = _get_vault_path()
    full_path = vault / journal_path

    if not full_path.exists():
        date_header = now.strftime("# %A, %B %d, %Y\n\n")
        formatted_entry = date_header + formatted_entry

    return append_to_note(journal_path, formatted_entry)
