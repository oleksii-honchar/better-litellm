# better-litellm Governance

This document defines the governance procedures for maintaining the `better-litellm` fork — how to make changes, sync with upstream, rebase feature branches, build, and push.

For an overview of the fork's purpose and features, see [BETTER-LITELLM.md](./BETTER-LITELLM.md).

---

## Fork Structure

```
                       upstream/BerriAI/litellm
                       ┌─────────────────────────┐
                       │  main (development)     │◀── upstream target, changes over time
                       └─────────────────────────┘
                             │
                             │ fork
                             ▼
            oleksii-honchar/better-litellm (origin)
            ┌─────────────────────────────────────┐
            │  patched/main (working branch)      │◀── patches + synced with upstream
            │  260522-feat-01, ...                │◀── feature branches off patched/main
            └─────────────────────────────────────┘
```

**Key rules:**
- **`patched/main`** — Your working branch. Contains patches + synced with upstream. All development happens here.
- **Feature branches** — Branch off `patched/main`. Rebased onto `patched/main` before merge.
- **`origin`** — Your fork (push target). NOT the original repo.
- **`upstream`** — Original repo (read-only, never push). Add it with: `git remote add upstream git@github.com:BerriAI/litellm.git`

---

## Core Principle: Preserve Our Patches

**Our patches are the highest priority.** When resolving any merge or rebase conflict:

1. **Always preserve our patch code** — if a conflict exists between our changes and upstream changes, our feature logic wins.
2. **Adapt to upstream structural changes** — if upstream changed APIs, types, or patterns, adapt our patch code to the new upstream patterns while preserving its behavior.
3. **Never discard our patches** — do NOT use `-X theirs` or blindly accept upstream's version when our patch code is involved.
4. **If unsure, keep both** — include both our code and upstream's code, then clean up manually.

---

## Syncing with Upstream (Staying Current)

**Before making any changes, always sync first:**

```bash
cd ~/www/misc/better-litellm

# 1. Fetch latest from both remotes
git fetch upstream main --quiet
git fetch origin --quiet

# 2. Check divergence
git log --oneline patched/main..upstream/main | wc -l  # commits behind
git log --oneline upstream/main..patched/main | wc -l  # commits ahead

# 3. Rebase patched/main onto upstream/main
git checkout patched/main
git rebase upstream/main

# 4. If conflicts occur, resolve them (preserve our patches!):
#    - Edit conflicted files — keep our patch code, adapt to upstream changes
#    - git add <resolved-file>
#    - git rebase --continue      (after resolving each conflict)
#    - git rebase --abort         (to cancel)

# 5. Push rebased branch to your fork
git push origin patched/main --force-with-lease
```

---

## Feature Branch Workflow

Feature branches are created from `patched/main` and must be rebased onto `patched/main` before they are merged back.

### Step 1: Create a feature branch from `patched/main`

```bash
cd ~/www/misc/better-litellm

# Ensure patched/main is up to date
git checkout patched/main
git pull origin patched/main

# Create feature branch (YYYYMM format)
git checkout -b 260522-feat-01

# Make your changes...
# ...

# Commit and push
git add .
git commit -m "feat: describe your change"
git push origin 260522-feat-01
```

### Step 2: Rebase feature branch onto `patched/main` (before merge)

```bash
# 1. Make sure patched/main is current
git checkout patched/main
git pull origin patched/main

# 2. Switch to feature branch
git checkout 260522-feat-01

# 3. Rebase onto patched/main
git rebase patched/main

# 4. Resolve any conflicts (our patches win)
#    - git add <resolved-file>
#    - git rebase --continue

# 5. Force-push the rebased branch
git push origin 260522-feat-01 --force-with-lease
```

### Step 3: Merge feature branch into `patched/main`

```bash
git checkout patched/main
git merge 260522-feat-01 --no-ff
git push origin patched/main
```

---

## Building and Running

### Local Dev (with uv)

```bash
cd ~/www/misc/better-litellm

# Install dependencies
uv sync

# Start the proxy with the local config
uv run litellm --config config.yaml

# Or use the convenience script
./scripts/start-dev.sh
```

### Local Dev (with pip)

```bash
cd ~/www/misc/better-litellm

# Install in development mode
pip install -e .

# Start the proxy
litellm --config config.yaml
```

### Start Script Options

```bash
./scripts/start-dev.sh              # Start proxy (default port 4000)
./scripts/start-dev.sh --stop       # Stop the proxy
./scripts/start-dev.sh --port 4001  # Start on different port
./scripts/start-dev.sh --help       # Show usage
```

### Verification

```bash
# Check the proxy is running
curl http://127.0.0.1:4000/health

# List available models
curl http://127.0.0.1:4000/v1/models

# Test a completion
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "qwopus3.6-27b", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 10}'
```

---

## Pushing Changes to GitHub

**After making local changes:**
```bash
cd ~/www/misc/better-litellm
git push origin patched/main
```

**If you need to force push (after rebase):**
```bash
git push origin patched/main --force-with-lease
```

---

## Recovery Scenarios

| Problem | Solution |
|---------|----------|
| Rebase fails with conflicts | Resolve conflicts (preserve our patches!), `git rebase --continue` |
| Rebase is too messy to continue | `git rebase --abort` to reset, then resolve manually |
| Accidentally lost our patch code | Check `git reflog` to recover, or re-apply from feature branch |
| Fork is far behind upstream | Run sync steps above, resolve conflicts iteratively |

---

## Common Mistakes to Avoid

- **Don't push to `upstream`** — `upstream` is read-only. Always push to `origin`.
- **Don't use `-X theirs` with local patches** — It will discard your changes on conflict.
- **Don't forget to fetch `origin/patched/main`** — Your fork's remote may have updates you haven't seen.
- **Don't merge feature branches without rebasing first** — Always rebase onto `patched/main` before merging.

---

## Environment Setup

### MAMMOTH_LAN_IP

The proxy connects to `http://mammoth.lan:8014/v1`. For local development, ensure `mammoth.lan` resolves:

**Option A — /etc/hosts:**
```bash
# Add to /etc/hosts (replace with actual IP)
sudo sh -c 'echo "<MAMMOTH_IP> mammoth.lan" >> /etc/hosts'
```

**Option B — Environment variable:**
```bash
export MAMMOTH_LAN_IP="<MAMMOTH_IP>"
# The start-dev.sh script uses this to update /etc/hosts temporarily
```

### uv

The recommended Python package manager. Install with:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Verification Commands

```bash
# Verify remotes are correct
git remote -v
# origin → oleksii-honchar/better-litellm.git (your fork)
# upstream → BerriAI/litellm.git (original)

# Verify current branch
git branch --show-current
# Should show: patched/main

# Verify divergence
git log --oneline origin/patched/main..patched/main | wc -l  # commits ahead
git log --oneline patched/main..origin/patched/main | wc -l  # commits behind
```
