import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from agents import Agent, Runner


sys.stdout.reconfigure(encoding="utf-8")


MAX_PLAN_CHARS = 120_000


def read_plan_file(plan_file: Path) -> str:
    if not plan_file.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_file}")

    content = plan_file.read_text(encoding="utf-8", errors="replace")

    if len(content) > MAX_PLAN_CHARS:
        truncated = content[:MAX_PLAN_CHARS]
        return (
            truncated
            + "\n\n[PLAN TRUNCATED]\n"
            + f"The plan was longer than {MAX_PLAN_CHARS} characters. "
            + "Only the first section was reviewed."
        )

    return content


def redact_obvious_secrets(text: str) -> str:
    """
    Best-effort local redaction before sending plan text to the model.
    This is not a substitute for proper secret management.
    """

    patterns = [
        (r"(?i)(client_secret\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
        (r"(?i)(password\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
        (r"(?i)(secret\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
        (r"(?i)(access_key\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
        (r"(?i)(primary_access_key\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
        (r"(?i)(connection_string\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
    ]

    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)

    return redacted


def build_prompt(plan_text: str) -> str:
    return f"""
Review the following Terraform plan output.

You are reviewing the plan in the context of an Azure DevOps pipeline for Azure cloud infrastructure.

Focus on risk, not style.

Identify:
- Destroy actions
- Replacement actions
- Force replacement
- Changes to public exposure
- Changes to network security groups
- Changes to Azure Firewall, route tables, private endpoints, DNS or public IPs
- Changes to managed identities, role assignments, Key Vault access, secrets or RBAC
- Changes to storage accounts, databases, disks, backup, retention or data protection
- Changes to AKS, App Gateway, WAF, Log Analytics, diagnostics or monitoring
- Any sign that logging, diagnostics, policy, backup or security posture is weakened

Return a markdown report with this exact structure:

# Terraform Plan AI Review

## Overall Risk
Low, Medium, High, or Critical

## Approval Recommendation
One of:
- Safe to proceed
- Proceed with caution
- Manual review recommended
- Do not apply until reviewed

## Summary
Short summary of the plan and the main risks.

## Action Summary
Summarise creates, updates, deletes and replacements if visible.

## High-Risk Findings
List high-risk findings. If none, say "None identified."

## Medium-Risk Findings
List medium-risk findings. If none, say "None identified."

## Low-Risk Observations
List low-risk observations. If none, say "None identified."

## Security and Governance Notes
Mention security, compliance, monitoring, diagnostic, RBAC, identity or data protection concerns.

## Recommended Next Steps
Clear practical steps for the engineer/reviewer.

Rules:
- Do not invent resource names that are not in the plan.
- If the plan is truncated, say so.
- If there is not enough information, say so.
- Do not recommend automatic apply for risky changes.
- Use plain ASCII only.
- Keep the report concise but useful.

Terraform plan output:

```text
{plan_text}
```
"""


def determine_exit_code(report: str, fail_on_high_risk: bool) -> int:
    if not fail_on_high_risk:
        return 0

    report_lower = report.lower()

    critical = "## overall risk" in report_lower and "critical" in report_lower
    high = "## overall risk" in report_lower and "high" in report_lower

    if critical or high:
        return 1

    return 0


async def run_review(plan_file: Path, output_file: Path, fail_on_high_risk: bool) -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable is not set.", file=sys.stderr)
        return 2

    plan_text = read_plan_file(plan_file)
    plan_text = redact_obvious_secrets(plan_text)

    agent = Agent(
        name="Terraform Plan Risk Reviewer",
        instructions="""
        You are a senior cloud platform engineer reviewing Terraform plan output.
        You specialise in Azure, Azure DevOps, Terraform, landing zones, networking,
        identity, governance, monitoring and operational risk.

        You are read-only. You do not modify infrastructure.
        Your job is to produce a clear markdown risk review for a human approver.
        Use plain ASCII only.
        """,
    )

    prompt = build_prompt(plan_text)
    result = await Runner.run(agent, prompt)

    report = result.final_output

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report, encoding="utf-8")

    print(report)

    return determine_exit_code(report, fail_on_high_risk)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review a Terraform plan text file and produce a markdown AI risk report."
    )

    parser.add_argument(
        "--plan-file",
        required=True,
        help="Path to terraform show -no-color output, for example plan.txt",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the markdown review report, for example plan-review.md",
    )

    parser.add_argument(
        "--fail-on-high-risk",
        action="store_true",
        help="Exit with code 1 if the report indicates High or Critical overall risk.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    plan_file = Path(args.plan_file)
    output_file = Path(args.output)

    return asyncio.run(
        run_review(
            plan_file=plan_file,
            output_file=output_file,
            fail_on_high_risk=args.fail_on_high_risk,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
