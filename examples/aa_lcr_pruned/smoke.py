"""Run the native CLI against a credential-free synthetic model and judge endpoint.

This checks transport, selection, contract judging and reporting, not model quality.
"""

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class FixtureEndpoint(BaseHTTPRequestHandler):
    """Return deterministic answers and valid judge verdicts for synthetic questions."""

    def do_POST(self) -> None:
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        content = '{"verdict":"CORRECT"}' if payload['model'] == 'fixture-judge' else 'Answer'
        body = json.dumps({
            'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': payload['model'],
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': content}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        }).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    """Dispatch a genuine CLI evaluation with an explicit local judge configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=Path('outputs/aa-lcr-pruned-smoke'))
    args = parser.parse_args()
    data = Path(__file__).resolve().parent / 'data'
    dataset_args = {'aa_lcr_pruned': {
        'local_path': str(data/'questions.jsonl'), 'subset_list': ['fixture'],
        'extra_params': {'reference_path': str(data/'references.json'), 'text_dir': str(data/'texts'),
                         'pruning_strategy': 'metadata_stratified', 'prune_ratio': 0.25},
    }}
    server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureEndpoint)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/v1'
    judge = {'strategy': 'llm', 'models': [{
        'model_id': 'fixture-judge', 'eval_type': 'openai_api', 'api_url': url, 'api_key': 'fixture-only',
    }]}
    try:
        result = subprocess.run([
            sys.executable, '-m', 'evalscope.cli.cli', 'eval', '--model', 'unseen', '--eval-type', 'openai_api',
            '--api-url', url, '--api-key', 'fixture-only', '--datasets', 'aa_lcr_pruned',
            '--dataset-args', json.dumps(dataset_args), '--judge', json.dumps(judge),
            '--eval-batch-size', '1', '--work-dir', str(args.work_dir), '--no-timestamp',
        ], timeout=120)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
