from dataclasses import dataclass

from app.modules.literature.application.ports import LiteratureIdentityRepository


@dataclass(frozen=True)
class IdentityReviewService:
    repository: LiteratureIdentityRepository

    def context(self, paper_id):
        return self.repository.identity_context(paper_id)

    def conflicts(self, *, limit=100, offset=0):
        return self.repository.list_identity_conflicts(limit=limit, offset=offset)

    def review(self, paper_id, **decision):
        return self.repository.review_identity(paper_id, **decision)

    def decide_conflict(self, conflict_id, **decision):
        return self.repository.decide_identity_conflict(conflict_id, **decision)

    def link_versions(self, preprint_id, **decision):
        return self.repository.link_paper_versions(preprint_id, **decision)

    def retract_version(self, version_id, **decision):
        return self.repository.retract_paper_version(version_id, **decision)
