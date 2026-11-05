"""Offline-first diagnostics/advice CLI. Writes proposals, never executes them."""
import argparse
from datetime import datetime, timezone
import os
import sqlite3
from pathlib import Path

from cryptoforge.llm_research_advisor import FreeAdvisor, DEFAULT_MODEL, jobpilot_credentials
from cryptoforge.llm_research_contracts import strict_json, validate_proposal
from cryptoforge.llm_research_requests import ResearchRequests
from cryptoforge.research_training_diagnostics import build_diagnostics, canonical, digest, validate_diagnostics


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--input', type=Path, help='closed-schema development prediction export')
    inputs.add_argument('--experiment-receipt', type=Path, help='completed offline experiment receipt')
    parser.add_argument('--output', type=Path, required=True, help='new private receipt file; never overwritten')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--mock-response', type=Path)
    mode.add_argument('--provider', choices=('openrouter', 'ollama'))
    parser.add_argument('--jobpilot-env', type=Path, help='explicit credential source; no values are logged')
    parser.add_argument('--request-ledger', type=Path, default=Path('.local/llm-training-api.sqlite'))
    parser.add_argument('--daily-max-requests', type=int, default=5)
    parser.add_argument('--model', default=None)
    parser.add_argument('--ollama-url', default=None)
    args = parser.parse_args(argv)
    if args.jobpilot_env and not args.provider:
        parser.error('--jobpilot-env requires --provider')
    # Reserve before any network request; crashes leave a visible started receipt.
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        parser.error('output must be a new writable file')
    receipt = {'schema_version': 'llm-research-receipt-v1', 'status': 'started',
               'started_at': datetime.now(timezone.utc).isoformat(), 'training_executed': False}
    with os.fdopen(fd, 'w') as output:
        output.write(canonical(receipt) + '\n')
        output.flush()
        os.fsync(output.fileno())
        try:
            source = args.input or args.experiment_receipt
            if source.stat().st_size > 32_000_000:
                raise ValueError('development input too large')
            export = strict_json(source.read_text(), max_bytes=32_000_000)
            if args.input:
                report = build_diagnostics(export)
            else:
                if export.get('status') != 'completed' or export.get('command') != 'run':
                    raise ValueError('completed offline experiment receipt required')
                result = export['result']
                if digest(result['artifact']) != result['artifact_sha256']:
                    raise ValueError('experiment artifact checksum mismatch')
                report = validate_diagnostics(result['reports']['validation']['diagnostics'])
            receipt['diagnostics'] = report
            if args.mock_response:
                if args.mock_response.stat().st_size > 64_000:
                    raise ValueError('mock response too large')
                proposal = validate_proposal(strict_json(args.mock_response.read_text()), report)
                if args.experiment_receipt and proposal['parameter'] not in ('l2', 'threshold'):
                    raise ValueError('parameter unsupported by development-example worker')
                receipt['advice'] = {'provider': 'mock', 'proposal': proposal, 'report_sha256': digest(report)}
            elif args.provider:
                credentials = jobpilot_credentials(args.jobpilot_env) if args.jobpilot_env else {}
                key = os.environ.get('CRYPTOFORGE_OPENROUTER_API_KEY', credentials.get('OPENROUTER_API_KEY', ''))
                model = args.model or (DEFAULT_MODEL if args.provider == 'openrouter' else
                                      credentials.get('OLLAMA_MODEL', 'nemotron-3-nano:30b'))
                url = args.ollama_url or credentials.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
                parameters = ('l2', 'threshold') if args.experiment_receipt else ('l2', 'threshold', 'lookback_candles')
                advisor = FreeAdvisor(provider=args.provider, model=model, api_key=key, ollama_url=url, parameters=parameters)
                receipt['advice'] = ResearchRequests(args.request_ledger, daily_maximum=args.daily_max_requests).propose(advisor, report)
            receipt['status'] = 'completed'
            code = 0
        except (ValueError, RuntimeError, OSError, TypeError, KeyError, sqlite3.Error):
            # Do not serialize arbitrary exception text, server bodies or inputs.
            receipt['status'] = 'failed'
            receipt['error'] = 'input, proposal or provider validation failed; no experiment executed'
            code = 1
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        output.seek(0)
        output.truncate()
        output.write(canonical(receipt) + '\n')
        output.flush()
        os.fsync(output.fileno())
    print(f"Research receipt: {args.output} ({receipt['status']}); no training executed")
    return code


if __name__ == '__main__':
    raise SystemExit(main())
