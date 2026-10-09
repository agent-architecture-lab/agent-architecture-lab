---
type: runbook
subject: community operations agent dev deployment
created: 2026-10-03
updated: 2026-10-09
author: jihyun
tags: [aws, discord, deployment]
related: [docs/superpowers/specs/2026-10-03-001-agent-architecture-lab-design.md]
---

# Dev deployment runbook

## Account owner steps

1. Create a Discord application and copy its application ID and public key.
2. Create the OpenAI API key secret in AWS Secrets Manager. Do not put its value in a file or command history.
3. Choose the email address that receives the 5, 8, and 10 USD monthly AWS budget alerts.
4. Deploy only the dev stack:

```bash
sam deploy --region ap-northeast-2 --template-file infra/template.yaml --stack-name community-ops-dev --capabilities CAPABILITY_IAM --parameter-overrides Environment=dev OpenAISecretArn=SECRET_ARN DiscordApplicationId=APPLICATION_ID DiscordPublicKey=PUBLIC_KEY BudgetAlertEmail=ALERT_EMAIL
```

5. Copy the current `DiscordInteractionEndpoint` output into the Discord application interaction endpoint setting. Confirm that it is the `community-ops-dev` output, not an earlier endpoint.
6. Register only the `aal-test` slash command, then run it with synthetic input.
7. Confirm Discord immediately shows a deferred response, then locate the same `run_id` in ingress and dispatch Lambda logs. Do not copy interaction tokens or request bodies into notes.
8. Confirm one Standard Step Functions execution starts for that `run_id` and the Discord result Lambda PATCHes the original deferred response.
9. Repeat the identical dispatch payload only in a controlled dev test. Confirm the duplicate converges on the existing execution rather than starting a second workflow.
10. Inspect the benchmark JSONL record and benchmark-gate JSON evidence before changing a prompt, model, RAG, context, or Reflection default. Do not send real personal data.

Do not deploy prod, change IAM outside this stack, or delete resources as part of this runbook.
