"""Learning Inbox pane: Skills / Rules / Allowlist proposals."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Label, Static, TabbedContent, TabPane


class _ProposalList(VerticalScroll):
    """Scrollable list of proposals."""

    DEFAULT_CSS = """
    _ProposalList {
        height: 1fr;
        padding: 0 1;
    }
    _ProposalList > .proposal-item {
        margin-bottom: 1;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """

    def show_items(self, items: list[dict[str, Any]]) -> None:
        self.remove_children()
        if not items:
            self.mount(Label("[dim]No proposals.[/dim]"))
            return
        for item in items:
            lines = "  ".join(f"{k}: {v}" for k, v in item.items() if k != "yaml")
            self.mount(Static(lines, classes="proposal-item"))


class LearningPane(Static):
    """Three-tab pane: Skills | Rules | Allowlist proposals."""

    DEFAULT_CSS = """
    LearningPane {
        height: 1fr;
        border: solid $accent;
    }
    """

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Skills", id="tab-skills"):
                yield _ProposalList(id="list-skills")
            with TabPane("Rules", id="tab-rules"):
                yield _ProposalList(id="list-rules")
            with TabPane("Allowlist", id="tab-allowlist"):
                yield _ProposalList(id="list-allowlist")

    def load_skills(self, items: list[dict[str, Any]]) -> None:
        self.query_one("#list-skills", _ProposalList).show_items(items)

    def load_rules(self, items: list[dict[str, Any]]) -> None:
        self.query_one("#list-rules", _ProposalList).show_items(items)

    def load_allowlist(self, items: list[dict[str, Any]]) -> None:
        self.query_one("#list-allowlist", _ProposalList).show_items(items)
