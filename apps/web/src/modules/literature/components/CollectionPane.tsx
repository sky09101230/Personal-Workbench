import { BookOpen, Folder, Star } from "lucide-react";
import type { ReactNode } from "react";
import type { Collection } from "../types";

type CollectionPaneProps = {
  collections: Collection[];
  providerReady: boolean;
  selectedCollectionId: string | null;
  totalPapers: number;
  onSelect: (collectionId: string | null) => void;
};

export function CollectionPane({
  collections,
  providerReady,
  selectedCollectionId,
  totalPapers,
  onSelect,
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
          <button className="collection-item" type="button" disabled>
            <Star size={15} aria-hidden="true" />
            <span className="collection-name">Favorites</span>
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
      </div>
    </aside>
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
