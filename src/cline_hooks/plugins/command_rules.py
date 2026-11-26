from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HooksPlugin, hookimpl, hookspec
from cline_hooks.handlers.commands import CommandRule, _split_git_words
from cline_hooks.plugins.build_tools import all_build_commands

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import ParsedCommand


def validate_git_commit_message(cmd: ParsedCommand, _all: list[ParsedCommand]) -> bool:
    """Check if a git commit message contains newlines.

    Returns:
        bool: True if the message is invalid (contains newlines).
    """
    if "commit" not in cmd.args:
        return False

    for flag in cmd.flags:
        if flag in {"-m", "--message"}:
            msg_idx = (
                cmd.flags.index(flag) + 1 + len([a for a in cmd.args if cmd.args.index(a) < cmd.flags.index(flag)])
            )
            all_words = cmd.args + cmd.flags
            if msg_idx < len(all_words):
                message = all_words[msg_idx]
                return "\n" in message
        elif flag.startswith("--message="):
            message = flag[10:]
            return "\n" in message

    return False


_MESSAGE_FLAG = re.compile(r"-[a-zA-Z]*m")
_INLINE_MESSAGE_FLAG = re.compile(r"-[a-zA-Z]*m(.+)", re.DOTALL)
_CHECK_NOUN = r"(?:tests?|builds?|checks?|ci|lint|type-?check|suite|pipeline)"
_AUXILIARY = r"(?:(?:is|are|was|were|has|have|had|been|now|all|currently|still|already|finally|again)\s+)*"
_DETERMINER = r"(?:the|a|our|this|these|every|both|all)"
_SUCCESS_WORD = r"(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?|successful(?:ly)?)"
_PASS_CLAIM = re.compile(
    rf"\s*(?:{_DETERMINER}\s+(?:\w+\s+){{0,2}})?"
    rf"(?:{_CHECK_NOUN}\s+{_AUXILIARY}{_SUCCESS_WORD}|(?:everything|all)\s+{_AUXILIARY}(?:green|passing|passes|passed))"
    r"(?![\w-])",
    re.IGNORECASE,
)
_CLAUSE_BOUNDARY = re.compile(r"[:;,()\[\]\n]|[.!?](?=\s|$)|\s[-|/&\u2013\u2014]+\s|&&|\|\|")


def _commit_messages(cmd: ParsedCommand) -> list[str]:
    """Return the `-m` and `--message` values of a `git commit`, else an empty list."""
    subcommand, subcommand_words = _split_git_words(cmd.words)
    if subcommand != "commit":
        return []
    messages: list[str] = []
    words = iter(subcommand_words)
    for word in words:
        if word.startswith("--message="):
            messages.append(word.removeprefix("--message="))
        elif word == "--message" or _MESSAGE_FLAG.fullmatch(word):
            messages.append(next(words, ""))
        elif not word.startswith("--") and (inline := _INLINE_MESSAGE_FLAG.fullmatch(word)):
            messages.append(inline.group(1))
    return messages


_TEST_NAME = re.compile(
    r"\btest_\w+|\w::test\w*"
    r"|\b(?:it|test|describe)(?:\.\w+)*\s*(?:(?:\([^()]*\)|`[^`]*`)\s*)?\(\s*[\"'`]"
)


def validate_git_commit_test_name(cmd: ParsedCommand, _all: list[ParsedCommand]) -> bool:
    """Check if a git commit message lists a test name.

    Returns:
        bool: True if the message is invalid (contains a test name).
    """
    return any(_TEST_NAME.search(message) for message in _commit_messages(cmd))


def validate_git_commit_pass_claim(cmd: ParsedCommand, _all: list[ParsedCommand]) -> bool:
    """Check if a git commit message claims that the build, tests, checks or CI pass.

    Returns:
        bool: True if the message is invalid (contains a pass claim).
    """
    return any(
        _PASS_CLAIM.match(clause) for message in _commit_messages(cmd) for clause in _CLAUSE_BOUNDARY.split(message)
    )


_FILE_MESSAGE_FLAG = re.compile(r"-[^-mCctuS]*F")


def validate_git_commit_file_message(cmd: ParsedCommand, _all: list[ParsedCommand]) -> bool:
    """Check if a git commit reads its message from a file.

    Returns:
        bool: True if the commit uses -F or --file.
    """
    subcommand, subcommand_words = _split_git_words(cmd.words)
    if subcommand != "commit":
        return False
    words = iter(subcommand_words)
    for word in words:
        if word == "--message" or _MESSAGE_FLAG.fullmatch(word):
            next(words, "")
        elif word == "--file" or word.startswith("--file=") or _FILE_MESSAGE_FLAG.match(word):
            return True
    return False


_NON_BUILD_FLAGS = frozenset({"--help", "--version"})


def _is_build_invocation(cmd: ParsedCommand | None) -> bool:
    """Return True when the command runs a build tool and is not a help or version query."""
    return cmd is not None and cmd.name in all_build_commands() and _NON_BUILD_FLAGS.isdisjoint(cmd.flags)


_VALUE_SHORT_OPTIONS = {"grep": frozenset("efmABCdD"), "head": frozenset("nc"), "tail": frozenset("ncs")}
_PATTERN_OPTIONS = frozenset({"e", "f", "--regexp", "--file"})
_VALUE_LONG_OPTIONS = frozenset({
    "--regexp",
    "--file",
    "--max-count",
    "--after-context",
    "--before-context",
    "--context",
    "--directories",
    "--devices",
    "--lines",
    "--bytes",
    "--sleep-interval",
    "--pid",
})


def _operands(cmd: ParsedCommand) -> list[str]:
    """Return the command's non-option words, less grep's pattern operand unless -e/-f supplied it."""
    value_options = _VALUE_SHORT_OPTIONS.get(cmd.name, frozenset())
    operands: list[str] = []
    has_pattern_option = False
    pending_value = False
    options_ended = False
    for word in cmd.words:
        if pending_value:
            pending_value = False
        elif options_ended or not word.startswith("-") or word == "-":
            operands.append(word)
        elif word == "--":
            options_ended = True
        elif word.startswith("--"):
            name = word.split("=", 1)[0]
            has_pattern_option |= name in _PATTERN_OPTIONS
            pending_value = name in _VALUE_LONG_OPTIONS and "=" not in word
        else:
            for index, char in enumerate(word[1:], start=1):
                if char in value_options:
                    has_pattern_option |= char in _PATTERN_OPTIONS
                    pending_value = index == len(word) - 1
                    break
    return operands[1:] if cmd.name == "grep" and not has_pattern_option else operands


def _file_inputs(cmd: ParsedCommand) -> list[str]:
    """Return the files a command reads: its operands and stdin redirects."""
    return [*_operands(cmd), *cmd.redirect_inputs]


def reads_piped_build_output(cmd: ParsedCommand) -> bool:
    """Return True when a grep, head or tail command reads a build command's output from stdin."""
    file_inputs = _file_inputs(cmd)
    reads_stdin = not file_inputs or "-" in file_inputs
    return cmd.name in _VALUE_SHORT_OPTIONS and _is_build_invocation(cmd.piped_from) and reads_stdin


def _filters_build_output(cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when the command reads a log a build command redirected its output to."""
    build_logs = {Path(log) for build in all_commands if _is_build_invocation(build) for log in build.redirect_outputs}
    return not build_logs.isdisjoint(map(Path, _file_inputs(cmd)))


_INLINE_SCRIPT_FLAGS = {"python": frozenset({"-c"}), "python3": frozenset({"-c"}), "node": frozenset({"-e", "--eval"})}
_UV_VALUE_OPTIONS = frozenset({
    "--with",
    "--with-editable",
    "--with-requirements",
    "--python",
    "-p",
    "--project",
    "--directory",
    "--env-file",
    "--extra",
    "--group",
    "--package",
    "--index",
})
_PYTHON_STREAM_METADATA = frozenset({"isatty", "closed", "name", "mode", "encoding", "errors"})
_PYTHON_JSON_PARSERS = frozenset({"load", "loads"})
_JS_JSON_PARSE = re.compile(r"\bJSON\.parse\s*\(")
_JS_STRING = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`")
_JS_STDIN_PATH = "__stdin_path__"
_JS_STDIN = re.compile(
    rf"\bprocess\.stdin\b(?!\.(?:isTTY|isRaw|destroyed|closed|readable\w*)\b)|\b{_JS_STDIN_PATH}\b|\breadFileSync\(\s*0\b"
)
_JS_NAME = re.compile(r"[A-Za-z_$][\w$]*")
_JS_ASSIGNMENT = re.compile(r"([A-Za-z_$][\w$]*)\s*\+?=(?![=>])\s*")
_JS_FOR_OF = re.compile(r"\b(?:const|let|var)\s+([\w$]+)\s+of\s+")
_JS_PARAMETERS = re.compile(r"\(([^()]*)\)\s*=>|([\w$]+)\s*=>|\bfunction\s*\w*\s*\(([^()]*)\)")


def _interpreter_call(cmd: ParsedCommand) -> tuple[str, list[str]]:
    """Return the program a command runs and its words, looking through `uv run` and its options."""
    if cmd.name != "uv" or cmd.words[:1] != ["run"]:
        return cmd.name, cmd.words
    words = iter(cmd.words[1:])
    for word in words:
        if word in _UV_VALUE_OPTIONS:
            next(words, None)
        elif not word.startswith("-"):
            return Path(word).name, list(words)
    return "", []


def _inline_script(cmd: ParsedCommand) -> tuple[str, str]:
    """Return the interpreter and its `python -c` or `node -e` snippet, with an empty snippet when there is none."""
    interpreter, words = _interpreter_call(cmd)
    flags = _INLINE_SCRIPT_FLAGS.get(interpreter, frozenset())
    words_iter = iter(words)
    for word in words_iter:
        if word in flags:
            return interpreter, next(words_iter, "")
        if not word.startswith("-"):
            break
    return interpreter, ""


def _reads_python_stdin(node: ast.AST) -> bool:
    """Return True when the node is a read of standard input."""
    match node:
        case ast.Attribute(attr="stdin") | ast.Name(id="stdin") | ast.Constant(value="/dev/stdin"):
            return True
        case ast.Call(func=ast.Name(id="input")):
            return True
        case ast.Call(func=ast.Name(id="open") | ast.Attribute(attr="fdopen"), args=[ast.Constant(value=0), *_]):
            return True
    return False


def _python_json_parse_names(nodes: list[ast.AST]) -> tuple[set[str], set[str]]:
    """Return the names bound to the json module and to its parse functions."""
    modules = {
        alias.asname or alias.name
        for node in nodes
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "json"
    }
    functions = {
        alias.asname or alias.name
        for node in nodes
        if isinstance(node, ast.ImportFrom) and node.module == "json"
        for alias in node.names
        if alias.name in _PYTHON_JSON_PARSERS
    }
    return modules, functions


def _is_json_parser(func: ast.expr, modules: set[str], functions: set[str]) -> bool:
    """Return True when the called expression is `json.load`, `json.loads` or an import of either."""
    match func:
        case ast.Name(id=name):
            return name in functions
        case ast.Attribute(value=ast.Name(id=module), attr=attr):
            return module in modules and attr in _PYTHON_JSON_PARSERS
    return False


def _python_bindings(node: ast.AST) -> tuple[list[ast.expr], ast.expr | None]:
    """Return the targets a statement binds and the expression that supplies them."""
    match node:
        case ast.Assign(targets=targets, value=source):
            return targets, source
        case ast.AnnAssign(target=target, value=source) | ast.NamedExpr(target=target, value=source):
            return [target], source
        case ast.For(target=target, iter=source):
            return [target], source
        case ast.withitem(context_expr=source, optional_vars=ast.expr() as target):
            return [target], source
    return [], None


def _python_stdin_names(nodes: list[ast.AST]) -> set[str]:
    """Return the names bound to something read from standard input."""
    names: set[str] = set()
    for node in nodes:
        targets, source = _python_bindings(node)
        if source is not None and _comes_from_python_stdin(source, names):
            names |= {n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name)}
    return names


def _comes_from_python_stdin(expression: ast.AST, stdin_names: set[str]) -> bool:
    """Return True when the expression reads standard input data or uses a name bound to it."""
    nodes = list(ast.walk(expression))
    metadata_owners = {
        id(node.value) for node in nodes if isinstance(node, ast.Attribute) and node.attr in _PYTHON_STREAM_METADATA
    }
    return any(
        id(node) not in metadata_owners
        and (_reads_python_stdin(node) or (isinstance(node, ast.Name) and node.id in stdin_names))
        for node in nodes
    )


def _python_parses_json(script: str) -> bool:
    """Return True when a Python snippet passes standard input to a json parse function."""
    try:
        nodes = list(ast.walk(ast.parse(script)))
    except (SyntaxError, ValueError):
        return False
    modules, functions = _python_json_parse_names(nodes)
    stdin_names = _python_stdin_names(nodes)
    return any(
        isinstance(node, ast.Call)
        and _is_json_parser(node.func, modules, functions)
        and any(_comes_from_python_stdin(argument, stdin_names) for argument in node.args)
        for node in nodes
    )


def _js_expression(text: str, start: int) -> str:
    """Return the text from `start` to the end of its expression: a top-level `;`, `,`, newline or closing bracket."""
    depth = 0
    for end in range(start, len(text)):
        if text[end] in "([{":
            depth += 1
        elif text[end] in ")]}":
            if not depth:
                return text[start:end]
            depth -= 1
        elif not depth and text[end] in ";,\n":
            return text[start:end]
    return text[start:]


def _js_comes_from_stdin(expression: str, stdin_names: set[str]) -> bool:
    """Return True when the expression reads standard input or uses a name bound to it."""
    return bool(_JS_STDIN.search(expression)) or not stdin_names.isdisjoint(_JS_NAME.findall(expression))


def _js_stdin_names(script: str) -> set[str]:
    """Return the names bound to something read from standard input, including stdin callback parameters."""
    names = {
        name
        for statement in re.split(r"[;\n]", script)
        if _JS_STDIN.search(statement)
        for groups in _JS_PARAMETERS.findall(statement)
        for name in _JS_NAME.findall(" ".join(groups))
    }
    bindings = [
        (match.group(1), _js_expression(script, match.end()))
        for pattern in (_JS_ASSIGNMENT, _JS_FOR_OF)
        for match in pattern.finditer(script)
    ]
    while found := {name for name, source in bindings if name not in names and _js_comes_from_stdin(source, names)}:
        names |= found
    return names


def _node_parses_json(script: str) -> bool:
    """Return True when a Node snippet passes a value read from standard input to JSON.parse."""
    emptied = _JS_STRING.sub(lambda m: _JS_STDIN_PATH if m.group()[1:-1] == "/dev/stdin" else '""', script)
    stdin_names = _js_stdin_names(emptied)
    return any(
        _js_comes_from_stdin(_js_expression(emptied, match.end()), stdin_names)
        for match in _JS_JSON_PARSE.finditer(emptied)
    )


_JSON_PARSE_CHECKS = {"python": _python_parses_json, "python3": _python_parses_json, "node": _node_parses_json}


def _parses_stdin_json_inline(cmd: ParsedCommand, _all: list[ParsedCommand]) -> bool:
    """Return True when an inline script parses JSON read from stdin."""
    interpreter, script = _inline_script(cmd)
    return bool(script) and _JSON_PARSE_CHECKS[interpreter](script)


def _is_standalone(_cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when the command is the only one (not piped into something else)."""
    return len(all_commands) == 1


def _is_follow(cmd: ParsedCommand) -> bool:
    """Return True when tail is following a file (-f / -F / --follow)."""
    return any(
        flag.startswith("--follow")
        or (flag.startswith("-") and not flag.startswith("--") and ("f" in flag[1:] or "F" in flag[1:]))
        for flag in cmd.flags
    )


def _is_standalone_tail(cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when tail is standalone reading a file, excluding live follow."""
    return len(all_commands) == 1 and not _is_follow(cmd)


class CommandRulesSpec:
    """Extension point for contributing shell command rules."""

    @hookspec
    def command_rules(self) -> list[CommandRule]:
        """Return CommandRule instances this plugin wants to enforce.

        Returns:
            List of CommandRule objects.
        """
        raise NotImplementedError


class CommandRulesPlugin(HooksPlugin):
    """Standard shell-safety command rules (rm -f, commit messages, build output)."""

    hookspecs = CommandRulesSpec

    @hookimpl
    def command_rules(self) -> list[CommandRule]:
        """Return the standard set of command rules.

        Returns:
            Rules for rm -f, git commit messages, build-context grep/head/tail, and
            standalone true/echo.
        """
        # Update prompts/shared/rules/hooks.md if these command rules change.
        return [
            CommandRule(
                command="rm",
                blocked_flags=frozenset({"-f", "--force"}),
                message="rm -f is not allowed. MUST drop -f (rm, or rm -r for a directory).",
            ),
            CommandRule(
                command="git",
                message="Commit messages MUST be single-line with no body.",
                validator=validate_git_commit_message,
            ),
            CommandRule(
                command="git",
                message="MUST NOT read the commit message from a file (-F, --file) - MUST use an inline message.",
                validator=validate_git_commit_file_message,
            ),
            CommandRule(
                command="git",
                message="A commit message MUST NOT claim that the build, tests, checks or CI pass.",
                validator=validate_git_commit_pass_claim,
            ),
            CommandRule(
                command="git",
                message="A commit message MUST NOT list test names.",
                validator=validate_git_commit_test_name,
            ),
            CommandRule(
                command="cat",
                message="MUST read files with the Read tool, not cat.",
                validator=_is_standalone,
            ),
            CommandRule(
                command="grep",
                message="MUST NOT filter build output with grep - MUST capture the full output.",
                validator=_filters_build_output,
            ),
            CommandRule(
                command="head",
                message="MUST NOT filter build output with head - MUST capture the full output.",
                validator=_filters_build_output,
            ),
            CommandRule(
                command="head",
                message="MUST read files with the Read tool, not head.",
                validator=_is_standalone,
            ),
            CommandRule(
                command="tail",
                message="MUST NOT filter build output with tail - MUST capture the full output.",
                validator=_filters_build_output,
            ),
            CommandRule(
                command="tail",
                message="MUST read files with the Read tool, not tail.",
                validator=_is_standalone_tail,
            ),
            *(
                CommandRule(
                    command=command,
                    message=(
                        "MUST parse JSON in the shell with jq, not an inline python -c or node -e script "
                        "(e.g. `curl -s URL | jq '.field'`)."
                    ),
                    validator=_parses_stdin_json_inline,
                )
                for command in (*_INLINE_SCRIPT_FLAGS, "uv")
            ),
            CommandRule(
                command="true",
                message=(
                    "MUST NOT use `true` as a standalone command. When waiting on a background agent "
                    "or task, MUST end your turn - a completion notification resumes you "
                    "automatically."
                ),
                validator=_is_standalone,
            ),
            CommandRule(
                command="echo",
                message="MUST NOT use standalone echo. Make the next real call instead, or end your turn.",
                validator=_is_standalone,
            ),
        ]
