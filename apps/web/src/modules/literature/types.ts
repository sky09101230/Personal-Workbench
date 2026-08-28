export type LiteratureStatus = {
  provider: string;
  provider_configured: boolean;
  sync_state: string;
  library_version: string | null;
  last_synced_at: string | null;
};

export type ExternalReference = {
  provider: string;
  library_id: string;
  item_key: string;
};

export type Collection = {
  id: string;
  name: string;
  parent_id: string | null;
  external_ref: ExternalReference | null;
};

export type Paper = {
  id: string;
  title: string;
  authors: string[];
  abstract: string | null;
  year: number | null;
  journal: string | null;
  doi: string | null;
  tags: string[];
  external_ref: ExternalReference | null;
};

export type Note = {
  id: string;
  paper_id: string;
  content: string;
  kind: "note" | "annotation";
  page_label: string | null;
  color: string | null;
  external_ref: ExternalReference | null;
};

export type Attachment = {
  id: string;
  paper_id: string;
  filename: string;
  content_type: string | null;
  downloadable: boolean;
  link_mode: string | null;
  availability: "available" | "linked_file" | "provider_unavailable" | "not_pdf";
  external_ref: ExternalReference | null;
};

export type CollectionsResponse = { items: Collection[] };
export type PapersResponse = { items: Paper[]; total: number; library_version: string | null };
export type FiltersResponse = { years: number[]; journals: string[]; tags: string[] };
export type PaperDetailResponse = {
  paper: Paper;
  collections: Collection[];
  pdf_available: boolean;
};
export type NotesResponse = { items: Note[] };
export type AttachmentsResponse = { items: Attachment[] };
export type SyncResponse = {
  status: "succeeded";
  sync_mode: "full" | "incremental";
  library_version: string | null;
  collections: number;
  papers: number;
  notes: number;
  attachments: number;
};

export type OverviewContent = {
  research_question: string;
  core_idea: string;
  methodology: string;
  contributions: string[];
  experiments: string;
  key_results: string[];
  limitations: string[];
  worth_reading: string;
  suggested_focus: string[];
};

export type DeepReadContent = {
  research_problem: string;
  core_logic: string;
  key_assumptions: string[];
  why_it_may_work: string;
  evidence_assessment: string;
  reproducible_parts: string[];
  potential_problems: string[];
  underdiscussed_limitations: string[];
  unresolved_questions: string[];
  research_inspirations: string[];
};

export type SelectionContent = {
  action: "explain" | "summarize" | "translate" | "ask";
  response: string;
  paper_evidence: string[];
  ai_inference: string[];
  uncertainty: string;
};

export type AskPaperContent = {
  answer: string;
  paper_evidence: string[];
  ai_inference: string[];
  uncertainty: string;
  insufficient_context: boolean;
};

export type LiteratureAIContent = OverviewContent | DeepReadContent | SelectionContent;

export type LiteratureAIAnalysis = {
  id: string;
  paper_id: string;
  analysis_type: string;
  model: string;
  prompt_version: string;
  content: LiteratureAIContent;
  created_at: string;
};

export type LiteratureAIConversation = {
  id: string;
  paper_id: string;
  created_at: string;
  updated_at: string;
};

export type LiteratureAIMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: { question: string } | AskPaperContent;
  model: string | null;
  prompt_version: string | null;
  created_at: string;
};

export type LiteratureUserNote = {
  id: string;
  paper_id: string;
  content: string;
  source: "manual" | "ai_overview" | "ai_deep_read" | "ai_chat" | "ai_selection";
  created_at: string;
  updated_at: string;
};

export type AnalysisListResponse = { items: LiteratureAIAnalysis[] };
export type ConversationListResponse = { items: LiteratureAIConversation[] };
export type MessageListResponse = { items: LiteratureAIMessage[] };
export type UserNoteListResponse = { items: LiteratureUserNote[] };

export type PdfSelection = {
  pageNumber: number;
  selectedText: string;
  contextBefore: string;
  contextAfter: string;
};
