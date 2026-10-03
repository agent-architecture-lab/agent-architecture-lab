---
type: configuration
subject: GitHub issue tracker
created: 2026-10-03
updated: 2026-10-03
author: jihyun
tags: [github, issues, agent-skills]
related: []
---

# Issue tracker: GitHub

이 레포의 이슈와 스펙은 GitHub Issues에서 관리한다. 모든 작업은 레포 루트에서 `gh` CLI로 수행한다.

## Conventions

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open`
- Label: `gh issue edit <number> --add-label "..."`
- Close: `gh issue close <number> --comment "..."`

## Pull requests as a triage surface

PRs are not a request surface. 외부 PR을 기능 요청으로 triage하지 않는다.

## Skill mapping

- A skill that says “publish to the issue tracker” creates a GitHub issue.
- A skill that says “fetch the relevant ticket” runs `gh issue view <number> --comments`.
