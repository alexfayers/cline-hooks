// Drives the cline-hooks pi bridge extension against a fake pi.
// Usage: node pi_extension_harness.mjs <extension.ts> <tool-input.json> [steps.json]
// Runs one tool_call then its tool_result; then a session_start and a session_compact; prints { queued, notified, input, blocked, content, structuredContent } as JSON.
import { readFileSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

// With steps.json (a list of { event, payload }), it instead fires those events in order and prints { queued, results } with each handler's return value.
// A step may set `defer` (do not wait for the handler until a later { join: true } step) or `writeFile` (create that file, releasing a hook that waits for it).
const [script, inputFile, stepsFile] = process.argv.slice(2)
const handlers = {}
const queued = []
const notified = []
const pi = { on: (event, handler) => (handlers[event] = handler), sendMessage: (message) => queued.push(message.content) }
const ctx = {
  cwd: '/work/project',
  ui: { notify: (message) => notified.push(message) },
  getContextUsage: () => undefined,
  sessionManager: { getSessionId: () => 's1', getSessionFile: () => '', getSessionName: () => '' },
}
const input = JSON.parse(readFileSync(inputFile, 'utf8'))
const module = await import(pathToFileURL(script).href)
module.default(pi)
if (stepsFile) {
  const results = []
  const deferred = []
  for (const { event, payload, defer, join, writeFile } of JSON.parse(readFileSync(stepsFile, 'utf8'))) {
    if (writeFile) writeFileSync(writeFile, '')
    if (join) await Promise.all(deferred)
    if (!event) continue
    const index = results.push(null) - 1
    const run = Promise.resolve(handlers[event]?.(payload, ctx)).then((value) => (results[index] = value ?? null))
    if (defer) deferred.push(run)
    else await run
  }
  await Promise.all(deferred)
  console.log(JSON.stringify({ queued, results }))
  process.exit(0)
}
const call = { toolName: 'delegate_agent', toolCallId: 'c1', input }
const callResult = await handlers.tool_call(call, ctx)
const result = await handlers.tool_result(
  { ...call, content: [{ type: 'text', text: 'done' }], structuredContent: { ok: true }, isError: false },
  ctx,
)
await handlers.session_start({ reason: 'startup' }, ctx)
await handlers.session_compact({}, ctx)
console.log(JSON.stringify({ queued, notified, input: call.input, blocked: callResult?.block === true, content: result?.content ?? null, structuredContent: result?.structuredContent ?? null }))
