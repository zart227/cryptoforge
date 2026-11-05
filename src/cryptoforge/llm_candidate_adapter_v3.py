"""Fixed v3 candidate request factory; local fixture transport is private to tests."""
from cryptoforge import llm_candidate_payload_v3 as contract
from cryptoforge import llm_prompt_preflight as prompt
from cryptoforge.llm_research_advisor import FreeAdvisor


class CandidateAdvisor(FreeAdvisor):
    def preflight(self, report, *, require_verified_input_limit=False):
        if self.provider=='ollama':
            # The public v3 entry point never accepts Ollama. This preserves a
            # bounded loopback-only fixture for the fixed child-worker tests.
            return super().preflight(report,require_verified_input_limit=require_verified_input_limit)
        if (self.provider!='openrouter' or self.model!=contract.POLICY['model']
                or self.parameters!=tuple(contract.POLICY['parameters'])):
            raise ValueError('fixed_v3_candidate_required')
        result=contract.preview(report)
        prompt.require_verified_limit(require_verified_input_limit)
        return {'messages':result['payload']['messages'],'payload':result['payload'],
                'audit':result['input_preflight']}
