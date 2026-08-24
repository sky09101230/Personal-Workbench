import { BookOpen, Folder } from "lucide-react";
import type { ReactNode } from "react";
import type { Collection, FiltersResponse } from "../types";

type CollectionPaneProps = {
  collections: Collection[];
  providerReady: boolean;
  selectedCollectionId: string | null;
  totalPapers: number;
  filters: FiltersResponse;
  author: string;
  year: string;
  journal: string;
  tag: string;
  onSelect: (collectionId: string | null) => void;
  onFilterChange: (name: "author" | "year" | "journal" | "tag", value: string) => void;
};

export function CollectionPane({
  collections,
  providerReady,
  selectedCollectionId,
  totalPapers,
  filters,
  author,
  year,
  journal,
  tag,
  onSelect,
  onFilterChange,
}: CollectionPaneProps) {
  const orderedCollections = [...collections].sort((left, right) =>
    left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" }),
  );

  return (
    <aside className="workspace-pane collection-pane" aria-label="Literature collections">
      <PaneHeader label="Library" />
      <div className="pane-scroll collection-scroll">
        <div className="collection-group">
          <button
            className={`collection-item ${selectedCollectionId === null ? "selected" : ""}`}
            type="button"
            onClick={() => onSelect(null)}
          >
            <BookOpen size={15} aria-hidden="true" />
            <span className="collection-name">All papers</span>
            <span className="collection-count">{totalPapers}</span>
          </button>
        </div>

        <div className="pane-subheading">Collections</div>
        {collections.length > 0 ? (
          <div className="collection-list">
            {orderedCollections.map((collection) => (
              <button
                className={`collection-item collection-item-nested ${selectedCollectionId === collection.id ? "selected" : ""}`}
                key={collection.id}
                type="button"
                title={collection.name || "Untitled collection"}
                onClick={() => onSelect(collection.id)}
                style={{ paddingLeft: collection.parent_id ? 28 : 10 }}
              >
                <Folder size={14} aria-hidden="true" />
                <span className="collection-name">{collection.name || "Untitled collection"}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="collection-empty">{providerReady ? "No collections yet" : "Configure Zotero to view collections"}</p>
        )}

        <div className="pane-subheading">Filters</div>
        <div className="filter-list">
          <label className="filter-field">
            <span>Author</span>
            <input
              value={author}
              placeholder="Author name"
              onChange={(event) => onFilterChange("author", event.target.value)}
            />
          </label>
          <FilterSelect label="Year" value={year} options={filters.years.map(String)} onChange={(value) => onFilterChange("year", value)} />
          <FilterSelect label="Journal / Venue" value={journal} options={filters.journals} onChange={(value) => onFilterChange("journal", value)} />
          <FilterSelect label="Tag" value={tag} options={filters.tags} onChange={(value) => onFilterChange("tag", value)} />
        </div>
      </div>
    </aside>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {options.map((option) => <option value={option} key={option}>{option}</option>)}
      </select>
    </label>
  );
}

export function PaneHeader({ label, trailing }: { label: string; trailing?: ReactNode }) {
  return (
    <div className="pane-header">
      <span>{label}</span>
      {trailing ? <span className="pane-header-trailing">{trailing}</span> : null}
    </div>
  );
}
