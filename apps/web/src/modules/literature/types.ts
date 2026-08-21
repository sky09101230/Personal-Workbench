export type LiteratureStatus = {
  provider: string;
  provider_configured: boolean;
  sync_state: string;
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

export type CollectionsResponse = { items: Collection[] };
export type PapersResponse = { items: Paper[]; total: number; library_version: string | null };
