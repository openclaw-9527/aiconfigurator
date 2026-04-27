#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

apt update && apt install curl jq -y

# install claude code
curl -fsSL https://claude.ai/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1  # API compatibility
: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set (provide via env var)}"

# Onboard
# Mark claude as onboarded to avoid asking for login
[ -f ~/.claude.json ] || echo '{}' > ~/.claude.json
jq '.hasCompletedOnboarding = true' ~/.claude.json > tmp.json
mv tmp.json ~/.claude.json
# Register API key as approved
api_key_suffix="${ANTHROPIC_API_KEY: -20}"
jq --arg suffix "$api_key_suffix" '.customApiKeyResponses = ((.customApiKeyResponses // {}) + {"approved": [$suffix]})' ~/.claude.json > tmp.json
mv tmp.json ~/.claude.json

# Allow all tools for common workspace paths
for workspace in "$HOME" "/" "*"; do
    jq --arg ws "$workspace" '.projects[$ws] = ((.projects[$ws] // {}) + {"allowedTools": ["*"], "hasTrustDialogAccepted": true})' ~/.claude.json > tmp.json
    mv tmp.json ~/.claude.json
done

# Skip the dangerous-mode permission prompt
mkdir -p ~/.claude
[ -f ~/.claude/settings.json ] || echo '{}' > ~/.claude/settings.json
jq '.skipDangerousModePermissionPrompt = true' ~/.claude/settings.json > tmp.json && mv tmp.json ~/.claude/settings.json
