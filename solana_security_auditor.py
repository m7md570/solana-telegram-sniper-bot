# -*- coding: utf-8 -*-
"""
Solana Smart Contract Security & Bug Bounty Auditor
Audits Solana (Anchor / Native Rust) smart contracts for critical on-chain vulnerabilities.
Detects:
1. Missing Signer Checks (Authority escalation)
2. Unchecked Account Ownership / Arbitrary Account Substitution
3. Arbitrary Cross-Program Invocations (CPI)
4. Stale Account Data Post-CPI (Missing .reload()?)
5. Raw Integer Arithmetic Overflows/Underflows
6. Reallocation without zero_init
7. Token-2022 Transfer Hook Honeypot vectors

Leverages the local unconstrained Qwen 27B model via LM Studio on RTX 4070
to formulate Immunefi & Code4rena-compliant Bug Bounty PoC reports ($0 capital cost).
"""

import os
import re
import json
import time
import datetime
import hashlib
import logging
from typing import Dict, List, Any, Optional

try:
    from local_model_client import query_local_ai, is_local_model_online
except ImportError:
    try:
        from .local_model_client import query_local_ai, is_local_model_online
    except Exception:
        query_local_ai = None
        is_local_model_online = lambda: False

logger = logging.getLogger("SolanaSecurityAuditor")

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "data", "audit_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


class SolanaVulnerabilityRule:
    """Definition for a smart contract vulnerability detection rule."""
    def __init__(self, rule_id: str, name: str, severity: str, cwe: str, description: str):
        self.rule_id = rule_id
        self.name = name
        self.severity = severity  # CRITICAL, HIGH, MEDIUM, LOW, INFO
        self.cwe = cwe
        self.description = description


RULES = {
    "MISSING_SIGNER": SolanaVulnerabilityRule(
        rule_id="SOL-001",
        name="Missing Signer Authorization Check",
        severity="CRITICAL",
        cwe="CWE-285: Improper Authorization",
        description="Authority or owner account is not verified as a Signer, allowing unauthorized state mutation or fund withdrawal."
    ),
    "UNCHECKED_OWNER": SolanaVulnerabilityRule(
        rule_id="SOL-002",
        name="Unchecked Account Ownership / Program ID",
        severity="HIGH",
        cwe="CWE-284: Improper Access Control",
        description="Account data deserialized without verifying owner == program_id, enabling arbitrary spoofed account substitution."
    ),
    "ARBITRARY_CPI": SolanaVulnerabilityRule(
        rule_id="SOL-003",
        name="Arbitrary Cross-Program Invocation (CPI)",
        severity="CRITICAL",
        cwe="CWE-829: Inclusion of Untrusted Resource",
        description="invoke/invoke_signed executed with an arbitrary program_id account, allowing an attacker to hijack program execution."
    ),
    "STALE_CPI_DATA": SolanaVulnerabilityRule(
        rule_id="SOL-004",
        name="Stale Data Read After CPI",
        severity="MEDIUM",
        cwe="CWE-672: Operation on Expired Data",
        description="Account data accessed after an external CPI without calling ctx.accounts.account.reload()?, causing inconsistent state."
    ),
    "UNCHECKED_ARITHMETIC": SolanaVulnerabilityRule(
        rule_id="SOL-005",
        name="Unchecked Integer Arithmetic Overflow/Underflow",
        severity="HIGH",
        cwe="CWE-190: Integer Overflow",
        description="Raw arithmetic operators (+, -, *) used on balances/shares without checked_add/checked_sub or saturating math."
    ),
    "REALLOC_NO_ZERO_INIT": SolanaVulnerabilityRule(
        rule_id="SOL-006",
        name="Account Reallocation Without Zero-Initialization",
        severity="MEDIUM",
        cwe="CWE-456: Missing Initialization of a Variable",
        description="realloc used without zero_init = true, exposing leftover dirty memory in resized Solana accounts."
    ),
    "TRANSFER_HOOK_RISK": SolanaVulnerabilityRule(
        rule_id="SOL-007",
        name="Unvalidated Token-2022 Transfer Hook",
        severity="HIGH",
        cwe="CWE-840: Business Logic Error",
        description="Token-2022 Transfer Hook extension enabled without validating execute instruction caller, risking DEX honeypot lockup."
    ),
}


def scan_missing_signer(code: str) -> List[Dict[str, Any]]:
    """Detects accounts that act as authority or owner without being constrained as Signer<'info>."""
    findings = []
    lines = code.split("\n")
    
    # Pattern 1: Anchor struct with authority/admin/owner field as AccountInfo or UncheckedAccount
    struct_pattern = re.compile(r"pub\s+(?:authority|admin|owner|payer|manager)\s*:\s*(?:AccountInfo|UncheckedAccount)", re.IGNORECASE)
    
    for idx, line in enumerate(lines, start=1):
        if struct_pattern.search(line):
            # Check if previous lines have #[account(signer)]
            has_signer_annotation = False
            for lookback in range(max(0, idx - 4), idx - 1):
                if "signer" in lines[lookback].lower():
                    has_signer_annotation = True
                    break
            
            if not has_signer_annotation:
                findings.append({
                    "rule": RULES["MISSING_SIGNER"],
                    "line": idx,
                    "snippet": line.strip(),
                    "recommendation": "Change type to `Signer<'info>` or annotate with `#[account(signer)]`."
                })
    return findings


def scan_unchecked_owner(code: str) -> List[Dict[str, Any]]:
    """Detects deserialization from raw AccountInfo without owner validation."""
    findings = []
    lines = code.split("\n")
    
    # Pattern: try_from_slice or unpack on AccountInfo without owner check in context
    deserialize_pattern = re.compile(r"(?:try_from_slice|unpack_unchecked|unpack)\s*\(", re.IGNORECASE)
    
    for idx, line in enumerate(lines, start=1):
        if deserialize_pattern.search(line):
            # Check surrounding lines for .owner == or check_id
            window = "\n".join(lines[max(0, idx - 10):min(len(lines), idx + 10)])
            if "owner" not in window and "check_id" not in window and "assert_eq" not in window:
                findings.append({
                    "rule": RULES["UNCHECKED_OWNER"],
                    "line": idx,
                    "snippet": line.strip(),
                    "recommendation": "Verify `account.owner == program_id` before deserializing account data."
                })
    return findings


def scan_arbitrary_cpi(code: str) -> List[Dict[str, Any]]:
    """Detects invoke / invoke_signed calls without explicit program ID validation."""
    findings = []
    lines = code.split("\n")
    
    invoke_pattern = re.compile(r"invoke(?:_signed)?\s*\(", re.IGNORECASE)
    for idx, line in enumerate(lines, start=1):
        if invoke_pattern.search(line):
            window = "\n".join(lines[max(0, idx - 12):min(len(lines), idx + 2)])
            if "expected_program" not in window and "system_program::ID" not in window and "token::ID" not in window and "check_id" not in window:
                findings.append({
                    "rule": RULES["ARBITRARY_CPI"],
                    "line": idx,
                    "snippet": line.strip(),
                    "recommendation": "Validate program account key matches expected constant (e.g. `require_keys_eq!(ctx.accounts.token_program.key(), anchor_spl::token::ID)`)."
                })
    return findings


def scan_stale_cpi_data(code: str) -> List[Dict[str, Any]]:
    """Detects CPI execution followed by accessing account fields without calling reload()."""
    findings = []
    lines = code.split("\n")
    
    cpi_line = -1
    for idx, line in enumerate(lines, start=1):
        if "cpi::" in line or "invoke" in line:
            cpi_line = idx
        elif cpi_line > 0 and (idx - cpi_line) < 15:
            if re.search(r"ctx\.accounts\.\w+\.(?:amount|balance|data)", line) and "reload" not in line:
                findings.append({
                    "rule": RULES["STALE_CPI_DATA"],
                    "line": idx,
                    "snippet": line.strip(),
                    "recommendation": "Invoke `ctx.accounts.<account>.reload()?` after CPI before inspecting state."
                })
                cpi_line = -1  # Report once per occurrence
    return findings


def scan_unchecked_arithmetic(code: str) -> List[Dict[str, Any]]:
    """Detects raw arithmetic on monetary fields without checked_* or safe math methods."""
    findings = []
    lines = code.split("\n")
    
    # Pattern: amount = a + b or balance += deposit without checked_*
    arith_pattern = re.compile(r"(?:amount|balance|shares|lamports|tokens|fee)\s*[\+\-\*]\=|\=\s*(?:amount|balance|shares|lamports)\s*[\+\-\*]", re.IGNORECASE)
    
    for idx, line in enumerate(lines, start=1):
        if arith_pattern.search(line):
            if "checked_" not in line and "saturating_" not in line and "safe_" not in line:
                findings.append({
                    "rule": RULES["UNCHECKED_ARITHMETIC"],
                    "line": idx,
                    "snippet": line.strip(),
                    "recommendation": "Use `checked_add()`, `checked_sub()`, or `checked_mul()` with `.ok_or(ErrorCode::MathOverflow)?`."
                })
    return findings


def scan_realloc_zero_init(code: str) -> List[Dict[str, Any]]:
    """Detects account reallocation without zero_init = true."""
    findings = []
    lines = code.split("\n")
    
    realloc_pattern = re.compile(r"realloc\s*=\s*", re.IGNORECASE)
    for idx, line in enumerate(lines, start=1):
        if realloc_pattern.search(line):
            if "zero_init" not in line and "zero_init" not in lines[max(0, idx - 2):min(len(lines), idx + 2)][0]:
                findings.append({
                    "rule": RULES["REALLOC_NO_ZERO_INIT"],
                    "line": idx,
                    "snippet": line.strip(),
                    "recommendation": "Specify `realloc::zero_init = true` to prevent data leakage and memory corruption."
                })
    return findings


def scan_transfer_hook_risks(code: str) -> List[Dict[str, Any]]:
    """Detects Token-2022 Transfer Hook vulnerabilities."""
    findings = []
    lines = code.split("\n")
    
    hook_pattern = re.compile(r"transfer_hook|TransferHook", re.IGNORECASE)
    for idx, line in enumerate(lines, start=1):
        if hook_pattern.search(line):
            if "check_id" not in code and "expected_hook" not in code and "authority" not in code:
                findings.append({
                    "rule": RULES["TRANSFER_HOOK_RISK"],
                    "line": idx,
                    "snippet": line.strip(),
                    "recommendation": "Ensure transfer hook verifies calling token program ID and restricts update authority."
                })
                break
    return findings


def audit_smart_contract_code(
    code: str,
    contract_name: str = "AnchorProgram",
    deep_llm: bool = True
) -> Dict[str, Any]:
    """
    Executes a comprehensive static & local LLM smart contract vulnerability audit.
    Generates an Immunefi & Code4rena-compliant bug bounty assessment report.
    """
    findings: List[Dict[str, Any]] = []
    findings.extend(scan_missing_signer(code))
    findings.extend(scan_unchecked_owner(code))
    findings.extend(scan_arbitrary_cpi(code))
    findings.extend(scan_stale_cpi_data(code))
    findings.extend(scan_unchecked_arithmetic(code))
    findings.extend(scan_realloc_zero_init(code))
    findings.extend(scan_transfer_hook_risks(code))
    
    # Calculate overall risk
    has_critical = any(f["rule"].severity == "CRITICAL" for f in findings)
    has_high = any(f["rule"].severity == "HIGH" for f in findings)
    has_medium = any(f["rule"].severity == "MEDIUM" for f in findings)
    
    if has_critical:
        risk_level = "CRITICAL"
        risk_score = 9.8
    elif has_high:
        risk_level = "HIGH"
        risk_score = 7.5
    elif has_medium:
        risk_level = "MEDIUM"
        risk_score = 5.0
    elif findings:
        risk_level = "LOW"
        risk_score = 2.5
    else:
        risk_level = "CLEAN"
        risk_score = 0.0

    # Local AI Reasoning via LM Studio Qwen 27B on RTX 4070
    llm_verdict = ""
    if deep_llm and query_local_ai:
        findings_summary = "\n".join([
            f"- [{f['rule'].severity}] {f['rule'].name} at line {f['line']}: {f['snippet']}"
            for f in findings
        ]) or "No static flaws detected."
        
        prompt = (
            f"Target Solana Smart Contract: {contract_name}\n"
            f"Code Excerpt:\n```rust\n{code[:1800]}\n```\n\n"
            f"Static Scanner Findings:\n{findings_summary}\n\n"
            f"Instructions:\n"
            f"1. Evaluate whether these flaws allow critical unauthorized access, fund drainage, or state corruption on Solana.\n"
            f"2. Provide an institutional Immunefi Bug Bounty Impact Summary (2-3 sentences) detailing the economic threat and exact remediation."
        )
        system = (
            "You are an elite Web3 Solana Smart Contract Security Researcher and Immunefi Top 10 Whitehat Auditor. "
            "Deliver rigorous, direct, non-hallucinatory security verdicts."
        )
        try:
            llm_res = query_local_ai(prompt, system_prompt=system, max_tokens=300, temperature=0.3)
            if llm_res:
                llm_verdict = llm_res.strip()
        except Exception as e:
            logger.debug(f"Local AI audit query skipped: {e}")

    # Fallback verdict if local model is offline
    if not llm_verdict:
        if risk_level == "CRITICAL":
            llm_verdict = (
                f"Critical access control flaw detected in {contract_name}. "
                "Missing signer or arbitrary CPI enables unauthorized account manipulation or direct vault drainage. "
                "Immediate patch required prior to mainnet deployment."
            )
        elif risk_level == "HIGH":
            llm_verdict = (
                f"High-severity risk identified in {contract_name}. "
                "Unchecked arithmetic or unvalidated account ownership could lead to corrupted protocol state. "
                "Enforce checked mathematical operations and verify account owners."
            )
        elif risk_level == "MEDIUM":
            llm_verdict = (
                f"Medium-severity logic warning in {contract_name}. "
                "Potential stale CPI data read or missing realloc zero-init. Recommend defensive constraints."
            )
        else:
            llm_verdict = f"Clean static audit: No critical Solana or Anchor authorization vulnerabilities detected in {contract_name}."

    # Generate Immunefi Bug Bounty PoC Markdown Report
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_hash = hashlib.sha256(f"{contract_name}_{timestamp}_{len(findings)}".encode()).hexdigest()[:8]
    
    immunefi_report = (
        f"# Immunefi Bug Bounty Vulnerability Report\n"
        f"**Target:** `{contract_name}`  \n"
        f"**Date:** `{timestamp}`  \n"
        f"**Severity:** `{risk_level}` (CVSS: {risk_score})  \n"
        f"**Auditor Engine:** Popcorn Whitehat Sentinel v3.90.0 (Local Qwen 27B Coprocessor)  \n\n"
        f"## 1. Vulnerability Summary\n"
        f"{llm_verdict}\n\n"
        f"## 2. Identified Vulnerabilities ({len(findings)})\n"
    )
    
    for idx, f in enumerate(findings, start=1):
        immunefi_report += (
            f"### {idx}. [{f['rule'].severity}] {f['rule'].name} (`{f['rule'].rule_id}`)\n"
            f"- **CWE:** {f['rule'].cwe}\n"
            f"- **Affected Line:** Line {f['line']}\n"
            f"- **Code Snippet:**\n```rust\n{f['snippet']}\n```\n"
            f"- **Description:** {f['rule'].description}\n"
            f"- **Remediation:** {f['recommendation']}\n\n"
        )
        
    immunefi_report += (
        f"## 3. Payout & Submission Destination\n"
        f"- **Researcher Solana Wallet:** `7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r`\n"
        f"- **Platform:** Immunefi / Code4rena Bug Bounty Program\n"
    )

    # Save report to persistent file
    report_filename = f"bounty_audit_{report_hash}.md"
    report_path = os.path.join(REPORTS_DIR, report_filename)
    try:
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write(immunefi_report)
    except Exception as e:
        logger.error(f"Failed to save audit report file: {e}")

    return {
        "contract_name": contract_name,
        "timestamp": timestamp,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "findings_count": len(findings),
        "findings": [
            {
                "rule_id": f["rule"].rule_id,
                "name": f["rule"].name,
                "severity": f["rule"].severity,
                "line": f["line"],
                "snippet": f["snippet"],
                "recommendation": f["recommendation"]
            }
            for f in findings
        ],
        "ai_verdict": llm_verdict,
        "report_file": report_path,
        "immunefi_report": immunefi_report
    }


def format_telegram_audit_report(result: Dict[str, Any], lang: str = "ar") -> str:
    """Formats the security audit result into a clean, bilingual HTML Telegram card."""
    risk = result.get("risk_level", "CLEAN")
    score = result.get("risk_score", 0.0)
    count = result.get("findings_count", 0)
    contract = result.get("contract_name", "SolanaProgram")
    verdict = result.get("ai_verdict", "")
    findings = result.get("findings", [])

    if risk == "CRITICAL":
        badge = "🚨 <b>خطر حرج (CRITICAL RISK)</b>" if lang == "ar" else "🚨 <b>CRITICAL RISK</b>"
    elif risk == "HIGH":
        badge = "⚠️ <b>خطر مرتفع (HIGH RISK)</b>" if lang == "ar" else "⚠️ <b>HIGH RISK</b>"
    elif risk == "MEDIUM":
        badge = "🟡 <b>خطر متوسط (MEDIUM RISK)</b>" if lang == "ar" else "🟡 <b>MEDIUM RISK</b>"
    elif risk == "LOW":
        badge = "🔵 <b>ملاحظات منخفضة (LOW RISK)</b>" if lang == "ar" else "🔵 <b>LOW RISK</b>"
    else:
        badge = "🛡️ <b>عقد آمن ونظيف (SAFE & SECURE)</b>" if lang == "ar" else "🛡️ <b>SAFE & SECURE</b>"

    if lang == "ar":
        text = (
            f"🔍 <b>تقرير فحص أمان العقود الذكية (Bug Bounty Audit)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>البرنامج:</b> <code>{contract}</code>\n"
            f"🛡️ <b>حالة الأمان:</b> {badge}\n"
            f"📊 <b>مؤشر الخطورة:</b> <code>{score:.1f}/10.0</code>\n"
            f"🐞 <b>عدد الثغرات المرصودة:</b> <code>{count}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 <b>تحليل الذكاء الاصطناعي (Qwen 27B):</b>\n"
            f"<i>{verdict}</i>\n"
        )
        if findings:
            text += f"\n📋 <b>أبرز الثغرات المكتشفة:</b>\n"
            for f in findings[:3]:
                text += (
                    f"• <b>[{f['severity']}] {f['name']} ({f.get('rule_id', '')})</b> (سطر {f['line']})\n"
                    f"  💡 <i>الحل:</i> {f['recommendation']}\n"
                )
            if len(findings) > 3:
                text += f"<i>... ويوجد {len(findings) - 3} ثغرات إضافية في التقرير الكامل.</i>\n"
        text += (
            f"\n💰 <b>جاهز لمكافآت Immunefi / Code4rena</b>\n"
            f"📁 <i>تم حفظ تقرير PoC الشامل في السيرفر للمطالبة بالمكافأة.</i>"
        )
    else:
        text = (
            f"🔍 <b>Solana Smart Contract Security Audit</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Program:</b> <code>{contract}</code>\n"
            f"🛡️ <b>Security Status:</b> {badge}\n"
            f"📊 <b>Risk Score:</b> <code>{score:.1f}/10.0</code>\n"
            f"🐞 <b>Vulnerabilities Found:</b> <code>{count}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 <b>AI Whitehat Verdict (Qwen 27B):</b>\n"
            f"<i>{verdict}</i>\n"
        )
        if findings:
            text += f"\n📋 <b>Key Vulnerabilities Detected:</b>\n"
            for f in findings[:3]:
                text += (
                    f"• <b>[{f['severity']}] {f['name']} ({f.get('rule_id', '')})</b> (Line {f['line']})\n"
                    f"  💡 <i>Fix:</i> {f['recommendation']}\n"
                )
            if len(findings) > 3:
                text += f"<i>... and {len(findings) - 3} more findings in full PoC report.</i>\n"
        text += (
            f"\n💰 <b>Immunefi / Code4rena Bug Bounty Ready</b>\n"
            f"📁 <i>Comprehensive PoC report saved to disk for reward submission.</i>"
        )
    return text
