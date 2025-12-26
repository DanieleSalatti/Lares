---
name: git-workflow
description: How to commit and push changes to git repositories. Use when making code changes, updating documentation, or modifying version-controlled files.
---

# Git Workflow

Standard workflow for committing and pushing changes.

## Quick Reference

**Key principle:** Always push after committing - don't leave unpushed commits.

## Workflow

### Step 1: Stage and Commit

Batch operations for efficiency:

```bash
cd /path/to/repo && git add -A && git commit -m "descriptive message" && git push
```

### Step 2: Commit Message Patterns

Use clear, descriptive messages:
- `feat: <description>` - new features
- `fix: <description>` - bug fixes
- `docs: <description>` - documentation updates
- `test: <description>` - test additions/changes
- `refactor: <description>` - code refactoring
- `chore: <description>` - maintenance tasks

### Step 3: Verify Success

Check the output for:
- `[branch hash] message` - commit successful
- `branch -> branch` - push successful

## Common Issues

**"Nothing to commit"**: No changes staged. Check if files were modified.

**Push rejected**: Remote has changes. Pull first with `git pull --rebase`.

**Wrong branch**: Check current branch with `git branch` before committing.

## Anti-patterns

❌ Commit without pushing (leaves work in limbo)
❌ Vague commit messages like "update" or "fix"
❌ Committing sensitive data (.env, credentials)
❌ Large commits mixing unrelated changes
