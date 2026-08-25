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
