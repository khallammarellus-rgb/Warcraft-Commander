#!/usr/bin/env python3
"""Grok-style Textual TUI for campaign setup."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from campaign_tactician_opord import (
    TACTICIAN_OPORD_SECTIONS,
    is_tactician_opord_step,
)
from campaign_terminal_image import (
    HalfBlockImage,
    recommended_terminal_size,
    resize_terminal,
    try_load_halfblock_image,
)
from clipboard_utils import copy_to_system_clipboard, write_clipboard_fallback

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, ListItem, ListView, RichLog, Static, TextArea


@dataclass
class WizardStep:
    step_id: str
    phase: str
    title: str
    briefing: str
    kind: str  # choice | text | faction_menu | faction_pick | review_edit
    choices: list[tuple[str, str]] = field(default_factory=list)
    text_placeholder: str = ""
    text_multiline: bool = False
    text_skeleton: str = ""


class QuitConfirm(ModalScreen[bool]):
    DEFAULT_CSS = """
    QuitConfirm { align: center middle; }
    #quit-box {
        width: 50; height: auto;
        border: thick $error; background: $surface; padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-box"):
            yield Static("Quit setup without saving?")
            yield Static("y = quit   n = stay")

    def key_y(self) -> None:
        self.dismiss(True)

    def key_n(self) -> None:
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)


class FinalizeConfirm(ModalScreen[bool]):
    DEFAULT_CSS = """
    FinalizeConfirm { align: center middle; }
    #finalize-box {
        width: 60; height: auto;
        border: thick $success; background: $surface; padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="finalize-box"):
            yield Static("Finalize campaign setup?")
            yield Static("This writes your HQ, session, and campaign files.")
            yield Static("y = yes, write files   n = go back to review")

    def key_y(self) -> None:
        self.dismiss(True)

    def key_n(self) -> None:
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)


class CampaignSetupApp(App):
    CSS = """
    Screen { layout: vertical; }
    #header {
        height: 3; padding: 0 1;
        background: $primary-background; color: $text;
    }
    #body { height: 1fr; }
    #briefing-panel { width: 60%; border-right: solid $primary; }
    #choices-panel { width: 40%; }
    #crest-display {
        height: auto;
        max-height: 24;
        padding: 0 1;
        content-align: center middle;
        background: #000000;
    }
    RichLog { height: 1fr; padding: 0 1; }
    ListView { height: 1fr; border: solid $primary-darken-2; }
    #opord-progress {
        height: auto;
        max-height: 12;
        padding: 0 1;
        margin-bottom: 1;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
    }
    #text-panel { height: 1fr; padding: 1; }
    #text-actions { height: auto; margin-top: 1; }
    #text-actions Button { margin-right: 1; }
    Input { margin-top: 1; }
    #text-hint { margin-top: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("a", "confirm", "confirm", show=True),
        Binding("b", "back", "back", show=True),
        Binding("c", "copy_opord", "copy prompt", show=True),
        Binding("q", "quit_wizard", "quit", show=True),
    ]

    def __init__(
        self,
        steps: list[WizardStep],
        on_complete: Callable[[dict], None],
        initial_answers: dict | None = None,
        *,
        review_formatter: Optional[Callable[[dict], str]] = None,
        faction_pick_builder: Optional[Callable[[str], list[tuple[str, str]]]] = None,
        faction_label_fn: Optional[Callable[[str], str]] = None,
        opord_prompt_fn: Optional[Callable[[dict], str]] = None,
        opord_prompt_backup: Path | None = None,
        step_visible_fn: Optional[Callable[[str, dict], bool]] = None,
        uses_ai_opord_fn: Optional[Callable[[dict], bool]] = None,
        welcome_crest_fn: Optional[Callable[[], str]] = None,
        crest_image_path: Path | None = None,
        eo_prefix_fn: Optional[Callable[[dict], str]] = None,
        review_confirm_id: str = "review_confirm",
        review_edit_id: str = "review_edit",
    ) -> None:
        super().__init__()
        self.steps = steps
        self.on_complete = on_complete
        self.answers: dict = dict(initial_answers or {})
        self.notes: dict[str, str] = {}
        self.step_index = 0
        self.review_formatter = review_formatter
        self.faction_pick_builder = faction_pick_builder
        self.faction_label_fn = faction_label_fn
        self.opord_prompt_fn = opord_prompt_fn
        self.opord_prompt_backup = opord_prompt_backup
        self.step_visible_fn = step_visible_fn
        self.uses_ai_opord_fn = uses_ai_opord_fn
        self.welcome_crest_fn = welcome_crest_fn
        self.crest_image_path = crest_image_path
        self.eo_prefix_fn = eo_prefix_fn
        self._crest_renderable: HalfBlockImage | None = None
        self.review_confirm_id = review_confirm_id
        self.review_edit_id = review_edit_id
        self._editing_from_review = False
        self._review_confirm_index = next(
            (i for i, s in enumerate(steps) if s.step_id == review_confirm_id),
            max(0, len(steps) - 2),
        )
        self._faction_menu_index = next(
            (i for i, s in enumerate(steps) if s.step_id == "faction_menu"),
            -1,
        )
        self._faction_pick_index = next(
            (i for i, s in enumerate(steps) if s.step_id == "faction_pick"),
            -1,
        )

    def compose(self) -> ComposeResult:
        yield Static("", id="header")
        with Horizontal(id="body"):
            with Vertical(id="briefing-panel"):
                yield Static(id="crest-display")
                yield RichLog(id="briefing", wrap=True, highlight=True)
            with Vertical(id="choices-panel"):
                yield Static("", id="opord-progress")
                yield ListView(id="choices")
                with Vertical(id="text-panel"):
                    yield Static("", id="text-hint")
                    with Horizontal(id="text-actions"):
                        yield Button("Copy AI prompt", id="copy-opord-btn", variant="primary")
                        yield Button("Confirm", id="confirm-text-btn", variant="success")
                    yield Input(placeholder="Type here, Enter to confirm", id="text-input")
                    yield TextArea(id="text-area")
        yield Footer()

    def on_mount(self) -> None:
        cols, rows = recommended_terminal_size(self.crest_image_path)
        resize_terminal(cols, rows)

        self._crest_renderable = try_load_halfblock_image(self.crest_image_path)
        crest_display = self.query_one("#crest-display", Static)
        crest_display.display = False

        text_input = self.query_one("#text-input", Input)
        text_input.display = False
        self.query_one("#text-hint", Static).display = False
        self.query_one("#copy-opord-btn", Button).display = False
        self.query_one("#confirm-text-btn", Button).display = False
        self.query_one("#text-area", TextArea).display = False
        self.query_one("#opord-progress", Static).display = False
        self._render_step()

    def _uses_multiline_text(self, step: WizardStep) -> bool:
        return step.kind == "text" and step.text_multiline

    def _read_text_input(self, step: WizardStep) -> str:
        if self._uses_multiline_text(step):
            return self.query_one("#text-area", TextArea).text.strip()
        return self.query_one("#text-input", Input).value.strip()

    def _write_text_input(self, step: WizardStep, value: str) -> None:
        if self._uses_multiline_text(step):
            self.query_one("#text-area", TextArea).text = value
        else:
            self.query_one("#text-input", Input).value = value

    def _current_step(self) -> WizardStep:
        return self.steps[self.step_index]

    def _step_visible(self, step_id: str) -> bool:
        if self.step_visible_fn is None:
            return True
        return self.step_visible_fn(step_id, self.answers)

    def _uses_ai_opord(self) -> bool:
        if self.uses_ai_opord_fn is None:
            return False
        return self.uses_ai_opord_fn(self.answers)

    def _on_tactician_opord_step(self, step: WizardStep | None = None) -> bool:
        current = step or self._current_step()
        return (
            self.answers.get("knowledge_level") == "tactician"
            and is_tactician_opord_step(current.step_id)
        )

    def _warn_o_reference_block(self) -> str:
        if not self._on_tactician_opord_step():
            return ""
        warn_o = self.answers.get("warn_o")
        if not warn_o or not str(warn_o).strip():
            return ""
        return (
            "\nWarn O reference (from higher)\n"
            "──────────────────────────────\n"
            f"{str(warn_o).strip()}"
        )

    def _opord_section_progress(self, current_step_id: str) -> str:
        lines = ["OPORD sections", "──────────────"]
        for section in TACTICIAN_OPORD_SECTIONS:
            saved = self.answers.get(section.step_id)
            done = bool(saved and str(saved).strip())
            if section.step_id == current_step_id:
                marker = "▶"
            elif done:
                marker = "✓"
            else:
                marker = " "
            lines.append(f"{marker} {section.title}")
        return "\n".join(lines)

    def _faction_labels(self) -> str:
        factions = self.answers.get("factions", [])
        if not factions:
            return "(none yet)"
        if self.faction_label_fn:
            return ", ".join(self.faction_label_fn(f) for f in factions)
        return ", ".join(factions)

    def _choices_so_far(self) -> str:
        lines = ["Choices so far:", "─────────────────"]
        labels = {
            "theater": "Map",
            "game_format": "Blind mode",
            "player_cell": "Cell",
            "commander_name": "Commander",
            "force_name": "Force name",
            "force_size": "Force size",
            "knowledge_level": "Experience",
            "opord_mode": "OPORD approach",
            "tutorial_completed": "Tutorial",
            "warn_o": "Warn O",
            "operation_order": "OPORD",
        }
        for key, label in labels.items():
            if key not in self.answers:
                continue
            if not self._step_visible(key):
                continue
            val = self.answers[key]
            if isinstance(val, bool):
                display = "yes" if val else "no"
            elif val is None:
                display = "(skipped)"
            else:
                display = str(val)
            lines.append(f"· {label}: {display}")
        if self.answers.get("factions"):
            lines.append(f"· Factions: {self._faction_labels()}")
        eo_ref = self._warn_o_reference_block()
        if eo_ref:
            lines.append(eo_ref)
        return "\n".join(lines)

    def _force_size_briefing(self, highlighted: str | None) -> str:
        from campaign_hq import FORCE_SIZES, force_size_preview

        step = self._current_step()
        lines = [step.briefing, ""]
        force_name = self.answers.get("force_name")
        if highlighted:
            lines.append("Preview (highlighted):")
            lines.append(f"  {force_size_preview(highlighted, force_name=force_name)}")
            lines.append("")
        lines.append("All echelons:")
        for size in FORCE_SIZES:
            marker = "▶ " if size == highlighted else "  "
            lines.append(f"{marker}{force_size_preview(size, force_name=force_name)}")
        return "\n".join(lines)

    def _update_crest_display(self, step: WizardStep) -> None:
        crest_display = self.query_one("#crest-display", Static)
        if step.step_id == "welcome" and self._crest_renderable is not None:
            crest_display.update(self._crest_renderable)
            crest_display.styles.height = self._crest_renderable.char_height
            crest_display.display = True
            return
        crest_display.display = False

    def _write_briefing_body(self, step: WizardStep) -> None:
        briefing = self.query_one("#briefing", RichLog)
        if step.step_id == "welcome":
            if self._crest_renderable is None and self.welcome_crest_fn:
                briefing.write(self.welcome_crest_fn())
                briefing.write("")
            briefing.write(step.briefing)
        elif step.step_id == self.review_confirm_id and self.review_formatter:
            briefing.write(self.review_formatter(self.answers))
        elif step.kind == "faction_pick":
            category = self.answers.get("_faction_category", "Alliance")
            briefing.write(f"Category: {category}\n")
            briefing.write(step.briefing)
            briefing.write(f"\nSelected factions: {self._faction_labels()}")
        elif step.step_id == "force_size":
            choices = self._active_choices()
            list_view = self.query_one("#choices", ListView)
            idx = list_view.index if list_view.index is not None else 0
            highlighted = choices[idx][0] if choices and 0 <= idx < len(choices) else None
            briefing.write(self._force_size_briefing(highlighted))
        elif step.step_id == "warn_o":
            from campaign_briefing import WARN_O_INSTRUCTIONS_AI, WARN_O_INSTRUCTIONS_TACTICIAN

            if self.answers.get("knowledge_level") == "tactician":
                briefing.write(WARN_O_INSTRUCTIONS_TACTICIAN)
            else:
                briefing.write(WARN_O_INSTRUCTIONS_AI)
        elif step.step_id == "operation_order" and self._uses_ai_opord() and self.opord_prompt_fn:
            from campaign_briefing import opord_step_briefing

            briefing.write(opord_step_briefing(self.opord_prompt_fn(self.answers)))
        elif is_tactician_opord_step(step.step_id):
            if self.eo_prefix_fn:
                prefix = self.eo_prefix_fn(self.answers).strip()
                if prefix:
                    briefing.write(prefix)
                    briefing.write("")
            briefing.write(step.briefing)
        else:
            briefing.write(step.briefing)

    def _active_choices(self) -> list[tuple[str, str]]:
        step = self._current_step()
        if step.kind == "review_edit":
            return self._review_edit_choices()
        if step.kind == "faction_pick":
            category = self.answers.get("_faction_category", "Alliance")
            if self.faction_pick_builder:
                return self.faction_pick_builder(category)
            return [("__back__", "← Back to category menu")]
        return step.choices

    def _review_edit_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        for i, s in enumerate(self.steps):
            if s.step_id in {self.review_confirm_id, self.review_edit_id, "faction_pick", "welcome"}:
                continue
            if not self._step_visible(s.step_id):
                continue
            choices.append((str(i), f"Change: {s.title}"))
        choices.append(("back", "Back to review (keep selections)"))
        return choices

    def _render_step(self) -> None:
        step = self._current_step()
        header = self.query_one("#header", Static)

        if step.step_id == self.review_confirm_id:
            header.update(f"  ★ REVIEW ★  Step {self.step_index + 1} of {len(self.steps)} — Confirm or change")
        else:
            header.update(f"  {step.phase} · Step {self.step_index + 1} of {len(self.steps)} — {step.title}")

        briefing = self.query_one("#briefing", RichLog)
        briefing.clear()
        self._update_crest_display(step)
        self._write_briefing_body(step)
        if step.step_id != self.review_confirm_id:
            briefing.write("")
            briefing.write(self._choices_so_far())

        choices = self.query_one("#choices", ListView)
        text_input = self.query_one("#text-input", Input)
        text_hint = self.query_one("#text-hint", Static)

        choices.clear()
        text_input.display = False
        text_hint.display = False
        choices.display = True

        copy_btn = self.query_one("#copy-opord-btn", Button)
        confirm_btn = self.query_one("#confirm-text-btn", Button)
        text_area = self.query_one("#text-area", TextArea)
        opord_progress = self.query_one("#opord-progress", Static)

        if self._on_tactician_opord_step(step):
            opord_progress.update(self._opord_section_progress(step.step_id))
            opord_progress.display = True
        else:
            opord_progress.display = False

        if step.kind == "text":
            choices.display = False
            text_hint.display = True
            confirm_btn.display = True
            existing = self.answers.get(step.step_id, "")
            existing_str = existing if isinstance(existing, str) else ""
            if self._uses_multiline_text(step):
                text_input.display = False
                text_area.display = True
                if existing_str:
                    text_area.text = existing_str
                elif step.text_skeleton:
                    text_area.text = step.text_skeleton
                else:
                    text_area.text = ""
                if step.step_id == "operation_order" and self._uses_ai_opord():
                    copy_btn.display = True
                    text_hint.update(
                        "Copy AI prompt (or c) · paste OPORD below · Confirm when done · empty to skip"
                    )
                elif is_tactician_opord_step(step.step_id):
                    copy_btn.display = False
                    text_hint.update(
                        "Draft this paragraph · edit the prompts · Confirm to advance"
                    )
                else:
                    copy_btn.display = False
                    text_hint.update("Paste Warn O below · Confirm when done · empty to skip")
                text_area.focus()
            else:
                text_area.display = False
                text_input.display = True
                copy_btn.display = False
                text_hint.update("Type below · Enter or Confirm to continue")
                text_input.placeholder = step.text_placeholder
                text_input.value = existing_str
                text_input.focus()
        else:
            copy_btn.display = False
            confirm_btn.display = False
            active_choices = self._active_choices()
            for value, label in active_choices:
                choices.append(ListItem(Label(label), id=f"choice-{value}"))
            if choices.children:
                saved = self.answers.get(step.step_id)
                if saved is not None and step.kind == "choice":
                    for idx, (value, _label) in enumerate(active_choices):
                        if value == saved:
                            choices.index = idx
                            break
                    else:
                        choices.index = 0
                else:
                    choices.index = 0
                if step.step_id == "force_size":
                    self._write_briefing_body(step)
            choices.focus()

        if step.step_id == self.review_confirm_id:
            self.notify(
                "Review screen — confirm on the right, or pick 'change a selection'",
                severity="information",
                timeout=6,
            )

    def _selected_choice_value(self) -> str | None:
        step = self._current_step()
        if step.kind not in ("choice", "review_edit", "faction_menu", "faction_pick"):
            return None
        choices = self._active_choices()
        list_view = self.query_one("#choices", ListView)
        if list_view.index is None or list_view.index >= len(choices):
            return None
        return choices[list_view.index][0]

    def _go_to_review(self) -> None:
        self._editing_from_review = False
        self.step_index = self._review_confirm_index
        self._render_step()

    def _go_to_faction_menu(self) -> None:
        self.step_index = self._faction_menu_index
        self._render_step()

    def _skip_virtual_steps_forward(self) -> None:
        """faction_pick and review_edit are only reached via explicit jumps."""
        self.step_index += 1
        while self.step_index < len(self.steps):
            sid = self.steps[self.step_index].step_id
            if sid in (self.review_edit_id, "faction_pick"):
                self.step_index += 1
                continue
            if not self._step_visible(sid):
                self.step_index += 1
                continue
            break

    def _skip_virtual_steps_backward(self) -> None:
        if self.step_index == 0:
            return
        self.step_index -= 1
        while self.step_index > 0:
            sid = self.steps[self.step_index].step_id
            if sid == "faction_pick" or not self._step_visible(sid):
                self.step_index -= 1
                continue
            break

    def _advance_linear(self) -> None:
        self._skip_virtual_steps_forward()
        if self.step_index >= len(self.steps):
            self._go_to_review()
            return
        self._render_step()

    def _finalize(self) -> None:
        def handle(confirmed: bool) -> None:
            if confirmed:
                self.on_complete({**self.answers, "notes": self.notes})
                self.exit()

        self.push_screen(FinalizeConfirm(), handle)

    def _advance(self, value) -> None:
        step = self._current_step()

        if step.step_id == self.review_confirm_id:
            if value == "finalize":
                self._finalize()
                return
            if value == "__edit__":
                self.step_index = next(
                    i for i, s in enumerate(self.steps) if s.step_id == self.review_edit_id
                )
                self._render_step()
                return

        if step.kind == "review_edit":
            if value == "back":
                self._go_to_review()
                return
            self._editing_from_review = True
            self.step_index = int(value)
            self._render_step()
            return

        if step.kind == "faction_menu":
            if value == "done":
                if not self.answers.get("factions"):
                    self.notify("Pick at least one faction first", severity="warning")
                    return
                self.answers[step.step_id] = "done"
                if self._editing_from_review:
                    self.notify("Updated — back to review", severity="information")
                    self._go_to_review()
                    return
                self._advance_linear()
                return
            self.answers["_faction_category"] = value
            self.step_index = self._faction_pick_index
            self._render_step()
            return

        if step.kind == "faction_pick":
            if value != "__back__":
                factions = self.answers.setdefault("factions", [])
                if value not in factions:
                    factions.append(value)
                    label = self.faction_label_fn(value) if self.faction_label_fn else value
                    self.notify(f"Added {label}", severity="information")
            self._go_to_faction_menu()
            return

        self.answers[step.step_id] = value

        if self._editing_from_review:
            self.notify("Updated — back to review", severity="information")
            self._go_to_review()
            return

        self._advance_linear()

    def action_confirm(self) -> None:
        step = self._current_step()
        if step.kind == "text":
            value = self._read_text_input(step)
            optional_steps = {"operation_order", "warn_o", *{
                s.step_id for s in TACTICIAN_OPORD_SECTIONS
            }}
            if not value and step.step_id not in optional_steps:
                self.notify("Enter a value first", severity="warning")
                return
            self._advance(value if value else None)
        elif step.kind in ("choice", "review_edit", "faction_menu", "faction_pick"):
            value = self._selected_choice_value()
            if value is None:
                return
            self._advance(value)

    def action_back(self) -> None:
        step = self._current_step()
        if step.step_id == self.review_edit_id:
            self._go_to_review()
            return
        if step.step_id == self.review_confirm_id:
            if self.step_index > 0:
                self._skip_virtual_steps_backward()
                self._render_step()
            return
        if step.kind == "faction_pick":
            self._go_to_faction_menu()
            return
        if self._editing_from_review:
            self._go_to_review()
            return
        if self.step_index == 0:
            self.notify("Already at first step", severity="information")
            return
        self._skip_virtual_steps_backward()
        self._render_step()

    def _copy_opord_prompt(self) -> None:
        if self._current_step().step_id != "operation_order":
            self.notify("Copy prompt is only on the Operation order step", severity="warning")
            return
        if not self._uses_ai_opord():
            self.notify("AI prompt is only available for Casual + Use AI", severity="warning")
            return
        if not self.opord_prompt_fn:
            return
        text = self.opord_prompt_fn(self.answers)
        backup_path = None
        if self.opord_prompt_backup is not None:
            backup_path = write_clipboard_fallback(self.opord_prompt_backup, text)

        if copy_to_system_clipboard(text):
            msg = "AI prompt copied to clipboard"
            if backup_path is not None:
                msg += f" (backup: {backup_path.name})"
            self.notify(msg, severity="information")
            return

        if backup_path is not None:
            self.notify(
                f"Clipboard unavailable — prompt saved to {backup_path}",
                severity="warning",
                timeout=8,
            )
        else:
            self.notify("Clipboard copy failed — select and copy from the briefing panel", severity="error")

    def action_copy_opord(self) -> None:
        self._copy_opord_prompt()

    @on(Button.Pressed, "#copy-opord-btn")
    def on_copy_opord_pressed(self) -> None:
        self._copy_opord_prompt()

    @on(Button.Pressed, "#confirm-text-btn")
    def on_confirm_text_pressed(self) -> None:
        self.action_confirm()

    def action_quit_wizard(self) -> None:
        def handle_result(quit_ok: bool) -> None:
            if quit_ok:
                self.exit(1)

        self.push_screen(QuitConfirm(), handle_result)

    @on(Input.Submitted, "#text-input")
    def on_text_submitted(self) -> None:
        self.action_confirm()

    @on(TextArea.Changed, "#text-area")
    def on_text_area_changed(self) -> None:
        if self._current_step().step_id != "operation_order":
            return
        briefing = self.query_one("#briefing", RichLog)
        briefing.clear()
        self._write_briefing_body(self._current_step())
        briefing.write("")
        briefing.write(self._choices_so_far())

    @on(ListView.Highlighted, "#choices")
    def on_choice_highlighted(self, _event: ListView.Highlighted) -> None:
        if self._current_step().step_id != "force_size":
            return
        briefing = self.query_one("#briefing", RichLog)
        briefing.clear()
        self._write_briefing_body(self._current_step())
        briefing.write("")
        briefing.write(self._choices_so_far())


def run_tui(
    steps: list[WizardStep],
    on_complete: Callable[[dict], None],
    *,
    review_formatter: Optional[Callable[[dict], str]] = None,
    faction_pick_builder: Optional[Callable[[str], list[tuple[str, str]]]] = None,
    faction_label_fn: Optional[Callable[[str], str]] = None,
    opord_prompt_fn: Optional[Callable[[dict], str]] = None,
    opord_prompt_backup: Path | None = None,
    step_visible_fn: Optional[Callable[[str, dict], bool]] = None,
    uses_ai_opord_fn: Optional[Callable[[dict], bool]] = None,
    welcome_crest_fn: Optional[Callable[[], str]] = None,
    crest_image_path: Path | None = None,
    eo_prefix_fn: Optional[Callable[[dict], str]] = None,
) -> int:
    app = CampaignSetupApp(
        steps,
        on_complete,
        review_formatter=review_formatter,
        faction_pick_builder=faction_pick_builder,
        faction_label_fn=faction_label_fn,
        opord_prompt_fn=opord_prompt_fn,
        opord_prompt_backup=opord_prompt_backup,
        step_visible_fn=step_visible_fn,
        uses_ai_opord_fn=uses_ai_opord_fn,
        welcome_crest_fn=welcome_crest_fn,
        crest_image_path=crest_image_path,
        eo_prefix_fn=eo_prefix_fn,
    )
    return app.run() or 0