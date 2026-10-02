/** Model selector state. The list itself comes from GET /models (managed in /admin). */
import type { ModelsResponse } from '@/lib/api'

export const MODEL_STORAGE_KEY = 'chatcv_model'

export type ModelOption = { id: string; label: string }

export function readStoredModel(): string | null {
  try {
    return localStorage.getItem(MODEL_STORAGE_KEY)
  } catch {
    return null
  }
}

export function storeModel(model: string): string {
  try {
    localStorage.setItem(MODEL_STORAGE_KEY, model)
  } catch {
    /* storage unavailable */
  }
  return model
}

export function toOptions(data: ModelsResponse): ModelOption[] {
  if (data.items?.length) return data.items
  return data.models.map((id) => ({ id, label: data.labels?.[id] ?? id }))
}

/** Keep the visitor's choice while it is still offered; otherwise use the server default. */
export function pickModel(current: string | null, data: ModelsResponse): string {
  return current && data.models.includes(current) ? current : data.default
}
