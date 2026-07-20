---
name: confirm-push
description: Confirm with the user before running a git push. Invoke this only after the user has explicitly approved THIS specific push - it unblocks the very next git push command and nothing else.
---

# confirm-push

**Invoke this only after the user has explicitly approved the push you are about to run.** If you have not asked, or the user has not said yes to pushing right now, stop and ask first - do not invoke this skill speculatively or as a way to get past the block.

This skill exists because a PreToolUse hook cannot read chat or otherwise verify that a human actually approved a push - it can only require a distinct, logged action immediately beforehand. Invoking this skill is that action.

The confirmation is one-shot: it is consumed by the very next `git push`, so a second push - even later in the same task - needs a fresh approval and a fresh invocation of this skill. Do not invoke it preemptively "just in case" for a push you have not asked about yet.
