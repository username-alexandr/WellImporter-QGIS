#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${GITHUB_WORKSPACE:-$(pwd)}"
PARTS_DIR="$ROOT_DIR/history-bootstrap/parts"
WORK_DIR="$RUNNER_TEMP/wellimporter-history"
ARCHIVE_B64="$WORK_DIR/history.b64"
ARCHIVE_XZ="$WORK_DIR/history.tar.xz"
EXTRACT_DIR="$WORK_DIR/extracted"
EXPECTED_SHA256="1fff209e715f7f5c88b5c49d8c87074bc899b4b74ca1d668670b4d3063cb9ff3"

VERSIONS=(
  1.1.0 1.2.0 1.3.0 1.4.0 1.4.1 1.4.2 1.4.3 1.4.4
  1.5.0 1.5.1 1.5.2 1.5.3 1.5.4 1.5.5 1.5.6
  1.6.0 1.7.0 1.8.0
  2.0.0 2.0.1 2.0.2 2.0.3 2.0.4 2.0.5
)

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR" "$EXTRACT_DIR"

# Части хранятся текстом, чтобы не искажать бинарный tar.xz при передаче
# через API. Порядок файлов part00..part15 является частью формата.
cat "$PARTS_DIR"/part* > "$ARCHIVE_B64"
base64 --decode "$ARCHIVE_B64" > "$ARCHIVE_XZ"

echo "$EXPECTED_SHA256  $ARCHIVE_XZ" | sha256sum --check --strict

tar -xJf "$ARCHIVE_XZ" -C "$EXTRACT_DIR"
HISTORY_ROOT="$EXTRACT_DIR/WellImporter_history_1.0.0_to_2.0.5"

for version in "${VERSIONS[@]}"; do
  source_dir="$HISTORY_ROOT/$version/WellImporter"
  if [[ ! -f "$source_dir/metadata.txt" || ! -f "$source_dir/__init__.py" ]]; then
    echo "Missing required files for $version" >&2
    exit 1
  fi

done

git config user.name "SashaRai"
git config user.email "56488397+SashaRai@users.noreply.github.com"

for version in "${VERSIONS[@]}"; do
  branch="archive/v$version"
  source_dir="$HISTORY_ROOT/$version/WellImporter"

  echo "Creating $branch"

  # Каждая архивная ветка создаётся как отдельный orphan snapshot.
  # Благодаря этому она не является кандидатом для слияния с main.
  git switch --detach >/dev/null 2>&1 || true
  git switch --orphan "history-$version"
  git rm -rf . >/dev/null 2>&1 || true
  git clean -fdx >/dev/null 2>&1 || true

  mkdir -p WellImporter
  cp -a "$source_dir"/. WellImporter/

  # В архивных ветках сохраняем только исходники, без кэшей Python.
  find WellImporter -type d -name '__pycache__' -prune -exec rm -rf {} + || true
  find WellImporter -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete || true

  cat > RELEASE.md <<EOF
# Well Importer $version

Historical source snapshot of Well Importer $version.

- Branch: \`$branch\`
- Purpose: source-code archive only
- Do not merge this branch into \`main\`.
- Current stable development continues in \`main\`.
EOF

  git add WellImporter RELEASE.md
  git commit -m "archive: Well Importer $version" \
    -m "Preserve the historical $version source snapshot. No functional changes applied."

  git push --force origin "HEAD:refs/heads/$branch"

done

echo "Created ${#VERSIONS[@]} historical branches successfully."
