#!/bin/bash

# Exit when gitleaks is not installed
if ! command -v gitleaks &> /dev/null; then
    echo "Warning: gitleaks is not installed. Skipping..." >&2
    sleep 10
    exit 0
fi

# Install commit-msg hook with a symlink if it is not already there
repo_root=$(git rev-parse --show-toplevel)

if [[ ! -L ${repo_root}/.git/hooks/commit-msg ]]; then
    ln -s ${repo_root}/.pre-commit-hooks/append-gitleaks-signature.sh ${repo_root}/.git/hooks/commit-msg
fi

# Run gitleaks to detect hardcoded secrets
gitleaks git --pre-commit --redact --staged --no-banner --no-color --log-level error --verbose
gl=$?

# Exit if gitleaks found issues
if [[ ${gl} -ne 0 ]]; then
    exit ${gl}
fi

# Signal success so the commit-msg hook generates the signature
gitleaks version > .git/.gitleaks_passed

exit 0
