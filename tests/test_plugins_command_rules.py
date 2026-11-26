from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.plugin import collect_contributions
from cline_hooks.handlers.commands import CommandRule, check_rules, extract_commands, parse_command
from cline_hooks.plugins.command_rules import CommandRulesPlugin, CommandRulesSpec

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def rules(use_plugins: Callable[..., None]) -> list[CommandRule]:
    """The command rules collected with only CommandRulesPlugin loaded.

    Returns:
        Every rule the plugin contributes, in contribution order.
    """
    use_plugins(CommandRulesPlugin())
    return [
        rule for contribution in collect_contributions(CommandRulesSpec.command_rules, list) for rule in contribution
    ]


class TestCommandRulesPluginCommandRules:
    def test_includes_grep_rule(self, rules: list[CommandRule]) -> None:
        commands = [r.command for r in rules]
        assert "grep" in commands


class TestCommandRulesPluginGitCommitMessageRule:
    def test_single_line_commit_message_is_allowed(self, rules: list[CommandRule]) -> None:
        commands = extract_commands(parse_command('git commit -m "single line message"'))
        assert check_rules(commands, rules) is None

    def test_multi_line_commit_message_is_blocked(self, rules: list[CommandRule]) -> None:
        commands = extract_commands(parse_command('git commit -m "line one\nline two"'))
        violated = check_rules(commands, rules)
        assert violated is not None
        assert violated.command == "git"
        assert violated.message == "Commit messages MUST be single-line with no body."


def _violated(rules: list[CommandRule], command: str) -> CommandRule | None:
    return check_rules(extract_commands(parse_command(command)), rules)


class TestCommandRulesPluginCommitMessageContentRule:
    @pytest.mark.parametrize(
        "message",
        [
            "feat: add parser, all tests pass",
            "fix: handle empty input; build passes",
            "fix: retry the call (CI green)",
            "chore: bump deps. Checks passed.",
            "fix: lint is passing",
            "refactor: split parser - everything green",
            "fix: tests have passed",
            "chore: everything is green",
            "fix: the build was green",
            "fix: CI has succeeded",
            "chore: CI was successful",
            "fix: tests currently pass",
            "fix: CI still passes",
            "fix: make the build pass on windows, checks pass",
            "fix: ensure the build works - tests pass",
            "fix: add the retry loop (all existing tests pass)",
        ],
    )
    def test_commit_message_claiming_a_pass_is_blocked(self, rules: list[CommandRule], message: str) -> None:
        violated = _violated(rules, f'git commit -m "{message}"')
        assert violated is not None
        assert "MUST NOT claim that the build, tests, checks or CI pass" in violated.message

    @pytest.mark.parametrize(
        "message",
        [
            "feat: add parser",
            "fix: make the build pass on windows",
            "fix: ensure tests pass on Windows",
            "test: verify the build passes without network",
            "fix: skip the step if checks pass",
            "fix: stop the flaky test failing",
            "docs: explain how CI checks run",
            "fix: ensure the retry loop in the parser still handles every empty input so that all the tests pass",
            "fix: prevent tests passing without assertions",
            "fix: stop the flaky test from passing by accident when the setup is skipped",
            "feat: test pass-through of the config",
            "fix: check that tests pass",
            "fix: confirm the tests pass",
        ],
    )
    def test_commit_message_without_a_pass_claim_is_allowed(self, rules: list[CommandRule], message: str) -> None:
        assert _violated(rules, f'git commit -m "{message}"') is None

    @pytest.mark.parametrize(
        "message",
        [
            "test: add test_parses_empty_input",
            "test: rename tests/test_parser.py::test_empty",
            "test: add it('parses empty input')",
            "test: add test.each([1])('accepts input', fn)",
            "test: add describe.each([[1, 2]]) ('accepts input', fn)",
            "test: add it.each\\`a | b\\`('accepts input', fn)",
        ],
    )
    def test_commit_message_listing_a_test_name_is_blocked(self, rules: list[CommandRule], message: str) -> None:
        violated = _violated(rules, f'git commit -m "{message}"')
        assert violated is not None
        assert "MUST NOT list test names" in violated.message

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -m ok -m 'tests pass'",
            "git commit --message='tests pass'",
            "git commit --message 'tests pass'",
            "git commit -m'tests pass'",
            "git commit -am 'tests pass'",
            "git -C /repo commit -m 'tests pass'",
            'git add . && git commit -m "$(cat <<EOF\ntests pass\nEOF\n)"',
        ],
    )
    def test_every_form_of_message_flag_is_checked(self, rules: list[CommandRule], command: str) -> None:
        assert _violated(rules, command) is not None

    @pytest.mark.parametrize(
        "command",
        ["git log -m 'tests pass'", "git log --grep commit -m 'tests pass'", "git commit --amend --no-edit"],
    )
    def test_other_commands_and_messageless_commits_are_allowed(self, rules: list[CommandRule], command: str) -> None:
        assert _violated(rules, command) is None

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -F message.txt",
            "git commit --file message.txt",
            "git commit --file=message.txt",
            "git commit -aF message.txt",
            "git commit -Fmessage.txt",
            "git -C /repo commit -F -",
        ],
    )
    def test_commit_message_read_from_a_file_is_blocked(self, rules: list[CommandRule], command: str) -> None:
        violated = _violated(rules, command)
        assert violated is not None
        assert "inline message" in violated.message

    @pytest.mark.parametrize("command", ["git log -F pattern", "git commit -m '-Fix the parser'", "git commit -mF"])
    def test_other_uses_of_the_file_flag_letter_are_allowed(self, rules: list[CommandRule], command: str) -> None:
        assert _violated(rules, command) is None


class TestCommandRulesPluginInlineJsonRule:
    @pytest.mark.parametrize(
        "command",
        [
            "curl -s https://example.test/api | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"id\"])'",
            "gh api repos/o/r | python -c 'import json,sys; print(json.loads(sys.stdin.read()))'",
            'cat out.json | node -e \'console.log(JSON.parse(require("fs").readFileSync(0, "utf8")).id)\'',
            "node --eval 'JSON.parse(require(\"fs\").readFileSync(0))' < out.json",
            "curl -s x | python3 -c 'import json,sys\ntext = sys.stdin.read().strip()\nprint(json.loads(text))'",
            "curl -s x | python3 -c 'import json,sys\nfor line in sys.stdin:\n    json.loads(line)'",
            'curl -s x | node -e \'JSON.parse(require("fs").readFileSync(process.stdin.fd, "utf8"))\'',
            "curl -s x | python3 -c 'import json,os,sys\njson.load(os.fdopen(sys.stdin.fileno()))'",
            "curl -s x | python3 -c 'import json\nwith open(0) as f:\n    json.load(f)'",
            "curl -s x | python3 -c 'import json,sys\nraw = sys.stdin.read()\nbody = raw.strip()\njson.loads(body)'",
            'curl -s x | node -e \'let d=""; process.stdin.on("data", c => d += c).on("end", () => JSON.parse(d))\'',
            'curl -s x | node -e \'const text = require("fs").readFileSync("/dev/stdin", "utf8"); JSON.parse(text)\'',
            "python3 -c 'import json,sys; json.load(sys.stdin)' < out.json",
            "python3 -c 'import json,sys; json.load(sys.stdin)' <<EOF\n{\"id\": 1}\nEOF\n",
            "/usr/bin/python3 -c 'import json,sys; json.load(sys.stdin)'",
            "curl -s x | python3 -c 'import json\nimport sys\nprint(json.load(sys.stdin))'",
            "gh api repos/o/r | uv run python -c 'import json,sys; print(json.load(sys.stdin))'",
            "curl -s x | uv run --with requests python3 -c 'import json,sys; json.load(sys.stdin)'",
            "curl -s x | uv run --python 3.12 python -c 'import json,sys; json.load(sys.stdin)'",
            "curl -s x | python3 -c 'from json import load\nimport sys\nprint(load(sys.stdin))'",
            "curl -s x | python3 -c 'from json import loads as parse\nimport sys\nparse(sys.stdin.read())'",
            "curl -s x | python3 -c 'import json as j, sys; j.load(sys.stdin)'",
            "curl -s x | python3 -c 'import json\nfrom sys import stdin\njson.load(stdin)'",
            "curl -s x | python3 -c 'import json\ndata = input()\njson.loads(data)'",
            "curl -s x | python3 -c 'import json\njson.load(open(\"/dev/stdin\"))'",
        ],
    )
    def test_inline_script_parsing_json_from_stdin_is_blocked(self, rules: list[CommandRule], command: str) -> None:
        violated = _violated(rules, command)
        assert violated is not None
        assert "jq" in violated.message

    @pytest.mark.parametrize(
        "command",
        [
            "curl -s x | uv run script.py",
            "curl -s x | uv run --script parse.py",
            "curl -s x | python3 script.py",
            "curl -s x | uv run python script.py",
            "curl -s x | uv run script.py -c 'json.load(sys.stdin)'",
            "curl -s x | uv run --with requests python -c 'print(1)'",
            "curl -s x | uv run --with python script.py -c 'json.load(sys.stdin)'",
            "curl -s x | python3 -c 'print(\"json.load(sys.stdin)\")'",
            "curl -s x | python3 -c 'from json import dumps\nimport sys\nprint(dumps(sys.stdin.read()))'",
            "curl -s x | python3 -c 'import sys\nfrom foo import load\nprint(load(sys.stdin))'",
            "python3 -c 'import json; print(json.loads(\"{}\"))'",
            "curl -s x | python3 -c 'import json; print(json.loads(\"{}\"))'",
            "python3 -c 'import json; json.load(open(\"a.json\"))' < out.json",
            "curl -s x | python3 -c 'import json,sys\nprint(sys.stdin.read())\nprint(json.loads(\"[1]\"))'",
            "curl -s x | python3 -c 'import json,sys\nprint(json.load(open(\"a.json\")), len(sys.stdin.read()))'",
            "curl -s x | node -e 'JSON.parse(\"{}\")'",
            "node --eval 'JSON.parse(1)' < out.json",
            "curl -s x | node -e 'console.log(JSON.parse(\"{}\"), process.stdin.isTTY)'",
            "curl -s x | node -e 'const data = \"{}\"; console.log(JSON.parse(data), process.stdin.isTTY)'",
            'curl -s x | node -e \'let d = "{}"; process.stdin.on("data", c => c); JSON.parse(d)\'',
            'curl -s x | node -e \'const t = require("fs").readFileSync("a"); process.stdin.resume(); JSON.parse(t)\'',
            "curl -s x | node -e 'console.log(\"JSON.parse(x)\")'",
            'curl -s x | node -e \'const data = process.stdin.isTTY ? "{}" : "[]"; JSON.parse(data)\'',
            'curl -s x | node -e \'const live = process.stdin.readable; JSON.parse(live ? "{}" : "[]")\'',
            'curl -s x | python3 -c \'import json,sys\ndata = "{}" if sys.stdin.isatty() else "[]"\njson.loads(data)\'',
            'curl -s x | python3 -c \'import json\nfrom sys import stdin\njson.loads("{}" if stdin.closed else "[]")\'',
            "curl -s x | python3 script.py -c 'json.load(sys.stdin)'",
            "curl -s x | node script.js -e 'JSON.parse(1)'",
            "curl -s x | python3 -m json.tool",
            "curl -s x | python3 -c 'import sys; print(sys.stdin.read().upper())'",
            "python3 -c 'import json; print(json.dumps({\"a\": 1}))'",
            "python3 -c 'import json; print(json.load(open(\"out.json\")))'",
            "node -e 'console.log(JSON.stringify({a: 1}))'",
            "node script.js < out.json",
            "curl -s x | jq .id",
            "python3 - <<EOF\nimport json,sys\nprint(json.load(sys.stdin))\nEOF\n",
            "tee notes.md <<EOF\npython3 -c 'json.load(sys.stdin)'\nEOF\n",
            "printf %s \"curl x | python3 -c 'json.load(sys.stdin)'\"",
            "git commit -m 'fix: replace python3 -c json.load(sys.stdin) with jq'",
            "rg 'python3 -c .*json.load' docs",
        ],
    )
    def test_scripts_tools_and_snippets_without_piped_json_parsing_are_allowed(
        self, rules: list[CommandRule], command: str
    ) -> None:
        assert _violated(rules, command) is None
