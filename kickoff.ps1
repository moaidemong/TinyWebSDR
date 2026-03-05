# kickoff.ps1
param(
  [string]$ProjectName = "TinyWebSDR",
  [string]$GithubOwner = "<YOUR_GITHUB_ID_OR_ORG>",
  [ValidateSet("public","private")] [string]$Visibility = "private"
)

$ErrorActionPreference = "Stop"

function Test-Command {
  param([string]$Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-OriginRemote {
  param(
    [string]$RepoUrl
  )

  $originUrl = git remote get-url origin 2>$null
  if ($LASTEXITCODE -eq 0 -and $originUrl) {
    if ($originUrl -ne $RepoUrl) {
      git remote set-url origin $RepoUrl
      Write-Host "Updated origin -> $RepoUrl"
    } else {
      Write-Host "origin already set -> $RepoUrl"
    }
  } else {
    git remote add origin $RepoUrl
    Write-Host "Added origin -> $RepoUrl"
  }
}

# 0) prerequisite check
if (!(Test-Command "git")) {
  throw "git is not installed or not in PATH."
}
git --version | Out-Null

$hasGh = Test-Command "gh"
if ($hasGh) {
  gh --version | Out-Null
} else {
  Write-Host "gh is not installed. Will use manual repo flow."
}

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
if (-not (git config --global user.name)) {
  throw 'git user.name is missing. Run: git config --global user.name "Your Name"'
}
if (-not (git config --global user.email)) {
  throw 'git user.email is missing. Run: git config --global user.email "you@example.com"'
}

git add .

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
  Write-Host "No staged changes to commit."
} elseif ($LASTEXITCODE -eq 1) {
  $commitOutput = git commit -m "chore: project kickoff (docs + conventions)" 2>&1
  if ($LASTEXITCODE -ne 0) {
    Write-Host $commitOutput
    throw "Commit failed."
  }
  Write-Host $commitOutput
} else {
  throw "git diff --cached --quiet failed."
}

# 4) create/push GitHub repo (with fallback)
$repo = "$GithubOwner/$ProjectName"
$repoUrl = "https://github.com/$repo.git"

if ($hasGh) {
  gh auth status *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "gh is installed but not authenticated. Run: gh auth login"
  }

  gh repo view $repo *> $null
  if ($LASTEXITCODE -ne 0) {
    $createOutput = gh repo create $repo --$Visibility 2>&1
    if ($LASTEXITCODE -ne 0) {
      Write-Host $createOutput
      throw "Failed to create GitHub repository via gh."
    }
    Write-Host "Created GitHub repo: https://github.com/$repo"
  } else {
    Write-Host "GitHub repo already exists: https://github.com/$repo"
  }
} else {
  Write-Host ""
  Write-Host "Create GitHub repo manually (if not already created):"
  Write-Host "https://github.com/new"
  Write-Host "- Owner: $GithubOwner"
  Write-Host "- Repository name: $ProjectName"
  Write-Host "- Visibility: $Visibility"
}

Ensure-OriginRemote -RepoUrl $repoUrl

$pushOutput = git push -u origin main 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host $pushOutput
  if ($pushOutput -match "Repository not found") {
    throw "Remote repository not found. Check owner/repo name and access permissions."
  }
  if ($pushOutput -match "Could not read from remote repository") {
    throw "No access to remote repository. Check authentication and repository permissions."
  }
  throw "git push failed."
}
Write-Host $pushOutput

Write-Host "Kickoff complete: https://github.com/$repo"
