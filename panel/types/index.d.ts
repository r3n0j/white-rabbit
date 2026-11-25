export type Mr = {
  label: string
  url: string
  state: string | null
  title: string | null
  fresh: boolean
  pipeline?: string | null
  merge_status?: string | null
  comments?: number | null
  merged_at?: string | null
}
export type Note = { title: string | null; action: string | null; link: string | null; at?: string | null }
export type Todo = { text: string; next: boolean }
export type PastTodo = { text: string; at: string | null }
export type Placement = 'band' | 'hint' | 'mode' | 'turn'
export type Tab = 'todo' | 'mr' | 'notes' | 'git'
export type Display = 'statusline' | 'band' | 'off'
export type Palette = 'default' | 'matrix' | 'night' | 'forest' | 'ember'
export type View = {
  mrs: Mr[]
  counts: { merged: number; to_merge: number }
  notes: Note[]
  todos: Todo[]
  then: string | null
  past?: PastTodo[]
  cwd?: string | null
  output_total?: number | null
  display?: Display
}
export type Git = {
  branch: string
  upstream: string | null
  ahead: number
  behind: number
  files: { status: string; path: string }[]
  unpushed: { sha: string; subject: string }[]
  incoming: { sha: string; subject: string }[]
}
export type Usage = {
  model: string | null
  startedAt: number
  percent: number | null
  tokens: number | null
  window: number
  usd: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'white-rabbit-panel': {
      view: View | null
      announced: string[]
      placement: Placement
      palette: Palette
      neb: boolean
      tab: Tab
      folds: Record<string, boolean>
      git: Git | null
      usage: Usage | null
    }
  }
}
