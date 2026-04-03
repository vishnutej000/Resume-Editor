import re


REQUIRED_COMMANDS = [
    r'\begin{document}',
    r'\end{document}',
    r'\section{Summary}',
    r'\section{Experience}',
    r'\section{Projects}',
    r'\section{Skills}',
]

PROTECTED_MACROS = [
    r'\skillitem',
    r'\begin{highlights}',
    r'\end{highlights}',
]


def validate(latex: str) -> list[str]:
    issues = []

    for cmd in REQUIRED_COMMANDS:
        if cmd not in latex:
            issues.append(f"Missing required element: {cmd}")

    for macro in PROTECTED_MACROS:
        if macro not in latex:
            issues.append(f"Protected macro was removed: {macro}")

    open_braces = latex.count('{')
    close_braces = latex.count('}')
    if open_braces != close_braces:
        issues.append(f"Unmatched braces: {open_braces} open vs {close_braces} close")

    tokens = re.findall(r'\\(begin|end)\{([^}]+)\}', latex)
    stack = []
    env_mismatch = False
    for kind, env in tokens:
        if kind == 'begin':
            stack.append(env)
            continue
        if not stack or stack[-1] != env:
            env_mismatch = True
            break
        stack.pop()

    if env_mismatch or stack:
        issues.append("Mismatched \\begin/\\end environments")

    return issues


def is_safe(latex: str) -> bool:
    return len(validate(latex)) == 0
