# pcd-maas

## CI

This repo uses the Autotagger GitHub Action to automatically tag releases based on commit messages. The action is configured to run on every push to the main branch and will create a new release if there are any new commits since the last release.

This repo has branch protection enabled for the main branch. This means that all commits to the main branch must be made through a pull request. The pull request must be approved by at least one other person before it can be merged.

Use `#major`, `#minor`, or `#patch` tags in your commit messages and autotagger will increase your version tags accordingly.

The repo also uses copilot to automatically lint and suggest changes to the code in all commits. The action is configured to run on every push to the main branch and will auto run on all PRs.
