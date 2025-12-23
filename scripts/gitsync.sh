#!/bin/bash
set -e

cd "$(git rev-parse --show-toplevel)"

git fetch origin
git fetch github

# Check if they've diverged
GITHUB_HEAD=$(git rev-parse github/master)
GITLAB_HEAD=$(git rev-parse origin/master)

if [ "$GITHUB_HEAD" = "$GITLAB_HEAD" ]; then
    echo "Already in sync"
    exit 0
fi

# Fast-forward local master to whichever is ahead
git checkout master
git merge --ff-only origin/master || true
git merge --ff-only github/master || true

# Push to both
git push origin master
git push github master

echo "Synced"
