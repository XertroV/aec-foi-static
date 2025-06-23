#!/usr/bin/env bash
# Re-track files in Git LFS listed in to-retrack.txt

find . -type f -name '*.pdf' -size +49000k > to-retrack.txt
find . -type f -name '*.zip' -size +49000k >> to-retrack.txt

while IFS= read -r file; do
  # Skip empty lines
  [ -z "$file" ] && continue

  echo "Tracking with Git LFS: $file"
  git lfs track "$file"
done < to-retrack.txt

# Add the updated .gitattributes file to the index
git add .gitattributes
