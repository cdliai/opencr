import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum


class ValidationStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"  # Suspicious but usable
    FAIL = "fail"  # Should be re-extracted or flagged
    EMPTY = "empty"  # Page produced no text


@dataclass
class ValidationResult:
    status: ValidationStatus
    issues: list[str]
    metrics: dict  # repetition_ratio, unique_line_ratio, etc.


class OutputValidator:
    """
    Validates OCR output for known failure patterns.
    Runs AFTER every page extraction.
    """

    # Thresholds — tune based on your corpus
    MAX_REPETITION_RATIO = 0.35  # If >35% of lines are duplicates -> WARN
    MAX_REPETITION_RATIO_FAIL = 0.60  # If >60% -> FAIL
    MIN_UNIQUE_CHARS = 10  # Minimum unique characters for non-empty
    MAX_SINGLE_CHAR_RATIO = 0.50  # If >50% of text is one character -> FAIL
    MIN_TEXT_LENGTH = 20  # Below this = probably blank page
    MAX_CONSECUTIVE_DUPES = 5  # 5+ identical consecutive lines = WARN

    def validate(self, text: str, page_num: int) -> ValidationResult:
        issues: list[str] = []
        metrics: dict = {}

        # Check 1: Empty / near-empty output
        stripped = text.strip()
        if len(stripped) < self.MIN_TEXT_LENGTH:
            return ValidationResult(
                status=ValidationStatus.EMPTY,
                issues=[f"Page {page_num}: output too short ({len(stripped)} chars)"],
                metrics={"text_length": len(stripped)},
            )

        # Check 2: Line-level repetition
        lines = [l.strip() for l in stripped.split("\n") if l.strip()]
        single_char_ratio = 0.0

        if lines:
            unique_lines = set(lines)
            repetition_ratio = 1 - (len(unique_lines) / len(lines))
            metrics["repetition_ratio"] = round(repetition_ratio, 3)
            metrics["total_lines"] = len(lines)
            metrics["unique_lines"] = len(unique_lines)

            if repetition_ratio > self.MAX_REPETITION_RATIO_FAIL:
                issues.append(
                    f"Page {page_num}: extreme repetition "
                    f"({repetition_ratio:.0%} duplicate lines)"
                )
            elif repetition_ratio > self.MAX_REPETITION_RATIO:
                issues.append(
                    f"Page {page_num}: moderate repetition "
                    f"({repetition_ratio:.0%} duplicate lines)"
                )

        # Check 3: Consecutive duplicate lines
        if lines:
            max_consec = 1
            current_consec = 1
            for i in range(1, len(lines)):
                if lines[i] == lines[i - 1]:
                    current_consec += 1
                    max_consec = max(max_consec, current_consec)
                else:
                    current_consec = 1

            metrics["max_consecutive_dupes"] = max_consec
            if max_consec >= self.MAX_CONSECUTIVE_DUPES:
                issues.append(
                    f"Page {page_num}: {max_consec} consecutive identical lines"
                )

        # Check 4: Character diversity (catches garbled output)
        char_counts = Counter(stripped.replace(" ", "").replace("\n", ""))
        if char_counts:
            most_common_char, most_common_count = char_counts.most_common(1)[0]
            total_chars = sum(char_counts.values())
            single_char_ratio = most_common_count / total_chars
            metrics["dominant_char"] = most_common_char
            metrics["dominant_char_ratio"] = round(single_char_ratio, 3)

            if single_char_ratio > self.MAX_SINGLE_CHAR_RATIO:
                issues.append(
                    f"Page {page_num}: '{most_common_char}' is "
                    f"{single_char_ratio:.0%} of output"
                )

        # Check 5: Model artifact detection
        artifact_patterns = [
            r"(<\|det\|>){3,}",  # Repeated detection tokens
            r"(<\|grounding\|>){2,}",  # Repeated grounding tokens
            r"(\S+\s*){1}\1{10,}",  # Same word 10+ times
        ]
        for pattern in artifact_patterns:
            if re.search(pattern, stripped):
                issues.append(f"Page {page_num}: model artifact detected")
                break

        # Determine overall status
        if any("extreme repetition" in i or "model artifact" in i for i in issues):
            status = ValidationStatus.FAIL
        elif single_char_ratio > self.MAX_SINGLE_CHAR_RATIO:
            status = ValidationStatus.FAIL
        elif issues:
            status = ValidationStatus.WARN
        else:
            status = ValidationStatus.PASS

        metrics["text_length"] = len(stripped)
        return ValidationResult(status=status, issues=issues, metrics=metrics)
