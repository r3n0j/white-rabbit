export type Mr = { label: string; url: string; state: string | null; title: string | null; fresh: boolean }
export type Note = { title: string | null; action: string | null; link: string | null }
export type Todo = { text: string; next: boolean }
export type Placement = 'band' | 'hint' | 'mode' | 'turn'
export type Tab = 'todo' | 'mr' | 'notes'
export type Display = 'statusline' | 'band' | 'off'
export type Palette = 'default' | 'matrix' | 'night' | 'forest' | 'ember'
export type View = {
  mrs: Mr[]
  counts: { merged: number; to_merge: number }
  notes: Note[]
  todos: Todo[]
  then: string | null
  display?: Display
}

declare module 'claude-code' {
  interface PluginState {
    'white-rabbit-panel': { view: View | null; announced: string[]; placement: Placement; palette: Palette; neb: boolean; tab: Tab }
  }
}
