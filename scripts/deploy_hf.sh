#!/bin/bash

set -e

WORK_BRANCH="feat/ux-ui"
DEPLOY_BRANCH="hf-temp"

git checkout $WORK_BRANCH

git branch -D $DEPLOY_BRANCH 2>/dev/null || true

git checkout --orphan $DEPLOY_BRANCH

git add .
git commit -m "Deploy to HuggingFace"

git push hf $DEPLOY_BRANCH:main --force

git checkout $WORK_BRANCH

git branch -D $DEPLOY_BRANCH