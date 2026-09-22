import { literatureLabel } from "../labels";
import { useState } from "react";
import type { MetadataPatch } from "../types";

export const metadataFields = ["title", "authors", "year", "journal", "doi", "arxiv_id", "abstract"] as const;
export function metadataText(value: unknown): string {
  return Array.isArray(value) ? value.join("; ") : value == null ? "" : String(value);
}

export function MetadataForm({ initial, onSave, busy, label = "保存元数据", onCancel }: {
  initial: MetadataPatch; onSave: (patch: MetadataPatch) => void; busy: boolean; label?: string; onCancel?: () => void;
}) {
  const [values, setValues] = useState(() => Object.fromEntries(metadataFields.map((field) => [field, metadataText(initial[field])])));
  return <form className="metadata-form" onSubmit={(event) => {
    event.preventDefault();
    const patch: MetadataPatch = {};
    for (const field of metadataFields) {
      if (values[field] === metadataText(initial[field])) continue;
      const value = values[field].trim();
      if (field === "authors") patch.authors = value.split(";").map((author) => author.trim()).filter(Boolean);
      else if (field === "year") patch.year = value ? Number(value) : null;
      else if (field === "title") patch.title = value;
      else patch[field] = value || null;
    }
    onSave(patch);
  }}>
    <fieldset disabled={busy}><div className="metadata-fields">{metadataFields.map((field) => <label key={field}>
      <span>{field === "authors" ? "作者（使用英文分号 ; 分隔）" : literatureLabel(field)}</span>
      {field === "abstract" ? <textarea value={values[field]} maxLength={30000} onChange={(e) => setValues({ ...values, [field]: e.target.value })} /> :
        <input required={field === "title"} type={field === "year" ? "number" : "text"} min={field === "year" ? 1000 : undefined} max={field === "year" ? 3000 : undefined} maxLength={field === "title" || field === "journal" ? 1000 : undefined} value={values[field]} onChange={(e) => setValues({ ...values, [field]: e.target.value })} />}
    </label>)}</div><div className="wb-actions"><button type="submit">{busy ? "正在保存…" : label}</button>{onCancel && <button type="button" onClick={onCancel}>取消编辑</button>}</div></fieldset>
  </form>;
}
