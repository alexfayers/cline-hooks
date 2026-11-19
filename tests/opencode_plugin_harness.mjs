// Drives the cline-hooks opencode bridge plugin against a fake opencode.
// Usage: node opencode_plugin_harness.mjs <plugin.ts> <steps.json>
// Fires each { hook, input, output } step in order (hook "event" takes { event } as its input) and prints
// { results, prompts } as JSON: each step's output (or thrown error message) and every prompt sent back.
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const [script, stepsFile] = process.argv.slice(2)
const prompts = []
const client = {
  session: {
    get: async ({ path }) => ({ data: path.id.startsWith('child') ? { parentID: 'main' } : {} }),
    promptAsync: async ({ path, body }) => prompts.push({ id: path.id, text: body.parts[0].text }),
  },
  mcp: { status: async () => ({ data: { 'my.memory': { status: 'connected' } } }) },
}
const module = await import(pathToFileURL(script).href)
const hooks = await module.ClineHooks({ client, directory: '/work/project' })
const results = []
for (const { hook, input, output } of JSON.parse(readFileSync(stepsFile, 'utf8'))) {
  try {
    await hooks[hook](input, output)
    results.push(output ?? null)
  } catch (error) {
    results.push({ error: error.message })
  }
}
console.log(JSON.stringify({ results, prompts }))
