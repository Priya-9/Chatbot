"""YAML-driven conversation journey engine.

A flow is a set of named nodes. The user's current node is stored on `User.journey_node`; free-form
values collected along the way live in `User.journey_data`.

Node types
----------
message          send `text`, then continue to `next` immediately
menu             send `text` with `options` (buttons if <= 3, list otherwise); wait for a choice.
                 `fallback: <node>` forwards unmatched free text to that node (e.g. the AI chat)
input            send `text`, wait for a reply, `validate` it, store it as `save_as`, go to `next`
action           run a registered Python action; go to `on_success` / `on_failure` (or the action's goto)
ai               send `text` once, then answer every message with RAG + LLM
language_select  list of supported languages; stores the choice on the user, then `next`
niche_select     (demo mode) list of business niches from NICHES_FILE; stores the choice as `niche`, then
                 `next`. Once chosen, every text can use {business}, {book_label}, {examples}... (app/demo)

Any node may set `requires_auth: true`; unauthenticated users are sent through `auth_node` first and
returned afterwards (the special target `_return`).
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import yaml

from app.whatsapp.messages import ButtonsOut, Incoming, ListOut, Outgoing, TextOut

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.demo.niches import Niche

    from app.models import Message, User
    from app.services.container import Services

log = logging.getLogger(__name__)

MAX_AUTO_STEPS = 25
RETURN = "_return"

VALIDATORS: dict[str, Callable[[str], bool]] = {
    "nonempty": lambda v: bool(v.strip()),
    "email": lambda v: bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", v.strip())),
    "phone": lambda v: bool(re.fullmatch(r"\+?[\d\s\-()]{7,20}", v.strip())),
    "otp": lambda v: bool(re.fullmatch(r"\d{6}", v.strip())),
}


@dataclass
class Context:
    db: "Session"
    user: "User"
    services: "Services"
    inbound: "Message | None" = None

    @property
    def lang(self) -> str:
        return self.services.translator.resolve(self.user.language)

    @property
    def niche(self) -> "Niche | None":
        return self.services.niches.get((self.user.journey_data or {}).get("niche") or "")

    def t(self, key: str, **params) -> str:
        params.setdefault("name", self.user.name or "")
        params.setdefault("brand", self.services.settings.business_name)
        if self.niche:
            for k, v in self.niche.params(self.lang).items():
                params.setdefault(k, v)
        params.setdefault("business", self.services.settings.business_name)
        return self.services.translator.t(key, self.lang, **params)

    @property
    def data(self) -> dict:
        return dict(self.user.journey_data or {})

    def set_data(self, **values) -> None:
        # reassign (not mutate) so SQLAlchemy detects the JSON change
        self.user.journey_data = {**(self.user.journey_data or {}), **values}


@dataclass
class ActionResult:
    ok: bool = True
    messages: list[Outgoing] = field(default_factory=list)
    goto: str | None = None  # overrides on_success / on_failure


Action = Callable[[Context, dict], ActionResult]


class JourneyEngine:
    def __init__(self, flow: dict, actions: dict[str, Action]):
        self.flow = flow
        self.nodes: dict[str, dict] = flow["nodes"]
        self.start = flow["start"]
        self.home = flow.get("home", self.start)
        self.auth_node = flow.get("auth_node")
        self.actions = actions
        self.commands: dict[str, str] = {
            kw.strip().lower(): cmd["goto"] for cmd in flow.get("commands", []) for kw in cmd["keywords"]
        }
        self._validate_flow()

    @classmethod
    def from_yaml(cls, path: str | Path, actions: dict[str, Action]) -> "JourneyEngine":
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")), actions)

    def _validate_flow(self) -> None:
        targets = {self.start, self.home, *self.commands.values()}
        if self.auth_node:
            targets.add(self.auth_node)
        for name, node in self.nodes.items():
            targets.update(node.get(k) for k in ("next", "on_success", "on_failure", "on_abort", "fallback"))
            targets.update(opt.get("next") for opt in node.get("options", []))
            if node.get("type") == "action" and node.get("action") not in self.actions:
                raise ValueError(f"Node {name!r} uses unknown action {node.get('action')!r}")
            if node.get("requires_auth") and not self.auth_node:
                raise ValueError(f"Node {name!r} requires auth but the flow has no auth_node")
        missing = {t for t in targets if t and t != RETURN and t not in self.nodes}
        if missing:
            raise ValueError(f"Flow references undefined nodes: {sorted(missing)}")

    # ------------------------------------------------------------------ public

    def handle(self, ctx: Context, inc: Incoming) -> list[Outgoing]:
        out: list[Outgoing] = []
        text = (inc.text or "").strip()

        command = self.commands.get(text.lower()) if text and not inc.reply_id else None
        if not ctx.user.journey_node or ctx.user.journey_node not in self.nodes:
            # new user (or a node removed from the flow): always begin at the start
            self.goto(ctx, self.start if not ctx.user.language else self.home, out)
        elif command:
            self.goto(ctx, command, out)
        else:
            self._handle_input(ctx, ctx.user.journey_node, inc, out)
        return out

    def goto(self, ctx: Context, node_id: str | None, out: list[Outgoing]) -> None:
        steps = 0
        while node_id:
            steps += 1
            if steps > MAX_AUTO_STEPS:
                log.error("Journey loop detected at node %r", node_id)
                return
            if node_id == RETURN:
                node_id = ctx.data.get("auth_return") or self.home
                ctx.set_data(auth_return=None)
                continue
            node = self.nodes[node_id]
            if node.get("requires_auth") and not ctx.services.auth.is_verified(ctx.user):
                ctx.set_data(auth_return=node_id)
                node_id = self.auth_node
                continue
            ctx.user.journey_node = node_id
            node_id = self._enter(ctx, node, out)

    # --------------------------------------------------------------- internals

    def _enter(self, ctx: Context, node: dict, out: list[Outgoing]) -> str | None:
        """Render a node. Returns the next node for auto-advancing nodes, None to wait for input."""
        ntype = node["type"]
        if ntype == "message":
            out.append(TextOut(ctx.t(node["text"])))
            return node.get("next")
        if ntype == "menu":
            out.append(self._render_menu(ctx, node))
            return None
        if ntype == "language_select":
            out.append(self._render_languages(ctx, node))
            return None
        if ntype == "niche_select":
            out.append(self._render_niches(ctx, node))
            return None
        if ntype in ("input", "ai"):
            if node.get("text"):
                out.append(TextOut(ctx.t(node["text"])))
            return None
        if ntype == "action":
            try:
                result = self.actions[node["action"]](ctx, node)
            except Exception:
                log.exception("Action %r failed", node["action"])
                result = ActionResult(ok=False, messages=[TextOut(ctx.t("common.error"))], goto=self.home)
            out.extend(result.messages)
            return result.goto or (node.get("on_success") if result.ok else node.get("on_failure"))
        raise ValueError(f"Unknown node type {ntype!r}")

    def _handle_input(self, ctx: Context, node_id: str, inc: Incoming, out: list[Outgoing]) -> None:
        node = self.nodes[node_id]
        ntype = node["type"]
        text = (inc.text or "").strip()

        if ntype == "menu":
            option = self._match_option(ctx, node, inc)
            if option:
                self.goto(ctx, option["next"], out)
            elif node.get("fallback") and text:
                ctx.user.journey_node = node["fallback"]
                self._handle_input(ctx, node["fallback"], inc, out)
            else:
                out.append(TextOut(ctx.t("common.invalid_option")))
                out.append(self._render_menu(ctx, node))

        elif ntype == "language_select":
            code = self._match_language(ctx, inc)
            if code:
                ctx.user.language = code
                out.append(TextOut(ctx.t("language.set")))
                self.goto(ctx, node["next"], out)
            else:
                out.append(self._render_languages(ctx, node))

        elif ntype == "niche_select":
            niche = self._match_niche(ctx, inc)
            if niche:
                # remember where this niche's chat starts, so AI memory doesn't leak between niches
                ctx.set_data(niche=niche.id, niche_from=ctx.inbound.id if ctx.inbound else None)
                self.goto(ctx, node["next"], out)
            else:
                if text:
                    out.append(TextOut(ctx.t("common.invalid_option")))
                out.append(self._render_niches(ctx, node))

        elif ntype == "input":
            if not text:
                out.append(TextOut(ctx.t("common.text_only")))
                return
            rule = node.get("validate")
            if rule and not VALIDATORS[rule](text):
                out.append(TextOut(ctx.t(f"validation.{rule}")))
                return
            ctx.set_data(**{node["save_as"]: text})
            self.goto(ctx, node["next"], out)

        elif ntype == "ai":
            if not text or inc.type not in ("text", "interactive", "button"):
                out.append(TextOut(ctx.t("common.text_only")))
                return
            exclude = ctx.inbound.id if ctx.inbound else None
            if ctx.inbound:
                ctx.inbound.ai = True
            answer = ctx.services.ai.answer(ctx.db, ctx.user, text, exclude_message_id=exclude)
            out.append(TextOut(answer, ai=True))

        else:  # message/action nodes don't take input: restart from the home menu
            self.goto(ctx, self.home, out)

    def _option_label(self, ctx: Context, opt: dict) -> str:
        return ctx.t(opt["label"])

    def _match_option(self, ctx: Context, node: dict, inc: Incoming) -> dict | None:
        options = node.get("options", [])
        if inc.reply_id:
            return next((o for o in options if o["id"] == inc.reply_id), None)
        text = (inc.text or "").strip().lower()
        if text.isdigit() and 1 <= int(text) <= len(options):
            return options[int(text) - 1]
        return next((o for o in options if self._option_label(ctx, o).lower() == text), None)

    def _match_language(self, ctx: Context, inc: Incoming) -> str | None:
        translator = ctx.services.translator
        if inc.reply_id and inc.reply_id.startswith("lang:"):
            code = inc.reply_id.removeprefix("lang:")
            return code if code in translator.languages else None
        text = (inc.text or "").strip().lower()
        for code in translator.languages:
            names = {code, translator.language_name(code).lower(), translator.english_name(code).lower()}
            if text in names:
                return code
        return None

    def _match_niche(self, ctx: Context, inc: Incoming) -> "Niche | None":
        niches = list(ctx.services.niches.values())
        if inc.reply_id and inc.reply_id.startswith("niche:"):
            return ctx.services.niches.get(inc.reply_id.removeprefix("niche:"))
        text = (inc.text or "").strip()
        if text.isdigit() and 1 <= int(text) <= len(niches):
            return niches[int(text) - 1]
        return next((n for n in niches if n.matches(text, ctx.lang)), None)

    def _render_niches(self, ctx: Context, node: dict) -> Outgoing:
        # WhatsApp lists show at most 10 rows; extra niches can still be reached by typing an alias
        rows = [
            (f"niche:{n.id}", n.text("title", ctx.lang), n.text("description", ctx.lang))
            for n in ctx.services.niches.values()
        ][:10]
        return ListOut(ctx.t(node["text"]), ctx.t(node.get("button", "menu.button")), rows)

    def _render_menu(self, ctx: Context, node: dict) -> Outgoing:
        body = ctx.t(node["text"])
        options = node.get("options", [])
        if len(options) <= 3:
            return ButtonsOut(body, [(o["id"], self._option_label(ctx, o)) for o in options])
        rows = [
            (o["id"], self._option_label(ctx, o), ctx.t(o["description"]) if o.get("description") else "")
            for o in options
        ]
        return ListOut(body, ctx.t(node.get("button", "menu.button")), rows)

    def _render_languages(self, ctx: Context, node: dict) -> Outgoing:
        tr = ctx.services.translator
        rows = [(f"lang:{c}", tr.language_name(c), tr.english_name(c)) for c in tr.languages]
        body = ctx.t(node["text"])
        if len(rows) <= 3:
            return ButtonsOut(body, [(rid, title) for rid, title, _ in rows])
        return ListOut(body, ctx.t(node.get("button", "language.button")), rows)
