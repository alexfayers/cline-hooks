// Drives the cline-hooks opencode bridge plugin against a fake opencode 2.x plugin context.
// Usage: node opencode_plugin_harness.mjs <plugin.ts> <steps.json> <root>
// Fires each { hook, event } step in order, where hook is "<domain>.<name>" (for example
// "tool.execute.before"), and prints { results, synthetic } as JSON: each step's event after the
// hook ran (or its thrown error message) and every synthetic message the plugin added.
// Sessions live in <root>/project, except "elsewhere" in <root>/other; ids starting "child" are children of "main".
// Ids starting "resumed" are sessions that have run before.
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const [script, stepsFile, root] = process.argv.slice(2)
const hooks = new Map()
const synthetic = []
const register = (domain) => async (name, callback) => {
  hooks.set(`${domain}.${name}`, callback)
  return { dispose: async () => {} }
}
const ctx = {
  location: { directory: `${root}/project` },
  session: {
    get: async ({ sessionID }) => ({
      id: sessionID,
      ...(sessionID.startsWith('child') ? { parentID: 'main' } : {}),
      ...(sessionID.startsWith('resumed') ? { time: { idle: 1 } } : {}),
      location: { directory: `${root}/${sessionID === 'elsewhere' ? 'other' : 'project'}` },
    }),
    synthetic: async (input) => synthetic.push(input),
    hook: register('session'),
  },
  tool: { hook: register('tool') },
  mcp: { list: async () => ({ data: [{ name: 'my.memory', status: 'connected' }] }) },
}
const plugin = (await import(pathToFileURL(script).href)).default
await plugin.setup(ctx)
const results = []
for (const { hook, event } of JSON.parse(readFileSync(stepsFile, 'utf8'))) {
  try {
    await hooks.get(hook)(event)
    results.push(event)
  } catch (error) {
    results.push({ error: error.message })
  }
}
console.log(JSON.stringify({ id: plugin.id, registered: [...hooks.keys()], results, synthetic }))
