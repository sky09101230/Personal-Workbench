// Display labels only. API values and scholarly content remain unchanged.
const labels: Record<string, string> = {
  library: "文献库", radar: "发现雷达", import: "导入",
  inbox: "待整理", saved: "已收藏", reading: "阅读中", read: "已读", archived: "已归档",
  incomplete: "待补全", complete: "完整", conflict: "存在冲突",
  unreviewed: "尚未完整审核", reviewed: "已人工审核", user_confirmation: "用户确认", upload_review: "上传审核", radar_evidence: "雷达发现依据",
  unresolved: "身份待确定", published_confirmed: "正式论文 · 人工确认", preprint_confirmed: "预印本 · 人工确认", identifier_confirmed: "标识符 · 人工确认", identity_confirmation: "人工身份确认", identity_correction: "人工身份更正",
  keep_current: "保留当前身份", keep_separate: "保留为不同论文", quarantine: "待恢复来源证据", reopen: "重新审核", open: "待处理", retracted: "已撤回",
  verified: "本地文件校验通过", remote_only: "仅有远程文件引用", missing: "本地文件缺失", corrupt: "本地文件校验失败", invalid: "文件记录或路径无效", unreadable: "本地文件无法读取", unsupported_backend: "存储后端不可用",
  title: "标题", authors: "作者", year: "年份", journal: "期刊", tag: "标签", doi: "DOI", arxiv_id: "arXiv ID", openalex_id: "OpenAlex ID", abstract: "摘要",
  zotero: "Zotero", zotero_import: "Zotero 导入", zotero_selective: "Zotero 选择性导入", manual_pdf: "PDF 上传", zotero_materialization: "Zotero PDF 本地化", legacy_recovery: "历史数据恢复",
  staging: "暂存中", reviewing: "审核中", confirmed: "已入库", cancelled: "已取消", ready: "待确认", needs_review: "待审核", already_confirmed: "已入库，无需重复", failed: "失败",
  pending: "待审核", accepted: "已接受", rejected: "已拒绝", imported: "已导入", already_exists: "文献已存在", available: "可用",
  materialized: "已保存到本地", already_local: "已有本地文件", pdf_missing: "未找到 PDF", pdf_failed: "PDF 保存失败", pdf_skipped: "已跳过 PDF",
  primary: "主文件", preprint: "预印本", supplementary: "补充材料", detached: "已解绑", linked_file: "外部链接文件", provider_unavailable: "来源不可用", not_pdf: "非 PDF 文件",
  manual: "手动笔记", user: "用户修订", ai_overview: "AI 概览", ai_deep_read: "AI 精读", ai_chat: "AI 对话", ai_selection: "AI 选文分析", note: "笔记", annotation: "批注",
  recommendation_reason: "推荐理由", ai_summary: "AI 摘要", selection_rank: "推荐排名", overall_score: "综合评分", run_key: "发现批次", method: "方式", filename: "文件名", library_id: "来源库标识", item_key: "来源条目标识", active: "关联状态",
  short_text: "可提取文字较少，请人工核对", missing_title: "未提取到标题", missing_doi: "未提取到 DOI", missing_authors: "未提取到作者", file_date_is_not_publication_date: "文件日期不等于出版年份", identifier_requires_review: "标识符需要人工核对", multiple_doi_candidates: "提取到多个 DOI 候选",
  identity_conflict: "文献标识冲突，请核对 DOI / arXiv", source_item_unavailable: "无法读取来源条目", pdf_info: "PDF 属性", text_scan: "正文提取", first_page: "首页提取", pdf_file_date: "文件日期", low: "低", medium: "中", high: "高",
};
export function literatureLabel(value: string): string {
  if (value.startsWith("source:")) return `${literatureLabel(value.slice(7))} 来源建议`;
  if (value.startsWith("review:")) return `${literatureLabel(value.slice(7))} 审核`;
  if (value.startsWith("proposal:")) return `${literatureLabel(value.slice(9))} 修订建议`;
  return labels[value] ?? value;
}
