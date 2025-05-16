# pcd-maas

## CI

This repo uses the Autotagger GitHub Action to automatically tag releases based on commit messages. The action is configured to run on every push to the main branch and will create a new release if there are any new commits since the last release.

Use `#major`, `#minor`, or `#patch` tags in your commit messages and autotagger will increase your version tags accordingly.

The repo also uses copilot to automatically lint and suggest changes to the code in all commits. The action is configured to run on every push to the main branch and will auto run on all PRs.
