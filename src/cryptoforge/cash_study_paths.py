"""A single canonical local namespace per frozen protocol, including aliases."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from cryptoforge.live_learning_protocol import validate_protocol

DEFAULT_PROTOCOL=Path('config/live-cash-recovery-protocol-v1.json')
LEGACY_PROTOCOL_SHA256='fb61812ca0eaf21bc65871598b58b91bc96f863ee8ebe8af9755e0dda385db43'


@dataclass(frozen=True)
class CashStudyPaths:
    protocol_sha256: str
    root: Path
    training: Path
    candidate: Path
    predictions: Path
    readiness: Path

    @property
    def shadow_report(self):
        return self.root/('cash-shadow-report.json' if self.protocol_sha256==LEGACY_PROTOCOL_SHA256 else 'shadow-report.json')

    @property
    def execution_policy(self):
        return Path('config/paper-execution-policy-v1.json') if self.protocol_sha256==LEGACY_PROTOCOL_SHA256 else self.root/'paper-execution-policy-v1.json'

    @property
    def acceptance_policy(self):
        return Path('config/paper-acceptance-policy-v1.json') if self.protocol_sha256==LEGACY_PROTOCOL_SHA256 else self.root/'paper-acceptance-policy-v1.json'

    @property
    def acceptance_registry(self):return self.root/'paper-acceptance-registry.sqlite'

    @property
    def paper_results(self):return self.root/'cash-paper-results.json'

    @property
    def paper_acceptance(self):return self.root/'cash-paper-acceptance.json'

    @property
    def paper_worker_report(self):return self.root/'cash-paper-worker-report.json'

    def paper_role_paths(self,role):
        if role not in {'candidate','baseline_control','stress_candidate'}:raise ValueError('supported isolated paper role required')
        prefix='cash-paper' if role=='candidate' else 'cash-paper-'+role.replace('_','-')
        return self.root/(prefix+'-wallet.sqlite'),self.root/(prefix+'-worker.sqlite')


def load_cash_study(protocol_path,*,state_root=Path('.local/state')):
    raw=protocol_path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if sha!=protocol_path.with_suffix('.sha256').read_text().strip():raise ValueError('frozen live protocol checksum mismatch')
    protocol=json.loads(raw);validate_protocol(protocol)
    if sha==LEGACY_PROTOCOL_SHA256:
        paths=CashStudyPaths(sha,state_root,state_root/'cash-training',state_root/'cash-shadow-candidate.json',
            state_root/'cash-shadow-predictions.sqlite',state_root/'live-learning-readiness.json')
        return protocol,paths
    root=state_root/'cash-studies'/sha
    return protocol,CashStudyPaths(sha,root,root/'training',root/'candidate.json',root/'predictions.sqlite',root/'readiness.json')


def cash_study_paths(protocol_path,*,state_root=Path('.local/state')):
    return load_cash_study(protocol_path,state_root=state_root)[1]
