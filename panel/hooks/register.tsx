import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Display, Mr, Note, Palette, Placement, View } from '../types'

const TABS = [
  { id: 'white-rabbit-todo', title: '▸ To-do', section: 'todo' },
  { id: 'white-rabbit-mr', title: '⇗ MR', section: 'mr' },
  { id: 'white-rabbit-notes', title: '▤ Notes', section: 'notes' },
] as const
const REFRESH_MS = 20_000

const view = atom({ plugin: 'white-rabbit-panel', key: 'view' } as const, null)
const announced = atom({ plugin: 'white-rabbit-panel', key: 'announced' } as const, [])
const placement = atom({ plugin: 'white-rabbit-panel', key: 'placement' } as const, 'mode')
const palette = atom({ plugin: 'white-rabbit-panel', key: 'palette' } as const, 'default')
const neb = atom({ plugin: 'white-rabbit-panel', key: 'neb' } as const, false)

type Colors = { background?: string; accent: string; hover?: string; text?: string; muted?: string; merged: string; opened: string }

const PALETTES: Record<Palette, Colors> = {
  default: { accent: 'cyan', merged: 'green', opened: 'yellow' },
  matrix: { background: '#04111b', accent: '#2ea7db', hover: '#7fb3c4', text: '#d8f0f8', muted: '#7fb3c4', merged: '#78d8c0', opened: '#f0b040' },
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
  const open = (await $.ui.panes()).filter(pane => TABS.some(tab => tab.id === pane.id))
  if (open.length > 0) {
    for (const pane of open) {
      await $.ui.close({ id: pane.id })
    }
    return
  }
  await refresh($)
  for (const tab of TABS) {
    await $.ui.open({ id: tab.id, title: tab.title })
  }
  await $.ui.open({ id: TABS[0].id, title: TABS[0].title })
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

  for (const tab of TABS) {
    on('ui.render', { component: 'Pane', requestId: tab.id }, async ($, e) => {
      const current = await read($, view)
      const colors = PALETTES[await read($, palette)]
      const { accent } = colors
      const muted = secondary(colors)
      const { Box, Link, Text } = $.ui.resolve(e)
      const frame = {
        flexDirection: 'column' as const,
        gap: 1,
        paddingX: 1,
        width: e.props.bodyColumns,
        minHeight: e.props.scroll.bodyRows,
        backgroundColor: colors.background,
      }
      const empty = (text: string) => <Box key="body" {...frame}><Text {...muted}>{text}</Text></Box>

      if (tab.section === 'todo') {
        if (current === null || (current.todos.length === 0 && !current.then)) {
          return empty('Nothing expected from you.')
        }
        return (
          <Box key="body" {...frame}>
            <Box flexDirection="column">
              {current.todos.map(todo => (
                <Text key={todo.text} bold={todo.next} {...(todo.next ? { color: colors.text } : muted)}>
                  {todo.next ? '▸' : '·'} {todo.text}
                </Text>
              ))}
              {current.then && <Text {...muted}>◦ {current.then}</Text>}
            </Box>
          </Box>
        )
      }

      if (tab.section === 'mr') {
        if (current === null || current.mrs.length === 0) {
          return empty('No merge request in this session.')
        }
        return (
          <Box key="body" {...frame}>
            <Box flexDirection="column">
              {current.mrs.map(mr => (
                <Box key={mr.url} flexDirection="row" gap={1}>
                  <Text color={mrColor(mr, colors)}>{mr.state === 'merged' ? '✓' : mr.state === 'opened' ? '●' : '○'}</Text>
                  <Text color={colors.text} strikethrough={mr.fresh}><Link href={mr.url} label={mr.label} /></Text>
                  {mr.title && <Text {...muted} wrap="truncate-end">{mr.title}</Text>}
                  {mr.state !== 'opened' && mr.state !== 'merged' && <Text {...muted}>({mr.state})</Text>}
                </Box>
              ))}
            </Box>
          </Box>
        )
      }

      if (current === null || current.notes.length === 0) {
        return empty('No note written in this session.')
      }
      const created = current.notes.filter(note => note.action === 'created')
      const modified = current.notes.filter(note => note.action !== 'created')
      return (
        <Box key="body" {...frame}>
          {[['Created', created], ['Modified', modified]].map(([heading, notes]) =>
            (notes as View['notes']).length > 0 && (
              <Box key={heading as string} flexDirection="column">
                <Text bold color={accent}>{heading as string}</Text>
                {(notes as View['notes']).map(note => (
                  note.link
                    ? <Link key={note.link} href={note.link} label={note.title ?? '?'} />
                    : <Text key={`note-${note.title}`} color={colors.text}>{note.title ?? '?'}</Text>
                ))}
              </Box>
            ))}
        </Box>
      )
    })
  }
}
