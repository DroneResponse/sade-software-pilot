# Troubleshooting

+ [Troubleshooting](#troubleshooting)
    + [Command Not Found: `uv` or `just`](#command-not-found-uv-or-just)
    + [Command Not Found: `software-pilot`](#command-not-found-software-pilot)
    + [Import Errors](#import-errors)
    + [Tests Fail](#tests-fail)
    + [Git Push Rejected](#git-push-rejected)

## Command Not Found: `uv` or `just`

+ Install `uv`: see <https://docs.astral.sh/uv/getting-started/installation/>.
+ Installing `just`: see <https://just.systems/man/en/pre-built-binaries.html>.

## Command Not Found: `software-pilot`

Ensure you're in the project directory:

```bash
cd /path/to/sade-software-pilot
uv run software-pilot --drone-id=0
```

## Import Errors

If you get `ModuleNotFoundError`:

```bash
# check dependencies are installed
uv sync
```

## Tests Fail

Run with verbose output:

```bash
uv run pytest tests/ -vv
```

Common issues:

+ Missing MAVSDK port (needs simulator running)
+ Incorrect configuration parameters
+ Dependency version conflicts

## Git Push Rejected

Ensure your branch is up to date:

```bash
git fetch origin
git rebase origin/master
git push origin feature/my-mission
```
