#!/usr/bin/env bash
# Re-track files in Git LFS listed in to-retrack.txt

set -euo pipefail

# Find large .pdf and .zip files (49 MB+)
find . -type f \( -name '*.pdf' -o -name '*.zip' \) -size +49000k \
  | sort -u > to-retrack.txt

# Re-track each file
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  echo "Tracking with Git LFS: $file"
  git lfs track "$file"
done < to-retrack.txt

# Stage updated attributes file
git add .gitattributes

# Optional: Clean up
# rm to-retrack.txt
