/** Model selector state, persisted in localStorage like the legacy page. */
export const MODEL_STORAGE_KEY = 'chatcv_model'
export const DEFAULT_MODEL = 'gpt-5.6-sol'

/** Options shown in the selector (same two as the legacy page; labels may be overridden by GET /models). */
export const VISIBLE_MODELS: { value: string; label: string }[] = [
  { value: 'gpt-5.6-sol', label: 'Sol（质量）' },
  { value: 'gpt-5.6-luna', label: 'Luna（更快）' },
]

const isVisible = (m: string | null | undefined): m is string => !!m && VISIBLE_MODELS.some((o) => o.value === m)

export function readStoredModel(): string | null {
  try {
    const v = localStorage.getItem(MODEL_STORAGE_KEY)
    return isVisible(v) ? v : null
  } catch {
    return null
  }
}

export function storeModel(model: string): string {
  const value = isVisible(model) ? model : DEFAULT_MODEL
  try {
    localStorage.setItem(MODEL_STORAGE_KEY, value)
  } catch {
    /* storage unavailable */
  }
  return value
}

export { isVisible as isSelectableModel }
