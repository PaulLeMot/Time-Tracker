"""Explicit CLI; no service installation, database access or automatic network binding."""
import argparse
import json
import os
from pathlib import Path
import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=('gateway', 'worker'))
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text('utf-8-sig'))
    config['_config_file'] = str(Path(args.config).resolve())
    if args.role == 'worker':
        from .resources import restrict_compute
        job_handle = restrict_compute(memory_mb=config.get('service_memory_mb', 2048), cpu_percent=config.get('resources', {}).get('cpu_percent', 10))
        if os.name == 'nt':
            config['resources'] = config.get('resources', {}) | {'cpu_percent': None}
        from .worker import create_worker
        app = create_worker(config)
    else:
        from .gateway import create_gateway
        app = create_gateway(config)
    host = config.get('bind', '127.0.0.1')
    tls = {k: config[k] for k in ('ssl_certfile', 'ssl_keyfile') if config.get(k)}
    if host != '127.0.0.1' and (args.role != 'worker' or len(tls) != 2):
        raise ValueError('remote_worker_requires_tls')
    uvicorn.run(app, host=host, port=config['port'], workers=1, access_log=False, log_level='warning',
                proxy_headers=False, limit_concurrency=16, timeout_keep_alive=3, **tls)


if __name__ == '__main__':
    main()
