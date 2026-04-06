# Goose-Core Development Rules

## Git Identity (MANDATORY)

All commits and pushes to `Goose-Flight/Goose-Core` MUST use the Goose Flight identity:

```
git config user.name "Goose Flight"
git config user.email "admin@flygoose.dev"
```

These are already set in the repo-local `.git/config`. Do NOT override them with personal accounts.

**Push authentication:** All pushes MUST authenticate as `goose-flight` (NOT USTungsten).

The repo is configured with a local credential store (`~/.git-credentials-goose`) that provides the goose-flight PAT automatically. The remote URL uses `goose-flight@github.com` to force the correct identity.

**Pre-push verification (MANDATORY before every push):**

```bash
# 1. Verify git remote uses goose-flight
git remote get-url origin
# Must show: https://goose-flight@github.com/Goose-Flight/Goose-Core.git

# 2. Verify commit identity
git config user.name   # Must show "Goose Flight"
git config user.email  # Must show "admin@flygoose.dev"

# 3. Verify credential resolves to goose-flight (non-interactive)
echo -e "protocol=https\nhost=github.com\nusername=goose-flight\n" | git credential fill 2>/dev/null | grep username
# Must show: username=goose-flight
```

**If credential is missing or push fails with 403:**

```bash
# Re-configure the repo-local credential store
git remote set-url origin https://goose-flight@github.com/Goose-Flight/Goose-Core.git
git config --local credential.https://github.com.username goose-flight
git config --local credential.helper "store --file ~/.git-credentials-goose"
# Then ask the board for the current goose-flight PAT and store it:
# echo "https://goose-flight:<PAT>@github.com" > ~/.git-credentials-goose
```

**NEVER:**
- Push using USTungsten credentials
- Use `gh auth` for push operations (it defaults to USTungsten)
- Embed PATs in remote URLs in committed files
- Log, print, or expose the PAT in output or comments

## Commit Co-authorship

All agent commits must include:
```
Co-Authored-By: Paperclip <noreply@paperclip.ing>
```
