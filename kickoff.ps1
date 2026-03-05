# kickoff.ps1
param(
  [string]$ProjectName = "TinyWebSDR",
  [string]$GithubOwner = "<YOUR_GITHUB_ID_OR_ORG>",
  [ValidateSet("public","private")] [string]$Visibility = "private"
)

$ErrorActionPreference = "Stop"

# 0) prerequisite check
git --version | Out-Null
gh --version | Out-Null

# 1) repo root
if (!(Test-Path ".git")) {
  git init
  git branch -M main
}

# 2) docs scaffold
New-Item -ItemType Directory -Force docs, docs\DECISIONS | Out-Null

@"
# Architecture
- Goal:
- Pipeline:
- Performance targets (latency/fps/drop):
- Runtime topology:
"@ | Set-Content docs\ARCHITECTURE.md -Encoding UTF8

@"
# Workflow
## Request format
- Goal
- DoD
- Constraints
- Priority/Deadline

## Progress format
- Done
- Next
- Blockers

## Decision record rule
- Decision
- Rationale
- Alternatives
- Date
"@ | Set-Content docs\WORKFLOW.md -Encoding UTF8

@"
# Glossary
- IQ:
- FFT row:
- Waterfall frame:
- Producer:
- Gateway:
- Latest-only:
- Backpressure:
"@ | Set-Content docs\GLOSSARY.md -Encoding UTF8

@"
# ADR-0001: Initial architecture
- Date:
- Status: Proposed
- Context:
- Decision:
- Consequences:
"@ | Set-Content docs\DECISIONS\ADR-0001-initial-architecture.md -Encoding UTF8

if (!(Test-Path "README.md")) {
@"
# $ProjectName
## Quick Start
## Architecture
## Development Rules
"@ | Set-Content README.md -Encoding UTF8
}

# 3) first commit
git add .
git commit -m "chore: project kickoff (docs + conventions)"
if ($LASTEXITCODE -ne 0) {
  Write-Host "No changes to commit."
}

# 4) create/push GitHub repo
$repo = "$GithubOwner/$ProjectName"
gh repo create $repo --$Visibility --source . --remote origin --push

Write-Host "Kickoff complete: https://github.com/$repo"
