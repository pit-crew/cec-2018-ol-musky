"""Rejection of a command that breaks a rule."""


class Rejected(Exception):
    """A command broke a rule. The world that the command read is not changed."""

    def __init__(self, rule: str, detail: object = None) -> None:
        super().__init__(rule if detail is None else f"{rule}: {detail}")
        self.rule = rule
        self.detail = detail


def require(ok: object, rule: str, detail: object = None) -> None:
    if not ok:
        raise Rejected(rule, detail)
