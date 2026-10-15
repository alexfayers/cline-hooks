// Drives the cline-hooks pi bridge extension against a fake pi.
// Usage: node pi_extension_harness.mjs <extension.ts> <tool-input.json>
// Runs one tool_call then its tool_result; prints { input, blocked, content } as JSON.
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const [script, inputFile] = process.argv.slice(2)
const handlers = {}
const pi = { on: (event, handler) => (handlers[event] = handler), sendMessage: () => {} }
const ctx = {
  cwd: '/work/project',
  getContextUsage: () => undefined,
  sessionManager: { getSessionId: () => 's1', getSessionFile: () => '', getSessionName: () => '' },
}
const input = JSON.parse(readFileSync(inputFile, 'utf8'))
const module = await import(pathToFileURL(script).href)
module.default(pi)
const call = { toolName: 'delegate_agent', toolCallId: 'c1', input }
const callResult = await handlers.tool_call(call, ctx)
const result = await handlers.tool_result(
  { ...call, content: [{ type: 'text', text: 'done' }], isError: false },
  ctx,
)
console.log(JSON.stringify({ input: call.input, blocked: callResult?.block === true, content: result?.content ?? null }))
