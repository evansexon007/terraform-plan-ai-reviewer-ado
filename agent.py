import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from agents import Agent, Runner


sys.stdout.reconfigure(encoding="utf-8")


MAX_PLAN_CHARS = 120_000


RISK_REVIEW_SCOPE = """
Review the entire Terraform plan. Do not limit the review to specific Azure resource types.

Assess every visible resource change for:
- Operational risk
- Security risk
- Governance risk
- Identity and access risk
- Network connectivity risk
- Public exposure risk
- Data loss risk
- Backup and retention risk
- Monitoring and diagnostics risk
- Cost, SKU or capacity impact
- Dependency or outage impact

Give additional attention to these high-impact change categories:

1. Destructive or disruptive changes
   - Resource deletion
   - Resource replacement
   - Force replacement
   - Data-bearing resources being removed
   - Changes likely to cause outage

2. Public exposure changes
   - Public IP creation or modification
   - Public network access enabled
   - Firewall or ACL changes that broaden access
   - 0.0.0.0/0, Internet, Any or wildcard source ranges

3. Network and connectivity changes
   - NSG rules
   - Azure Firewall rules
   - Route tables and UDRs
   - DNS zones and records
   - Private endpoints
   - Private DNS zone links
   - NAT gateways
   - Load balancers
   - Application Gateway listeners, probes, rules and backend pools
   - WAF policy changes

4. Identity and access changes
   - Managed identities
   - Role assignments
   - RBAC scope changes
   - Privileged roles
   - Service principals
   - Key Vault access policies or RBAC model changes

5. Data platform and storage changes
   - Storage accounts
   - Blob containers
   - Shared key access
   - Public blob access
   - SQL, PostgreSQL, MySQL, Cosmos DB or other databases
   - Managed disks
   - Backup vaults and Recovery Services vaults
   - Retention policies

6. Security posture changes
   - Key Vault public access
   - Purge protection
   - Soft delete retention
   - Defender or security settings
   - Encryption changes
   - TLS or HTTPS settings
   - Secrets or passwords in configuration

7. Observability and operations changes
   - Log Analytics workspaces
   - Diagnostic settings
   - Activity or audit logging
   - Application Insights
   - Alerts and action groups
   - Monitoring removed or weakened

8. Platform services
   - AKS clusters and node pools
   - App Service and Function Apps
   - Container Apps
   - API Management
   - Application Gateway
   - Azure Firewall
   - ACR
   - Event Grid
   - Service Bus
   - Automation accounts

9. Governance and management changes
   - Azure Policy assignments
   - Management locks
   - Tags used for ownership, environment, cost or lifecycle
   - Resource group or subscription-scope changes
   - Naming or location changes

10. Cost or capacity impact
   - SKU changes
   - Scaling changes
   - VM size changes
   - Node count changes
   - Premium service enablement
   - New always-on resources
"""


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
        (r"(?i)(administrator_login_password\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
        (r"(?i)(admin_password\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
        (r"(?i)(DATABASE_PASSWORD\s*=\s*)\"[^\"]+\"", r'\1"[REDACTED]"'),
    ]

    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)

    return redacted


def build_prompt(plan_text: str) -> str:
    prompt_parts = [
        "Review the following Terraform plan output.",
        "",
        "You are reviewing the plan in the context of an Azure DevOps pipeline for Azure cloud infrastructure.",
        "",
        "Focus on risk, not style.",
        "",
        RISK_REVIEW_SCOPE,
        "",
        "Return a markdown report with this exact structure:",
        "",
        "# Terraform Plan AI Review",
        "",
        "## Overall Risk",
        "Low, Medium, High, or Critical",
        "",
        "## Approval Recommendation",
        "One of:",
        "- Safe to proceed",
        "- Proceed with caution",
        "- Manual review recommended",
        "- Do not apply until reviewed",
        "",
        "## Summary",
        "Short summary of the plan and the main risks.",
        "",
        "## Action Summary",
        "Summarise creates, updates, deletes and replacements if visible.",
        "",
        "## High-Risk Findings",
        'List high-risk findings. If none, say "None identified."',
        "",
        "## Medium-Risk Findings",
        'List medium-risk findings. If none, say "None identified."',
        "",
        "## Low-Risk Observations",
        'List low-risk observations. If none, say "None identified."',
        "",
        "## Security and Governance Notes",
        "Mention security, compliance, monitoring, diagnostic, RBAC, identity or data protection concerns.",
        "",
        "## Recommended Next Steps",
        "Clear practical steps for the engineer/reviewer.",
        "",
        "Rules:",
        "- Review the full plan text, not only the highlighted risk categories.",
        "- Do not invent resource names that are not in the plan.",
        "- If the plan is truncated, say so.",
        "- If there is not enough information, say so.",
        "- Do not recommend automatic apply for risky changes.",
        "- Use plain ASCII only.",
        "- Keep the report concise but useful.",
        "- Treat destructive, public exposure, identity, network, Key Vault, database, storage, backup and monitoring changes as higher-risk unless clearly benign.",
        "",
        "Terraform plan output:",
        "",
        "```text",
        plan_text,
        "```",
    ]

    return "\n".join(prompt_parts)


def extract_overall_risk(report: str) -> str:
    """
    Extract the Overall Risk value from the markdown report.
    Expected values: Low, Medium, High, Critical.
    """

    match = re.search(
        r"## Overall Risk\s+([A-Za-z]+)",
        report,
        flags=re.IGNORECASE,
    )

    if not match:
        return "unknown"

    return match.group(1).strip().lower()


def determine_exit_code(report: str, fail_on_high_risk: bool) -> int:
    if not fail_on_high_risk:
        return 0

    overall_risk = extract_overall_risk(report)

    if overall_risk in ["high", "critical"]:
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
        identity, governance, monitoring, security and operational risk.

        You are read-only. You do not modify infrastructure.
        Your job is to produce a clear markdown risk review for a human approver.

        Review the complete Terraform plan provided by the user.
        Do not limit your review to specific Azure resource types.
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
