from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_PROMPT_TEMPLATE = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
PROMPT_TEMPLATES: dict[str, str] = {
    "v1": DEFAULT_PROMPT_TEMPLATE,
    "v2": (
        "Feature={{feature}}\n"
        "Instruction=Answer only from the supplied documents; say when evidence is missing.\n"
        "Docs={{docs}}\n"
        "Question={{message}}"
    ),
}
DEFAULT_VERSION_BY_LABEL = {"production": "v1", "canary": "v2"}


@dataclass(frozen=True)
class ResolvedPrompt:
    text: str
    name: str
    label: str
    version: str
    source: str = "local"


def _compile_prompt(
    template: str, *, feature: str, docs: list[str], message: str
) -> str:
    return (
        template.replace("{{feature}}", feature)
        .replace("{{docs}}", "\n".join(docs))
        .replace("{{message}}", message)
    )


def resolve_prompt(
    *,
    feature: str,
    docs: list[str],
    message: str,
    name: str | None = None,
    label: str | None = None,
    version: str | None = None,
) -> ResolvedPrompt:
    resolved_name = name or os.getenv("PROMPT_NAME", "day13-chat")
    resolved_label = label or os.getenv("PROMPT_LABEL", "production")
    expected_version = DEFAULT_VERSION_BY_LABEL.get(resolved_label)
    if expected_version is None:
        supported = ", ".join(sorted(DEFAULT_VERSION_BY_LABEL))
        raise ValueError(
            f"Unsupported prompt label: {resolved_label}. Supported labels: {supported}"
        )

    resolved_version = version or os.getenv("PROMPT_VERSION") or expected_version

    template = PROMPT_TEMPLATES.get(resolved_version)
    if template is None:
        supported = ", ".join(sorted(PROMPT_TEMPLATES))
        raise ValueError(
            f"Unsupported prompt version: {resolved_version}. Supported versions: {supported}"
        )
    if resolved_version != expected_version:
        raise ValueError(
            "Prompt label/version mismatch: "
            f"label {resolved_label!r} resolves to {expected_version!r}, "
            f"got {resolved_version!r}"
        )

    return ResolvedPrompt(
        text=_compile_prompt(
            template, feature=feature, docs=docs, message=message
        ),
        name=resolved_name,
        label=resolved_label,
        version=resolved_version,
    )
