#!/usr/bin/env bash
# Reproducible environment: clones the three supplied repos at the pinned base commits and installs tooling.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p repos
pin() { # name url sha
  [ -d "repos/$1/.git" ] || git clone -q "$2" "repos/$1"
  git -C "repos/$1" fetch -q origin "$3" 2>/dev/null || git -C "repos/$1" fetch -q --unshallow || true
  git -C "repos/$1" checkout -q "$3"
}
pin click   https://github.com/pallets/click                    08b803cf32ceb2ae6a772c62d5da42757a897d44
pin zod     https://github.com/colinhacks/zod                   d40c329910436e528d3c26cb1b9179e05abebf05
pin jsoncpp https://github.com/open-source-parsers/jsoncpp      93acc7b155048f1a66c43235cc205519f1e7a6ea
python3 -m venv .venv
.venv/bin/pip install -q -e repos/click pytest
# zod: its declared package manager ("nub") is unavailable; pnpm + a workspace file works.
if [ ! -d repos/zod/node_modules ]; then
  printf "packages:\n  - 'packages/*'\n" > repos/zod/pnpm-workspace.yaml
  (cd repos/zod && COREPACK_ENABLE_STRICT=0 npm_config_manage_package_manager_versions=false \
     npx -y pnpm@10 install --no-frozen-lockfile --ignore-scripts)
fi
echo "setup complete (needs python3, g++, node>=20)"
