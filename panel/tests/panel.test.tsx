import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const VIEW = {
  mrs: [
    { label: 'atlas-api!45', url: 'https://gitlab.com/g/atlas-api/-/merge_requests/45', state: 'merged', title: 'feat: x', fresh: true },
    { label: 'ops!3', url: 'https://gitlab.com/g/ops/-/merge_requests/3', state: 'opened', title: null, fresh: false },
  ],
  counts: { merged: 1, to_merge: 1 },
  notes: [
    { title: 'plan', action: 'created', link: 'obsidian://open?vault=V&file=plan' },
    { title: 'edited', action: 'modified', link: 'obsidian://open?vault=V&file=edited' },
  ],
  todos: [{ text: 'Relire ops!3', next: true }],
  then: null,
  display: 'band',
}

const kept = new Map<string, unknown>()

function panes(on: On) {
  const open = new Set<string>()
  kept.clear()
  on('store.get', async (_, e) => ({ value: kept.get(e.key) }))
  on('store.set', async (_, e) => {
    kept.set(e.key, e.value)
    return { value: undefined }
  })
  on('session.id', async () => ({ value: 'sid' }))
  on('ui.open', async (_, e) => {
    open.add(e.id)
    return { value: { isPlaced: true as const } }
  })
  on('ui.close', async (_, e) => {
    open.delete(e.id)
    return { value: undefined }
  })
  on('ui.panes', async () => ({
    value: [...open].map(id => ({ id, title: id, isShown: true, isFocused: false, isPlaced: true })),
  }))
  return open
}

const PANE_PROPS = { title: 'White rabbit', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 20 }, view: {} }

const BAND = {
  component: 'AbovePrompt',
  props: { hasSurvey: false, isWorking: false, maxRows: 3, bodyColumns: 120, scroll: { offset: 0, bodyRows: 3 }, view: {} },
} as const

test('the band summarises the session and its button toggles the pane', async ($, on) => {
  const open = panes(on)
  on('process.run', async (_, e) => ({ value: { exitCode: 0, stdout: e.argv[1] === 'view' ? JSON.stringify(VIEW) : '', stderr: '' } }))
  await $.command.run({ command: 'rabbit', args: 'place band' })
  await $.command.run({ command: 'rabbit', args: '' })
  expect([...open]).toEqual(['white-rabbit'])

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'white-rabbit-panel', surface, ...BAND })
    expect(await ui.find({ key: 'open' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /▸ Relire ops!3/ })).toBeDefined()
    expect(await ui.find({ text: 'plan' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1 to merge/ })).toBeDefined()
    await ui.unmount()
  }

  const band = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...BAND })
  await band.press({ key: 'open' })
  expect([...open]).toEqual([])
  open.add('ghost')
  await band.press({ key: 'open' })
  expect([...open].sort()).toEqual(['ghost', 'white-rabbit'])
  await band.unmount()
})

test('the button reopens a pane closed behind its back', async ($, on) => {
  const open = panes(on)
  on('process.run', async () => ({ value: { exitCode: 0, stdout: JSON.stringify(VIEW), stderr: '' } }))
  await $.command.run({ command: 'rabbit', args: 'place band' })
  await $.command.run({ command: 'rabbit', args: '' })
  open.clear()
  const band = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...BAND })
  await band.press({ key: 'open' })
  expect([...open]).toEqual(['white-rabbit'])
  await band.unmount()
})

test('the pane lists the merge requests, notes and to-do, and a fresh merge is announced', async ($, on) => {
  panes(on)
  const toasts: string[] = []
  on('ui.toast', async (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('process.run', async () => ({ value: { exitCode: 0, stdout: JSON.stringify(VIEW), stderr: '' } }))
  await $.command.run({ command: 'rabbit', args: '' })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({
      plugin: 'white-rabbit-panel', surface, component: 'Pane', requestId: 'white-rabbit', props: PANE_PROPS as never,
    })
    expect(await ui.find({ type: 'Text', text: /▸ Relire ops!3/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /To-do 1/ })).toBeDefined()
    await ui.press({ key: 'tab-mr' })
    expect(kept.get('tab')).toBe('mr')
    expect((await ui.find({ type: 'Link', text: 'atlas-api!45' }))?.props.href).toBe(VIEW.mrs[0]?.url)
    expect(await ui.find({ type: 'Text', text: /Relire/ })).toBeUndefined()
    await ui.press({ key: 'tab-notes' })
    if (surface === 'terminal') {
      expect((await ui.find({ type: 'Link', text: 'plan' }))?.props.href).toBe(VIEW.notes[0]?.link)
    }
    expect(await ui.find({ type: 'Text', text: /MODIFIED 1/ })).toBeDefined()
    await ui.press({ key: 'tab-todo' })
    await ui.unmount()
  }
  expect(toasts).toEqual(['🐇 atlas-api!45 merged'])
})

test('nothing is drawn above the prompt when the session left nothing', async ($, on) => {
  panes(on)
  on('process.run', async () => ({ value: {
    exitCode: 0, stdout: JSON.stringify({ mrs: [], counts: { merged: 0, to_merge: 0 }, notes: [], todos: [], then: null }), stderr: '',
  } }))
  on('ui.render', async ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box key="engine" />
  })
  await $.command.run({ command: 'rabbit', args: '' })
  const ui = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...BAND })
  expect(await ui.find({ key: 'engine' })).toBeDefined()
  expect(await ui.find({ key: 'open' })).toBeUndefined()
  await ui.unmount()
})

test('/rabbit place moves the button out of the band', async ($, on) => {
  const open = panes(on)
  on('process.run', async () => ({ value: { exitCode: 0, stdout: JSON.stringify(VIEW), stderr: '' } }))
  on('ui.render', async ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box key="engine" />
  })
  await $.command.run({ command: 'rabbit', args: 'place nowhere' })
  await $.command.run({ command: 'rabbit', args: '' })
  await $.command.run({ command: 'rabbit', args: '' })

  const sites = {
    hint: { component: 'PromptHint', props: { isDraft: false, isWorking: false, hint: '? for shortcuts' } },
    mode: { component: 'SessionMode', props: { modes: ['focus'] } },
    turn: { component: 'TurnDuration', props: { word: 'Baked', durationMs: 64_000 } },
  } as const
  for (const [where, site] of Object.entries(sites)) {
    await $.command.run({ command: 'rabbit', args: `place ${where}` } as never)
    const band = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...BAND })
    expect(await band.find({ key: 'open' })).toBeUndefined()
    await band.unmount()
    const ui = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...site } as never)
    await ui.press({ key: 'open' })
    expect([...open]).toEqual(['white-rabbit'])
    await ui.press({ key: 'open' })
    expect([...open]).toEqual([])
    await ui.unmount()
  }
  const turn = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...sites.turn } as never)
  expect(await turn.find({ type: 'Text', text: /Baked for 1m 4s/ })).toBeDefined()
  await turn.unmount()
})

test('/rabbit place and /rabbit color cycle without an argument', async ($, on) => {
  panes(on)
  on('process.run', async () => ({ value: { exitCode: 0, stdout: JSON.stringify(VIEW), stderr: '' } }))
  const said = async (args: string) => ((await $.command.run({ command: 'rabbit', args })) as { text: string }).text

  expect(await said('place')).toMatch(/\(turn\)/)
  expect(await said('place')).toMatch(/\(band\)/)
  expect(await said('place hint')).toMatch(/\(hint\)/)
  expect(await said('place')).toMatch(/\(mode\)/)
  expect(await said('place nowhere')).toMatch(/Unknown place/)

  expect(await said('color')).toBe('Rabbit pane painted matrix.')
  expect(await said('color')).toBe('Rabbit pane painted night.')
  await $.command.run({ command: 'rabbit', args: '' })
  const ui = await $.ui.mount({
    plugin: 'white-rabbit-panel', surface: 'terminal', component: 'Pane', requestId: 'white-rabbit',
    props: PANE_PROPS as never,
  })
  expect((await ui.find({ key: 'body' }))?.props.backgroundColor).toBe('#1e1e2e')
  expect((await ui.find({ type: 'Text', text: / ▸ To-do 1 / }))?.props.backgroundColor).toBe('#89b4fa')
  await ui.unmount()
  expect(await said('color ember')).toBe('Rabbit pane painted ember.')
  expect(await said('color')).toBe('Rabbit pane painted default.')
})

test('/rabbit display moves MR, notes and next between the statusline, the band and nowhere', async ($, on) => {
  panes(on)
  let shown = 'band'
  const calls: string[][] = []
  on('process.run', async (_, e) => {
    calls.push([...e.argv])
    if (e.argv[1] === 'config') shown = e.argv[4] ?? shown
    return { value: { exitCode: 0, stdout: JSON.stringify({ ...VIEW, display: shown }), stderr: '' } }
  })
  await $.command.run({ command: 'rabbit', args: 'place band' })
  await $.command.run({ command: 'rabbit', args: '' })
  await $.command.run({ command: 'rabbit', args: '' })
  const said = async (args: string) => ((await $.command.run({ command: 'rabbit', args })) as { text: string }).text

  expect(await said('display')).toMatch(/\(off\)/)
  expect(calls).toContainEqual(['white-rabbit', 'config', 'set', 'display.summary', 'off'])
  const band = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...BAND })
  expect(await band.find({ key: 'open' })).toBeDefined()
  expect(await band.find({ type: 'Text', text: /Relire/ })).toBeUndefined()
  expect(await band.find({ type: 'Link', text: 'plan' })).toBeUndefined()
  await band.unmount()

  expect(await said('display')).toMatch(/\(statusline\)/)
  expect(await said('display band')).toMatch(/\(band\)/)
  const back = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...BAND })
  expect(await back.find({ type: 'Text', text: /▸ Relire ops!3/ })).toBeDefined()
  await back.unmount()
  expect(await said('display nowhere')).toMatch(/Unknown display/)
})

test('the button place and the palette are kept in the store', async ($, on) => {
  panes(on)
  on('process.run', async () => ({ value: { exitCode: 0, stdout: JSON.stringify(VIEW), stderr: '' } }))
  await $.command.run({ command: 'rabbit', args: 'place mode' })
  await $.command.run({ command: 'rabbit', args: 'color matrix' })
  expect(kept.get('placement')).toBe('mode')
  expect(kept.get('palette')).toBe('matrix')
})

test('the footer holds the rabbit button by default and Nebuchadnezzar when matrix is installed', async ($, on) => {
  panes(on)
  const calls: string[][] = []
  on('process.run', async (_, e) => {
    calls.push([...e.argv])
    return { value: { exitCode: 0, stdout: e.argv[1] === 'view' ? JSON.stringify(VIEW) : '', stderr: '' } }
  })
  on('command.register', async () => ({ value: undefined }))
  on('clock.every', async () => ({ value: undefined }))
  on('session.start', async (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ source: 'startup', cwd: '/tmp' } as never)
  await $.command.run({ command: 'rabbit', args: 'color matrix' })
  const footer = { component: 'SessionMode', props: { modes: [] } } as const
  const ui = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...footer } as never)
  expect(await ui.find({ key: 'open' })).toBeDefined()
  await ui.press({ key: 'neb' })
  expect(calls).toContainEqual(['matrix', 'focus', 'neb', '--raise'])
  await ui.unmount()

  await $.command.run({ command: 'rabbit', args: 'place band' })
  const after = await $.ui.mount({ plugin: 'white-rabbit-panel', surface: 'terminal', ...footer } as never)
  expect(await after.find({ key: 'open' })).toBeUndefined()
  expect(await after.find({ key: 'neb' })).toBeDefined()
  await after.unmount()
  const pane = await $.ui.mount({
    plugin: 'white-rabbit-panel', surface: 'terminal', component: 'Pane', requestId: 'white-rabbit',
    props: PANE_PROPS as never,
  })
  expect(await pane.find({ key: 'neb' })).toBeUndefined()
  await pane.unmount()
})
