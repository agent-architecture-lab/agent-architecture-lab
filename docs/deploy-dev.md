---
type: runbook
subject: community operations agent dev deployment
created: 2026-10-03
updated: 2026-10-03
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
sam deploy --region us-east-1 --template-file infra/template.yaml --stack-name community-ops-dev --capabilities CAPABILITY_IAM --parameter-overrides Environment=dev OpenAISecretArn=SECRET_ARN DiscordApplicationId=APPLICATION_ID DiscordPublicKey=PUBLIC_KEY BudgetAlertEmail=ALERT_EMAIL
```

5. Copy the `DiscordInteractionEndpoint` output into the Discord application interaction endpoint setting.
6. Register a test slash command, then run one synthetic or anonymized command.
7. Inspect the Step Functions execution and the benchmark JSONL record. Do not send real personal data.

Do not deploy prod, change IAM outside this stack, or delete resources as part of this runbook.
