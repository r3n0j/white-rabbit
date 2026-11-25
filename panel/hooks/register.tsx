import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { Display, Git, Mr, Note, Palette, Placement, Tab, Usage, View } from '../types'

const PANE = 'white-rabbit'
const TITLE = 'White rabbit'
const TABS: { id: Tab; glyph: string; label: string }[] = [
  { id: 'todo', glyph: '▸', label: 'To-do' },
  { id: 'mr', glyph: '⇗', label: 'MR' },
  { id: 'notes', glyph: '▤', label: 'Notes' },
  { id: 'git', glyph: '⎇', label: 'Git' },
]
const REFRESH_MS = 20_000

const view = atom({ plugin: 'white-rabbit-panel', key: 'view' } as const, null)
const announced = atom({ plugin: 'white-rabbit-panel', key: 'announced' } as const, [])
const placement = atom({ plugin: 'white-rabbit-panel', key: 'placement' } as const, 'mode')
const palette = atom({ plugin: 'white-rabbit-panel', key: 'palette' } as const, 'default')
const tab = atom({ plugin: 'white-rabbit-panel', key: 'tab' } as const, 'todo')
const folds = atom({ plugin: 'white-rabbit-panel', key: 'folds' } as const, {})
const git = atom({ plugin: 'white-rabbit-panel', key: 'git' } as const, null)
const usage = atom({ plugin: 'white-rabbit-panel', key: 'usage' } as const, null)
const FOLDED_BY_DEFAULT = ['mr-merged', 'mr-closed', 'todo-past']
const neb = atom({ plugin: 'white-rabbit-panel', key: 'neb' } as const, false)

type Colors = { background?: string; accent: string; hover?: string; rule?: string; alarm?: string; tip?: string; text?: string; muted?: string; merged: string; opened: string }

const PALETTES: Record<Palette, Colors> = {
  default: { accent: 'cyan', merged: 'green', opened: 'yellow' },
  matrix: { background: '#04111b', accent: '#2ea7db', hover: '#7fb3c4', rule: '#26566e', alarm: '#e0303a', tip: '#0c2435', text: '#d8f0f8', muted: '#7fb3c4', merged: '#78d8c0', opened: '#f0b040' },
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

async function loadUsage($: EngineInterface): Promise<Usage | null> {
  try {
    const { context, cost, startedAt } = await $.session.usage()
    const model = await $.session.model().catch(() => null)
    return {
      model,
      startedAt,
      percent: context.percent ?? null,
      tokens: context.tokens ?? null,
      window: context.window,
      usd: cost?.usd ?? null,
    }
  } catch {
    return null
  }
}

async function loadGit($: EngineInterface, cwd: string | null | undefined): Promise<Git | null> {
  if (!cwd) {
    return null
  }
  try {
    const status = await $.process.run(['git', 'status', '--porcelain=v1', '-b'], { cwd, timeoutMs: 5_000 })
    if (status.exitCode !== 0) {
      return null
    }
    const [head = '', ...lines] = status.stdout.split('\n').filter(Boolean)
    const tracking = /^## (.+?)(?:\.\.\.(\S+))?(?: \[(.*)\])?$/.exec(head)
    const branch = tracking?.[1] ?? '?'
    const upstream = tracking?.[2] ?? null
    const counts = tracking?.[3] ?? ''
    const commits = async (range: string) => {
      if (upstream === null) {
        return []
      }
      const log = await $.process.run(['git', 'log', '--format=%h%x09%s', range], { cwd, timeoutMs: 5_000 })
      return log.exitCode !== 0 ? [] : log.stdout.split('\n').filter(Boolean).map(line => {
        const [sha = '', ...subject] = line.split('\t')
        return { sha, subject: subject.join('\t') }
      })
    }
    const unpushed = await commits('@{u}..HEAD')
    const incoming = await commits('HEAD..@{u}')
    return {
      branch,
      upstream,
      ahead: Number(/ahead (\d+)/.exec(counts)?.[1] ?? 0),
      behind: Number(/behind (\d+)/.exec(counts)?.[1] ?? 0),
      files: lines.map(line => ({ status: line.slice(0, 2).trim(), path: line.slice(3) })),
      unpushed,
      incoming,
    }
  } catch {
    return null
  }
}

async function ask($: EngineInterface, text: string, done: string) {
  try {
    await $.prompt.submit({ text })
    $.ui.toast(done)
  } catch {
    $.ui.toast('The session could not be asked')
  }
}

function askRebase($: EngineInterface, mr: Mr) {
  return ask($, `Rebase la MR ${mr.label} (${mr.url}) sur sa branche cible : GitLab la signale en need rebase.`,
    `Asked the session to rebase ${mr.label}`)
}

function askPipeline($: EngineInterface, mr: Mr) {
  return ask($, `Le pipeline de la MR ${mr.label} (${mr.url}) est en échec : regarde pourquoi et propose un correctif.`,
    `Asked the session to look into the pipeline of ${mr.label}`)
}

function plural(n: number, word: string) {
  return `${n} ${word}${n > 1 ? 's' : ''}`
}

function askCommit($: EngineInterface, repo: Git) {
  return ask($, `Committe ${repo.files.length > 1 ? 'les' : 'le'} ${plural(repo.files.length, 'changement')} en cours de la branche ${repo.branch}, `
    + 'découpés en commits cohérents, aux conventions du repo.', 'Asked the session to commit')
}

function askPush($: EngineInterface, repo: Git) {
  return ask($, `Pousse ${repo.unpushed.length > 1 ? 'les' : 'le'} ${plural(repo.unpushed.length, 'commit')} non ${repo.unpushed.length > 1 ? 'poussés' : 'poussé'} de la branche ${repo.branch} : `
    + 'je donne mon accord pour ce push.', 'Asked the session to push')
}

function askPull($: EngineInterface, repo: Git) {
  return ask($, `La branche ${repo.branch} a ${plural(repo.behind, 'commit')} de retard sur ${repo.upstream ?? 'sa branche distante'} : `
    + 'mets-la à jour avec git pull --rebase.', 'Asked the session to pull')
}

async function compact($: EngineInterface) {
  try {
    const { skip } = await $.session.compact()
    if (skip) {
      $.ui.toast(`Compaction skipped: ${skip}`)
    }
  } catch {
    $.ui.toast('Compaction waits for the end of the turn')
  }
  await update($, usage, () => null)
  const fresh = await loadUsage($)
  await update($, usage, () => fresh)
}

async function refresh($: EngineInterface) {
  const now = await loadUsage($)
  await update($, usage, () => now)
  const next = await load($)
  if (next === null) {
    return
  }
  await update($, view, () => next)
  const repo = await loadGit($, next.cwd)
  await update($, git, () => repo)
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

const MERGE_WORDS: Record<string, string> = {
  mergeable: 'mergeable',
  need_rebase: 'need rebase',
  not_approved: 'not approved',
  conflict: 'conflicts',
  discussions_not_resolved: 'threads open',
  blocked_status: 'blocked by dependencies',
  ci_must_pass: 'pipeline must pass',
  ci_still_running: 'pipeline running',
  draft_status: 'draft',
  not_open: 'not open',
  requested_changes: 'changes requested',
  jira_association_missing: 'no Jira ticket',
}

function age(at: string | null | undefined, now: number) {
  const time = at ? Date.parse(at) : NaN
  if (Number.isNaN(time)) {
    return ''
  }
  const minutes = Math.max(0, Math.round((now - time) / 60_000))
  if (minutes < 60) return `${minutes}m`
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)}h`
  return `${Math.round(minutes / 1440)}d`
}

function stamp(at: string | null | undefined) {
  const time = at ? new Date(at) : null
  if (!time || Number.isNaN(time.getTime())) {
    return ''
  }
  const two = (n: number) => String(n).padStart(2, '0')
  return `${two(time.getDate())}/${two(time.getMonth() + 1)} ${two(time.getHours())}:${two(time.getMinutes())}`
}

function newestMergeFirst(mrs: Mr[]) {
  return mrs.map((mr, index) => ({ mr, index }))
    .sort((a, b) => (Date.parse(b.mr.merged_at ?? '') || 0) - (Date.parse(a.mr.merged_at ?? '') || 0) || b.index - a.index)
    .map(({ mr }) => mr)
}

function modelName(model: string | null) {
  if (!model) {
    return '?'
  }
  const short = model.replace(/^claude-/, '').replace(/\[.*\]$/, '')
  const [family = '', ...version] = short.split('-')
  return `${family.charAt(0).toUpperCase()}${family.slice(1)}${version.length ? ` ${version.join('-')}` : ''}`
}

function tokens(n: number | null | undefined) {
  if (n === null || n === undefined) return '—'
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${Math.round(n / 1000)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

function dollars(usd: number) {
  return usd >= 100 ? `${Math.round(usd)}$` : `${usd.toFixed(2)}$`
}

function since(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86_400)}d`
}

function gauge(percent: number, cells: number) {
  const full = Math.round((Math.min(100, Math.max(0, percent)) / 100) * cells)
  return '▰'.repeat(full) + '▱'.repeat(cells - full)
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
    const repo = await read($, git)
    const session = await read($, usage)
    const now = await $.clock.now()
    const past = current?.past ?? []
    const alarm = colors.alarm ?? 'red'
    const counts: Record<Tab, number> = {
      todo: todos.length,
      mr: mrs.length,
      notes: notes.length,
      git: (repo?.files.length ?? 0) + (repo?.unpushed.length ?? 0) + (repo?.behind ?? 0),
    }

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
            <Box key={`${id}-rule`} flexGrow={1} flexShrink={1}>
              <Text {...rule} wrap="truncate-end">{'─'.repeat(Math.max(0, width - label.length))}</Text>
            </Box>
          </Box>
          {!closed && body()}
        </Box>
      )
    }
    const empty = (text: string) => <Text {...muted}>{text}</Text>

    const percent = session?.percent ?? null
    const level = percent === null ? colors.text : percent >= 85 ? alarm : percent >= 60 ? colors.opened : colors.accent
    const tipBackground = colors.tip ?? 'gray'
    const tipColor = colors.tip ? colors.text : 'black'
    const tooltip = (scope: string, text: string, spot: { top: number; left?: number; right?: number }) => (
      <Box key={`${scope}-card`} position="absolute" {...spot} display="none" hover={{ scope, display: 'flex' }}
        backgroundColor={tipBackground} paddingX={1}>
        <Text color={tipColor}>{text}</Text>
      </Box>
    )
    const sessionLine = session && (
      <Text key="session-line" wrap="truncate-end">
        <Text bold color={colors.accent}>{modelName(session.model)}</Text>
        <Text {...muted}> · OUT </Text>
        <Text color={colors.text}>{tokens(current?.output_total)}</Text>
        {session.usd !== null && <Text {...muted}> · </Text>}
        {session.usd !== null && <Text color={colors.text}>{dollars(session.usd)}</Text>}
        <Text {...muted}> · </Text>
        <Text color={colors.text}>{since(now - session.startedAt)}</Text>
      </Text>
    )
    const folder = (current?.cwd ?? '').split('/').filter(Boolean).pop()
    const gitLine = repo && (
      <Text key="git-line" wrap="truncate-end">
        {folder && <Text bold color={colors.text}>/{folder} </Text>}
        <Text bold color={colors.accent}>⎇ </Text>
        <Text bold color={colors.text}>{repo.branch}</Text>
        {repo.upstream === null && <Text {...muted}> (no upstream)</Text>}
        {repo.ahead > 0 && <Text color={colors.opened}> ↑{repo.ahead}</Text>}
        {repo.behind > 0 && <Text color={colors.opened}> ↓{repo.behind}</Text>}
        <Text {...muted}> · ✎ {repo.files.length} modified · ⇡ {repo.unpushed.length} unpushed</Text>
      </Text>
    )
    const label = percent === null ? 'CTX ? ' : `CTX ${Math.round(percent)}% `
    const contextLine = session && (
      <Box key="context" flexDirection="column">
        <Box key="context-row" flexDirection="row" gap={1}>
          <Box key="context-text" flexGrow={1} flexShrink={1} hover={{ scope: 'context-tip' }}>
            <Text wrap="truncate-end">
              <Text bold color={level}>{label}</Text>
              <Text color={level}>{gauge(percent ?? 0, Math.max(4, width - label.length - 3))}</Text>
            </Text>
          </Box>
          <Box key="compact-zone">
            <Button key="compact" plain label="⇊" onPress={() => compact($)}
              hover={{ ...hovered(colors).hover, scope: 'compact-tip' }} />
          </Box>
        </Box>
        {session.tokens !== null && tooltip('context-tip',
          `${Math.round(session.tokens / 1000)}k / ${Math.round(session.window / 1000)}k tokens`, { top: 1, left: 0 })}
        {tooltip('compact-tip', 'Compact the conversation', { top: 1, right: 0 })}
      </Box>
    )

    const tabs = (
      <Box key="tabs" flexDirection="row" flexWrap="wrap" columnGap={1}>
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

    const todoTab = () => (todos.length === 0 && !current?.then && past.length === 0)
      ? empty('Nothing expected from you.')
      : (
        <Box key="todo" flexDirection="column" gap={1}>
          {section('todo-next', 'NEXT', todos.length, () => todos.map(todo => todo.next
            ? <Text key={todo.text} bold color={colors.merged}>▸ {todo.text}</Text>
            : <Text key={todo.text} color={colors.text}>○ {todo.text}</Text>))}
          {section('todo-then', 'THEN', current?.then ? 1 : 0, () => <Text {...muted}>◦ {current?.then}</Text>)}
          {section('todo-past', 'PAST', past.length, () => past.map(item => (
            <Text key={`past-${item.text}`} wrap="truncate-end">
              <Text {...rule}>{age(item.at, now).padEnd(4)}</Text>
              <Text {...muted}>✓ {item.text}</Text>
            </Text>
          )))}
        </Box>
      )

    const mrRow = (mr: Mr) => (
      <Box key={mr.url} flexDirection="column">
        <Text wrap="truncate-end">
          <Text bold strikethrough={mr.fresh} color={ink}
            backgroundColor={mr.state === 'opened' ? colors.merged : colors.muted ?? 'gray'}>
            {' ⇗ '}<Link href={mr.url} label={mr.label} />{' '}
          </Text>
          <Text color={mrColor(mr, colors)}>
            {' '}{mr.state === 'merged' ? '✓ merged' : mr.state === 'opened' ? 'open' : `✕ ${mr.state ?? '?'}`}
            {mr.state === 'merged' && stamp(mr.merged_at) ? ` ${stamp(mr.merged_at)}` : ''}
          </Text>
          {mr.state === 'opened' && mr.pipeline && (
            <Text color={mr.pipeline === 'success' ? colors.merged : mr.pipeline === 'failed' ? alarm : colors.opened}>
              {' · '}{mr.pipeline === 'success' ? '✓' : mr.pipeline === 'failed' ? '✖' : '◐'} pipeline
              {mr.pipeline === 'success' || mr.pipeline === 'failed' ? '' : ` ${mr.pipeline}`}
            </Text>
          )}
          {mr.state === 'opened' && mr.merge_status && MERGE_WORDS[mr.merge_status] !== undefined && (
            <Text color={mr.merge_status === 'mergeable' ? colors.merged : mr.merge_status === 'conflict' ? alarm : colors.opened}>
              {' · '}{MERGE_WORDS[mr.merge_status]}
            </Text>
          )}
          {(mr.comments ?? 0) > 0 && <Text {...muted}>{' · '}{mr.comments} comment{mr.comments === 1 ? '' : 's'}</Text>}
        </Text>
        {mr.title && <Text {...muted} wrap="truncate-end">   {mr.title}</Text>}
        {mr.state === 'opened' && (mr.merge_status === 'need_rebase' || mr.pipeline === 'failed') && (
          <Box key={`${mr.url}-actions`} flexDirection="row" gap={2} paddingLeft={3}>
            {mr.merge_status === 'need_rebase' && (
              <Button key={`rebase-${mr.url}`} plain dimColor label="⟲ ask to rebase" onPress={() => askRebase($, mr)}
                {...hovered(colors)} />
            )}
            {mr.pipeline === 'failed' && (
              <Button key={`pipeline-${mr.url}`} plain dimColor label="⌕ ask why the pipeline failed"
                onPress={() => askPipeline($, mr)} {...hovered(colors)} />
            )}
          </Box>
        )}
      </Box>
    )
    const mrGroups: [string, string, Mr[]][] = [
      ['mr-open', 'OPEN', mrs.filter(mr => mr.state === 'opened')],
      ['mr-fresh', 'MERGED THIS TURN', newestMergeFirst(mrs.filter(mr => mr.state === 'merged' && mr.fresh))],
      ['mr-merged', 'MERGED', newestMergeFirst(mrs.filter(mr => mr.state === 'merged' && !mr.fresh))],
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
                <Text key={note.link ?? `note-${note.title}`} wrap="truncate-end">
                  <Text {...rule}>{age(note.at, now).padEnd(4)}</Text>
                  <Text color={colors.accent}>▤ </Text>
                  {note.link
                    ? <Link href={note.link} label={note.title ?? '?'} />
                    : <Text color={colors.text}>{note.title ?? '?'}</Text>}
                </Text>
              ))}
            </Box>
          )))}
        </Box>
      )
    }

    const gitTab = () => {
      if (repo === null) {
        return empty('The session folder is not a git repository.')
      }
      if (counts.git === 0) {
        return empty('Nothing to push, nothing modified.')
      }
      const action = (key: string, label: string, onPress: () => void) => (
        <Box key={`${key}-zone`} paddingLeft={2}>
          <Button key={key} plain dimColor label={label} onPress={onPress} {...hovered(colors)} />
        </Box>
      )
      const commitRow = (commit: { sha: string; subject: string }) => (
        <Text key={`commit-${commit.sha}`} wrap="truncate-end">
          <Text color={colors.accent}>{commit.sha} </Text>
          <Text color={colors.text}>{commit.subject}</Text>
        </Text>
      )
      return (
        <Box key="git" flexDirection="column" gap={1}>
          {section('git-pull', 'TO PULL', repo.behind, () => (
            <Box key="git-pull-list" flexDirection="column">
              {repo.incoming.map(commitRow)}
              {action('git-pull', '⇣ ask to pull', () => askPull($, repo))}
            </Box>
          ))}
          {section('git-unpushed', 'UNPUSHED', repo.unpushed.length, () => (
            <Box key="git-unpushed-list" flexDirection="column">
              {repo.unpushed.map(commitRow)}
              {action('git-push', '⇡ ask to push', () => askPush($, repo))}
            </Box>
          ))}
          {section('git-modified', 'MODIFIED', repo.files.length, () => (
            <Box key="git-modified-list" flexDirection="column">
              {repo.files.map(file => (
                <Text key={`file-${file.path}`} wrap="truncate-start">
                  <Text color={file.status === '??' ? colors.opened : colors.accent}>{file.status.padEnd(2)} </Text>
                  <Text color={colors.text}>{file.path}</Text>
                </Text>
              ))}
              {action('git-commit', '✎ ask to commit', () => askCommit($, repo))}
            </Box>
          ))}
        </Box>
      )
    }
    const tabBody = { todo: todoTab, mr: mrTab, notes: notesTab, git: gitTab }[shown]

    return (
      <Box key="body" flexDirection="column" gap={1} paddingX={1}
        width={e.props.bodyColumns} minHeight={e.props.scroll.bodyRows} backgroundColor={colors.background}>
        <Box key="identity" flexDirection="column">
          {sessionLine}
          {gitLine}
          {contextLine}
          <Text key="separator" {...rule} wrap="truncate-end">{'─'.repeat(Math.max(0, width))}</Text>
        </Box>
        {tabs}
        {tabBody()}
      </Box>
    )
  })
}
