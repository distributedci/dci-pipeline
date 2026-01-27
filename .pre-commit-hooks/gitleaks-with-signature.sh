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

# Create a signature and a hash
GL_VER=$(gitleaks version)
TS=$(date --utc +%FT%T)
GL_SIGN=$(echo -n "${GL_VER}|${TS}" | base64)
GL_HASH=$(echo -n ${GL_SIGN}| sha1sum | awk '{print $1}')

# Store the data in a temp file to be added as a git msg
cat > .git/.gitleaks_data <<EOF
Gitleaks-Sign: ${GL_SIGN}
Gitleaks-Hash: ${GL_HASH}
EOF

exit 0
