"""
Content moderation service for user-generated content.
Uses keyword blocklist for immediate filtering.
All imports are logged for async admin review.
"""

import re
from typing import Tuple


class ContentModerationService:
    """
    Lightweight, synchronous keyword-based moderation.

    Designed to flag clearly harmful content (CSAM references, doxxing,
    real-world violence/terror instructions, suicide encouragement) without
    blocking general adult themes, dark fiction, or creative writing.

    The blocklist intentionally stays small and high-precision to avoid
    false positives on otome / romance / dark-fiction content typical of
    SillyTavern character cards.
    """

    # Each entry: (compiled_regex, human_readable_reason)
    # Patterns are case-insensitive; word boundaries used where appropriate
    # to avoid e.g. matching "assassinate" inside benign words.
    _BLOCKED_PATTERNS = [
        # ── Child sexual abuse material (CSAM) ─────────────────────────
        (
            re.compile(
                r"\b(?:lolic[oō]n|shotac[oō]n|pre[\s\-]?teen\s+(?:sex|nude|porn)|"
                r"child\s+(?:porn|sex|nude|rape)|cp\s+(?:material|content)|"
                r"underage\s+(?:porn|sex|nude)|kiddie\s+porn|"
                r"sex(?:ual)?\s+(?:with|abuse\s+of)\s+(?:a\s+)?(?:minor|child|kid|infant|toddler))\b",
                re.IGNORECASE,
            ),
            "sexual_content_involving_minors",
        ),
        (
            # Catch phrasings like "sexual content with a minor" / "sexual
            # acts involving children" where filler words separate the
            # sexual descriptor from the minor reference.
            re.compile(
                r"\bsex(?:ual)?\s+(?:\w+\s+){0,3}"
                r"(?:with|involving|of|upon|toward)\s+"
                r"(?:a\s+|the\s+|any\s+)?"
                r"(?:minor|minors|child|children|kid|kids|infant|infants|toddler|toddlers|underage\s+person|underage\s+people)\b",
                re.IGNORECASE,
            ),
            "sexual_content_involving_minors",
        ),
        # ── Detailed violence / terrorism instructions ─────────────────
        (
            re.compile(
                r"\bhow\s+to\s+(?:make|build|construct|assemble)\s+"
                r"(?:a\s+)?(?:bomb|pipe\s*bomb|ied|explosive\s+device|nerve\s+agent|"
                r"chemical\s+weapon|biological\s+weapon|dirty\s+bomb)\b",
                re.IGNORECASE,
            ),
            "weapon_construction_instructions",
        ),
        (
            re.compile(
                r"\b(?:instructions?|tutorial|guide|recipe)\s+(?:for|to)\s+"
                r"(?:making|synthesizing|producing)\s+"
                r"(?:methamphetamine|fentanyl|sarin|vx\s+gas|ricin|anthrax)\b",
                re.IGNORECASE,
            ),
            "illegal_substance_synthesis",
        ),
        (
            re.compile(
                r"\b(?:plan|plot|carry\s+out)\s+(?:a\s+)?"
                r"(?:mass\s+shooting|terror(?:ist)?\s+attack|school\s+shooting|"
                r"genocide|ethnic\s+cleansing)\b",
                re.IGNORECASE,
            ),
            "real_world_terrorism_planning",
        ),
        # ── Self-harm / suicide encouragement ──────────────────────────
        (
            re.compile(
                r"\b(?:you\s+should\s+(?:kill\s+yourself|commit\s+suicide|end\s+your\s+life)|"
                r"go\s+(?:kill\s+yourself|kys)|"
                r"best\s+way\s+to\s+(?:kill\s+yourself|commit\s+suicide)|"
                r"pro[\s\-]?ana\s+(?:tips|guide)|thinspo\s+(?:tips|methods))\b",
                re.IGNORECASE,
            ),
            "self_harm_encouragement",
        ),
        # ── Doxxing / real person harassment ───────────────────────────
        (
            re.compile(
                r"\b(?:dox(?:x)?(?:ing)?|leak(?:ing)?\s+(?:home\s+)?address|"
                r"swat(?:ting)?)\s+(?:of\s+|target(?:ing)?\s+|a\s+)?"
                r"(?:real\s+person|specific\s+person|celebrity|streamer|journalist)\b",
                re.IGNORECASE,
            ),
            "doxxing_or_harassment",
        ),
        (
            re.compile(
                r"\b(?:home\s+address|social\s+security\s+number|ssn|"
                r"credit\s+card\s+number)\s+(?:of|belonging\s+to)\s+"
                r"[A-Z][a-z]+\s+[A-Z][a-z]+\b",
                re.IGNORECASE,
            ),
            "personal_information_disclosure",
        ),
        # ── Non-consensual / human trafficking ─────────────────────────
        (
            re.compile(
                r"\b(?:human\s+trafficking|sex\s+trafficking|"
                r"sell(?:ing)?\s+(?:a\s+)?(?:child|minor|kid)\s+(?:for|into)\s+"
                r"(?:sex|slavery|labor))\b",
                re.IGNORECASE,
            ),
            "human_trafficking_content",
        ),
    ]

    async def check_text(
        self, text: str, user_id: int, db
    ) -> Tuple[bool, str]:
        """
        Check text content for harmful patterns.

        Returns:
            (is_safe, reason). ``reason`` is an empty string when ``is_safe``
            is True; otherwise a short machine-readable category describing
            the violation (e.g. ``"self_harm_encouragement"``).
        """
        if not text:
            return True, ""

        # Normalize: collapse whitespace so split-line patterns still match.
        normalized = re.sub(r"\s+", " ", text).strip()

        for pattern, reason in self._BLOCKED_PATTERNS:
            if pattern.search(normalized):
                return False, reason

        return True, ""

    async def log_moderation(
        self,
        db,
        content_type: str,
        content_id: int,
        user_id: int,
        ai_id: int,
        action: str,
        reason: str = "",
    ) -> None:
        """
        Log a moderation decision to ``content_moderation_logs``.

        ``reviewer_id`` is left at the column default (0) to indicate an
        automated review; an admin can later overwrite it when they audit
        the entry.
        """
        from models.content_moderation_log import ContentModerationLog

        log = ContentModerationLog(
            content_type=content_type,
            content_id=content_id or 0,
            user_id=user_id or 0,
            ai_id=ai_id or 0,
            reason=reason or "",
            action_taken=action,
            reviewer_id=0,  # 0 = automated review (no human reviewer yet)
        )
        db.add(log)
