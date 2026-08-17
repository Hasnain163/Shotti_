/** Mirrors the backend Pydantic models. Hand-written on purpose: codegen is not
 *  worth the setup at this size, but these must be kept in step with
 *  backend/app/models/. */

export type Verdict = 'LIKELY_TRUE' | 'LIKELY_FALSE' | 'UNVERIFIED' | 'MISLEADING'

export type Stance = 'supports' | 'contradicts' | 'neutral'
export type Reliability = 'high' | 'medium' | 'low'

export type SourceType =
  | 'fact_check'
  | 'news'
  | 'government'
  | 'academic'
  | 'encyclopedia'
  | 'social'
  | 'blog'
  | 'other'

export interface Source {
  title: string
  url: string
  domain: string
  snippet: string | null
  published_date: string | null
  source_type: SourceType | null
}

/** A quote, referenced to a source by index into `VerifyResponse.sources`. The
 *  backend never emits URLs from the model, so an index is the only link. */
export interface EvidenceItem {
  quote: string
  source_index: number
}

export interface SourceAssessment {
  source_index: number
  url: string
  domain: string
  stance: Stance
  reliability: Reliability
  is_outdated: boolean
  published_date: string | null
  note: string
}

export interface VerifyMeta {
  duration_ms: number
  sources_found: number
  sources_used: number
  queries_used: number
  dropped_evidence_count: number
  has_conflicting_evidence: boolean
  relies_on_speculation: boolean
  degraded: boolean
}

export interface VerifyResponse {
  claim: string
  normalized_claim: string
  verdict: Verdict
  confidence_score: number
  explanation: string
  supporting_evidence: EvidenceItem[]
  contradicting_evidence: EvidenceItem[]
  important_context: string[]
  sources: Source[]
  claim_id: string
  language: string
  source_assessments: SourceAssessment[]
  meta: VerifyMeta
}

export type ScreenshotKind =
  | 'social_post'
  | 'news_article'
  | 'news_card'
  | 'messaging'
  | 'video_frame'
  | 'document'
  | 'other'

export interface ScreenshotExtraction {
  extracted_text: string
  primary_claim: string
  language: string
  kind: ScreenshotKind
  visible_date: string | null
  visible_source: string | null
  has_factual_claim: boolean
  notes: string | null
}

export interface ScreenshotExtractionResponse {
  extraction: ScreenshotExtraction
  suggested_claim: string
}

export interface ScreenshotVerifyResponse extends VerifyResponse {
  extraction: ScreenshotExtraction
}

export interface HealthResponse {
  status: string
  app: string
  version: string
  services: Record<string, boolean>
}

/** The backend's shared error envelope. */
export interface ApiErrorBody {
  error: string
  message: string
  details?: Record<string, unknown> | null
}
