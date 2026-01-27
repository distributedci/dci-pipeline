#!/bin/bash

# Get the commit message file
COMMIT_MSG_FILE=$1

# Check if gitleaks data file exists from pre-commit hook
GL_DATA=".git/.gitleaks_data"

if [[ -f "${GL_DATA}" ]]; then
    # remove any line starting with Gitleaks-
    sed -i -e '/^Gitleaks-/d' "${COMMIT_MSG_FILE}"

    # Append data to commit message
    echo "" >> "${COMMIT_MSG_FILE}"
    cat "${GL_DATA}" >> "${COMMIT_MSG_FILE}"

    # Clean up temporary file
    rm -f "${GL_DATA}"
fi

exit 0
