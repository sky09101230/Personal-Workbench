"""Metadata review use cases delegate atomic decisions through a repository port."""
from dataclasses import dataclass
from app.modules.literature.application.ports import LiteratureWorkflowRepository


@dataclass(frozen=True)
class MetadataReviewService:
    repository: LiteratureWorkflowRepository

    def create_proposal(self, paper_id, source, proposed_metadata):
        return self.repository.create_metadata_proposal(paper_id, source, proposed_metadata)

    def list_proposals(self, paper_id):
        return self.repository.list_metadata_proposals(paper_id)

    def get_proposal(self, proposal_id):
        return self.repository.get_metadata_proposal(proposal_id)

    def accept_proposal(self, proposal_id):
        return self.repository.resolve_metadata_proposal(proposal_id, accept=True)

    def reject_proposal(self, proposal_id):
        return self.repository.resolve_metadata_proposal(proposal_id, accept=False)

    def edit_and_accept(self, proposal_id, edits):
        return self.repository.resolve_metadata_proposal(proposal_id, accept=True, edits=edits)
