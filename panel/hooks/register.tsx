import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { Display, Mr, Note, Palette, Placement, Tab, View } from '../types'

const PANE = 'white-rabbit'
const TITLE = 'White rabbit'
const TABS: { id: Tab; glyph: string; label: string }[] = [
  { id: 'todo', glyph: '▸', label: 'To-do' },
  { id: 'mr', glyph: '⇗', label: 'MR' },
  { id: 'notes', glyph: '▤', label: 'Notes' },
]
const REFRESH_MS = 20_000

const view = atom({ plugin: 'white-rabbit-panel', key: 'view' } as const, null)
const announced = atom({ plugin: 'white-rabbit-panel', key: 'announced' } as const, [])
const placement = atom({ plugin: 'white-rabbit-panel', key: 'placement' } as const, 'mode')
const palette = atom({ plugin: 'white-rabbit-panel', key: 'palette' } as const, 'default')
const tab = atom({ plugin: 'white-rabbit-panel', key: 'tab' } as const, 'todo')
const folds = atom({ plugin: 'white-rabbit-panel', key: 'folds' } as const, {})
const FOLDED_BY_DEFAULT = ['mr-merged', 'mr-closed']
const neb = atom({ plugin: 'white-rabbit-panel', key: 'neb' } as const, false)

type Colors = { background?: string; accent: string; hover?: string; rule?: string; text?: string; muted?: string; merged: string; opened: string }

const PALETTES: Record<Palette, Colors> = {
  default: { accent: 'cyan', merged: 'green', opened: 'yellow' },
  matrix: { background: '#04111b', accent: '#2ea7db', hover: '#7fb3c4', rule: '#26566e', text: '#d8f0f8', muted: '#7fb3c4', merged: '#78d8c0', opened: '#f0b040' },
  night: { background: '#1e1e2e', accent: '#89b4fa', merged: 'green', opened: 'yellow' },
  forest: { background: '#1b2b22', accent: '#8fd694', merged: 'green', opened: 'yellow' },
  ember: { background: '#2b1d16', accent: '#f5a97f', merged: 'green', opened: 'yellow' },
}

const PLACEMENTS: Record<Placement, string> = {
  band: 'in the band above the prompt',
  hint: 'at the end of the hint line under the prompt',
  mode: 'with the mode labels at the right of the prompt footer',
  turn: 'after the duration line closing each turn',
}

const DISPLAYS: Record<Display, string> = {
  statusline: 'MR, notes and next action shown in the statusline',
  band: 'MR, notes and next action shown in the band above the prompt',
  off: 'MR, notes and next action hidden (the pane still has them)',
}


async function load($: EngineInterface): Promise<View | null> {
  try {
    const { exitCode, stdout } = await $.process.run(['white-rabbit', 'view', await $.session.id()],
      { timeoutMs: 5_000 })
    return exitCode === 0 && stdout.trim() ? (JSON.parse(stdout) as View) : null
  } catch {
    return null
  }
}

async function refresh($: EngineInterface) {
  const next = await load($)
  if (next === null) {
    return
  }
  await update($, view, () => next)
  const fresh = next.mrs.filter(mr => mr.fresh).map(mr => mr.url)
  const before = await read($, announced)
  for (const mr of next.mrs.filter(mr => mr.fresh && !before.includes(mr.url))) {
    $.ui.toast(`🐇 ${mr.label} merged`)
  }
  await update($, announced, () => fresh)
}

async function toggle($: EngineInterface) {
  if ((await $.ui.panes()).some(pane => pane.id === PANE)) {
    await $.ui.close({ id: PANE })
    return
  }
  await refresh($)
  await $.ui.open({ id: PANE, title: TITLE })
}

function isEmpty(current: View | null) {
  return current === null
    || (current.mrs.length === 0 && current.notes.length === 0 && current.todos.length === 0 && !current.then)
}

function formatDuration(ms: number) {
  const seconds = Math.round(ms / 1000)
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

function following<K extends string>(choices: Record<K, unknown>, current: K): K {
  const names = Object.keys(choices) as K[]
  return names[(names.indexOf(current) + 1) % names.length] ?? current
}

async function detectNeb($: EngineInterface) {
  try {
    const { exitCode } = await $.process.run(['which', 'matrix'], { timeoutMs: 2_000 })
    await update($, neb, () => exitCode === 0)
  } catch {
    await update($, neb, () => false)
  }
}

async function openNeb($: EngineInterface) {
  try {
    const { exitCode } = await $.process.run(['matrix', 'focus', 'neb', '--raise'], { timeoutMs: 10_000 })
    if (exitCode !== 0) {
      $.ui.toast('neb could not be brought to the front')
    }
  } catch {
    $.ui.toast('neb could not be brought to the front')
  }
}

async function restore($: EngineInterface) {
  const savedPlace = await $.store.get('placement')
  if (typeof savedPlace === 'string' && savedPlace in PLACEMENTS) {
    await update($, placement, () => savedPlace as Placement)
  }
  const savedPalette = await $.store.get('palette')
  if (typeof savedPalette === 'string' && savedPalette in PALETTES) {
    await update($, palette, () => savedPalette as Palette)
  }
  const savedFolds = await $.store.get('folds')
  if (savedFolds !== null && typeof savedFolds === 'object' && !Array.isArray(savedFolds)) {
    await update($, folds, () => savedFolds as Record<string, boolean>)
  }
  const savedTab = await $.store.get('tab')
  if (TABS.some(known => known.id === savedTab)) {
    await update($, tab, () => savedTab as Tab)
  }
}

function isFolded(current: Record<string, boolean>, id: string) {
  return current[id] ?? FOLDED_BY_DEFAULT.includes(id)
}

async function fold($: EngineInterface, id: string) {
  const next = await update($, folds, current => ({ ...current, [id]: !isFolded(current, id) }))
  await $.store.set('folds', next)
}

async function showTab($: EngineInterface, wanted: Tab) {
  await update($, tab, () => wanted)
  await $.store.set('tab', wanted)
}

async function place($: EngineInterface, args: string) {
  const asked = args.trim()
  if (asked && !(asked in PLACEMENTS)) {
    return `Unknown place "${asked}": /rabbit place [${Object.keys(PLACEMENTS).join('|')}], none to cycle.`
  }
  const wanted = (asked || following(PLACEMENTS, await read($, placement))) as Placement
  await update($, placement, () => wanted)
  await $.store.set('placement', wanted)
  return `Rabbit button moved ${PLACEMENTS[wanted]} (${wanted}).`
}

async function paint($: EngineInterface, args: string) {
  const asked = args.trim()
  if (asked && !(asked in PALETTES)) {
    return `Unknown palette "${asked}": /rabbit color [${Object.keys(PALETTES).join('|')}], none to cycle.`
  }
  const wanted = (asked || following(PALETTES, await read($, palette))) as Palette
  await update($, palette, () => wanted)
  await $.store.set('palette', wanted)
  return `Rabbit pane painted ${wanted}.`
}

async function display($: EngineInterface, args: string) {
  const asked = args.trim()
  if (asked && !(asked in DISPLAYS)) {
    return `Unknown display "${asked}": /rabbit display [${Object.keys(DISPLAYS).join('|')}], none to cycle.`
  }
  const current = (await read($, view))?.display ?? 'statusline'
  const wanted = (asked || following(DISPLAYS, current)) as Display
  try {
    const { exitCode, stdout } = await $.process.run(['white-rabbit', 'config', 'set', 'display.summary', wanted],
      { timeoutMs: 5_000 })
    if (exitCode !== 0) {
      return `Display stays ${current}: ${stdout.trim()}`
    }
  } catch {
    return `Display stays ${current}: white-rabbit could not be run.`
  }
  await refresh($)
  return `${DISPLAYS[wanted]} (${wanted}).`
}

function fitting(notes: Note[], budget: number) {
  const shown: Note[] = []
  let used = 0
  for (const note of notes) {
    const width = (note.title ?? '?').length + 3
    if (shown.length > 0 && used + width > budget) {
      break
    }
    shown.push(note)
    used += width
  }
  return shown
}

function mrColor(mr: Mr, colors: Colors) {
  if (mr.state === 'merged') return colors.merged
  if (mr.state === 'opened') return colors.opened
  return undefined
}

function hovered(colors: Colors) {
  return colors.hover ? { hover: { color: colors.hover, bold: true } } : {}
}

async function lit($: EngineInterface) {
  return hovered(PALETTES[await read($, palette)])
}

function secondary(colors: Colors) {
  return colors.muted ? { color: colors.muted } : { dimColor: true }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await restore($)
    await detectNeb($)
    await $.command.register({ name: 'rabbit', description: 'Show or hide the white-rabbit pane; /rabbit place cycles its button, /rabbit color its palette, /rabbit display where MR, notes and next show' })
    $.clock.every(REFRESH_MS, () => void refresh($))
    await refresh($)
    return started
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    await refresh($)
    return done
  })

  on('command.run', { command: 'rabbit' }, async ($, e) => {
    const [verb, ...rest] = e.args.trim().split(/\s+/)
    if (verb === 'place') {
      return { text: await place($, rest.join(' ')) }
    }
    if (verb === 'display') {
      return { text: await display($, rest.join(' ')) }
    }
    if (verb === 'color') {
      return { text: await paint($, rest.join(' ')) }
    }
    await toggle($)
    return { text: 'White-rabbit pane toggled.' }
  })

  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    if (await read($, placement) !== 'hint') {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    const hover = await lit($)
    return (
      <Box key="hint" flexDirection="row" gap={1}>
        <Text dimColor wrap="truncate-end">{e.props.hint}</Text>
        <Button key="open" plain dimColor label="◧ rabbit" onPress={() => toggle($)} {...hover} />
      </Box>
    )
  })

  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const inMode = await read($, placement) === 'mode'
    const withNeb = await read($, neb)
    if (!inMode && !withNeb) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    const hover = await lit($)
    return (
      <Box key="mode" flexDirection="row" gap={1}>
        {e.props.modes.length > 0 && <Text dimColor>{e.props.modes.join(' & ')}</Text>}
        {withNeb && <Button key="neb" plain dimColor label="⇱ Nebuchadnezzar" onPress={() => openNeb($)} {...hover} />}
        {inMode && <Button key="open" plain dimColor label="◧ rabbit" onPress={() => toggle($)} {...hover} />}
      </Box>
    )
  })

  on('ui.render', { component: 'TurnDuration' }, async ($, e, next) => {
    if (await read($, placement) !== 'turn') {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    const hover = await lit($)
    return (
      <Box key="turn" flexDirection="row" gap={1}>
        <Text dimColor>{e.props.word} for {formatDuration(e.props.durationMs)}</Text>
        <Button key="open" plain dimColor label="◧ rabbit" onPress={() => toggle($)} {...hover} />
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const current = await read($, view)
    const inBand = await read($, placement) === 'band'
    const summary = current?.display === 'band' && !isEmpty(current) ? current : null
    if (e.props.hasSurvey || isEmpty(current) || (!inBand && summary === null)) {
      return next(e)
    }
    const colors = PALETTES[await read($, palette)]
    const muted = secondary(colors)
    const { Box, Button, Link, Text } = $.ui.resolve(e)
    const button = inBand && <Button key="open" plain label="◧ rabbit" onPress={() => toggle($)} {...hovered(colors)} />
    if (summary === null) {
      return <Box flexDirection="row">{button}</Box>
    }
    const { merged, to_merge } = summary.counts
    const pending = summary.mrs.filter(mr => mr.state !== 'merged' || mr.fresh)
    const notes = fitting(summary.notes, e.props.bodyColumns - (inBand ? 18 : 8))
    const upcoming = summary.todos.find(todo => todo.next)
    const others = summary.todos.length - 1
    const label = (text: string) => <Text bold color={colors.accent}>{text}</Text>

    const rows = [
      merged + to_merge > 0 && (
        <Box key="mr" flexDirection="row" gap={1}>
          {label('MR:')}
          {merged > 0 && <Text color={colors.merged}>✓ {merged} merged</Text>}
          {to_merge > 0 && <Text color={colors.opened}>● {to_merge} to merge</Text>}
          {pending.map(mr => (
            <Text key={mr.url} strikethrough={mr.fresh} color={colors.text}><Link href={mr.url} label={mr.label} /></Text>
          ))}
        </Box>
      ),
      summary.notes.length > 0 && (
        <Box key="notes" flexDirection="row" gap={1}>
          {label('Notes:')}
          {notes.map(note => (
            note.link
              ? <Link key={note.link} href={note.link} label={note.title ?? '?'} />
              : <Text key={`note-${note.title}`} color={colors.text}>{note.title ?? '?'}</Text>
          ))}
          {summary.notes.length > notes.length && <Text {...muted}>+{summary.notes.length - notes.length}</Text>}
        </Box>
      ),
      upcoming && (
        <Box key="next" flexDirection="row" gap={1}>
          {label('Next:')}
          <Text bold color={colors.text} wrap="truncate-end">▸ {upcoming.text}</Text>
          {others > 0 && <Text {...muted}>(+{others})</Text>}
        </Box>
      ),
      !upcoming && summary.then && (
        <Box key="then" flexDirection="row" gap={1}>
          {label('Then:')}
          <Text {...muted} wrap="truncate-end">◦ {summary.then}</Text>
        </Box>
      ),
    ].filter(Boolean)

    return (
      <Box key="band" flexDirection="row" gap={1}>
        {button}
        <Box flexDirection="column">{rows}</Box>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const current = await read($, view)
    const shown = await read($, tab)
    const colors = PALETTES[await read($, palette)]
    const muted = secondary(colors)
    const ink = colors.background ?? 'black'
    const rule = colors.rule ? { color: colors.rule } : { dimColor: true }
    const { Box, Button, Link, Text } = $.ui.resolve(e)
    const width = e.props.bodyColumns - 2
    const todos = current?.todos ?? []
    const mrs = current?.mrs ?? []
    const notes = current?.notes ?? []
    const counts: Record<Tab, number> = { todo: todos.length, mr: mrs.length, notes: notes.length }

    const folded = await read($, folds)
    const section = (id: string, title: string, count: number, body: () => RenderChildren) => {
      if (count === 0) {
        return null
      }
      const closed = isFolded(folded, id)
      const label = ` ${closed ? '▸' : '▾'} ${title} ${count} `
      return (
        <Box key={id} flexDirection="column">
          <Box key={`${id}-head`} flexDirection="row">
            <Button key={`fold-${id}`} plain label={label} onPress={() => fold($, id)}
              hover={{ color: colors.accent, bold: true }} />
            <Text {...rule}>{'─'.repeat(Math.max(0, width - label.length))}</Text>
          </Box>
          {!closed && body()}
        </Box>
      )
    }
    const empty = (text: string) => <Text {...muted}>{text}</Text>

    const tabs = (
      <Box key="tabs" flexDirection="row" gap={1}>
        {TABS.map(({ id, glyph, label }) => {
          const caption = `${glyph} ${label} ${counts[id]}`
          return id === shown
            ? <Text key={`tab-${id}`} bold color={ink} backgroundColor={colors.accent}> {caption} </Text>
            : (
              <Box key={`tab-${id}-zone`}>
                <Button key={`tab-${id}`} plain label={` ${caption} `} onPress={() => showTab($, id)} {...hovered(colors)} />
              </Box>
            )
        })}
      </Box>
    )

    const todoTab = () => (todos.length === 0 && !current?.then)
      ? empty('Nothing expected from you.')
      : (
        <Box key="todo" flexDirection="column" gap={1}>
          {section('todo-next', 'NEXT', todos.length, () => todos.map(todo => todo.next
            ? <Text key={todo.text} bold color={colors.merged}>▸ {todo.text}</Text>
            : <Text key={todo.text} color={colors.text}>○ {todo.text}</Text>))}
          {section('todo-then', 'THEN', current?.then ? 1 : 0, () => <Text {...muted}>◦ {current?.then}</Text>)}
        </Box>
      )

    const mrRow = (mr: Mr) => (
      <Box key={mr.url} flexDirection="column">
        <Box flexDirection="row" gap={1}>
          <Text bold strikethrough={mr.fresh} color={ink}
            backgroundColor={mr.state === 'opened' ? colors.merged : colors.muted ?? 'gray'}>
            {' ⇗ '}<Link href={mr.url} label={mr.label} />{' '}
          </Text>
          <Text color={mrColor(mr, colors)}>
            {mr.state === 'merged' ? '✓ merged' : mr.state === 'opened' ? 'open' : `✕ ${mr.state ?? '?'}`}
          </Text>
        </Box>
        {mr.title && <Text {...muted} wrap="truncate-end">   {mr.title}</Text>}
      </Box>
    )
    const mrGroups: [string, string, Mr[]][] = [
      ['mr-open', 'OPEN', mrs.filter(mr => mr.state === 'opened')],
      ['mr-fresh', 'MERGED THIS TURN', mrs.filter(mr => mr.state === 'merged' && mr.fresh)],
      ['mr-merged', 'MERGED', mrs.filter(mr => mr.state === 'merged' && !mr.fresh)],
      ['mr-closed', 'CLOSED', mrs.filter(mr => mr.state !== 'opened' && mr.state !== 'merged')],
    ]
    const mrTab = () => mrs.length === 0
      ? empty('No merge request in this session.')
      : (
        <Box key="mr" flexDirection="column" gap={1}>
          {mrGroups.map(([id, title, group]) => section(id, title, group.length, () => group.map(mrRow)))}
        </Box>
      )

    const notesTab = () => {
      if (notes.length === 0) {
        return empty('No note written in this session.')
      }
      const groups: [string, string, Note[]][] = [
        ['notes-created', 'CREATED', notes.filter(note => note.action === 'created')],
        ['notes-modified', 'MODIFIED', notes.filter(note => note.action !== 'created')],
      ]
      return (
        <Box key="notes" flexDirection="column" gap={1}>
          {groups.map(([id, heading, group]) => section(id, heading, group.length, () => (
            <Box key={`${id}-list`} flexDirection="column">
              {group.map(note => (
                <Box key={note.link ?? `note-${note.title}`} flexDirection="row" gap={1}>
                  <Text color={colors.accent}>▤</Text>
                  {note.link
                    ? <Link href={note.link} label={note.title ?? '?'} />
                    : <Text color={colors.text}>{note.title ?? '?'}</Text>}
                </Box>
              ))}
            </Box>
          )))}
        </Box>
      )
    }

    return (
      <Box key="body" flexDirection="column" gap={1} paddingX={1}
        width={e.props.bodyColumns} minHeight={e.props.scroll.bodyRows} backgroundColor={colors.background}>
        {tabs}
        {shown === 'todo' ? todoTab() : shown === 'mr' ? mrTab() : notesTab()}
      </Box>
    )
  })
}
