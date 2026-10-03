import gzip, io, json, os, shutil, tempfile, time, uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

import requests

import _radar_engine as radar_engine
from _radar_config import SOURCES_CONFIG, PROFILE_DATA, SEED_ITEMS, SEED_STATUS, SEED_CHAINS

BATCH_SIZE = 5
STORE_TOKEN = os.environ.get('RADAR_INTERNAL_TOKEN', 'teacher-radar-internal-v1')


def _origin(handler):
    host = handler.headers.get('X-Forwarded-Host') or handler.headers.get('Host')
    proto = handler.headers.get('X-Forwarded-Proto') or 'https'
    return f'{proto}://{host}'

def _preview_auth(handler):
    """Forward EdgeOne preview-link auth params to same-project subrequests."""
    try:
        q = parse_qs(urlparse(handler.path).query)
        return {k:q[k][0] for k in ('eo_token','eo_time') if q.get(k)}
    except Exception:
        return {}


def _api_url(origin, path, auth=None, extra=None):
    params={}
    if auth: params.update(auth)
    if extra: params.update(extra)
    qs=urlencode(params)
    return f"{origin}{path}" + (f"?{qs}" if qs else "")


def _get_json(origin, kind, fallback, auth=None):
    try:
        r = requests.get(_api_url(origin, '/api/radar-data', auth, {'kind':kind}), timeout=15, headers={'User-Agent':'TeacherExamRadar/Internal'})
        if r.ok and 'application/json' in (r.headers.get('Content-Type') or ''):
            return r.json()
    except Exception:
        pass
    return fallback


def _store_json(origin, kind, obj, auth=None):
    raw = json.dumps(obj, ensure_ascii=False, separators=(',',':')).encode('utf-8')
    body = gzip.compress(raw, compresslevel=6)
    r = requests.post(
        _api_url(origin, '/api/radar-store', auth, {'kind':kind}), data=body, timeout=25,
        headers={'Content-Type':'application/gzip','Content-Encoding':'gzip','X-Radar-Token':STORE_TOKEN,'User-Agent':'TeacherExamRadar/Internal'}
    )
    r.raise_for_status()


def _read_body(handler):
    n = int(handler.headers.get('Content-Length', '0') or 0)
    if not n:
        return {}
    try:
        return json.loads(handler.rfile.read(n).decode('utf-8'))
    except Exception:
        return {}


def _minutes_since(iso):
    if not iso: return 999999
    try:
        from datetime import datetime, timezone
        d = datetime.fromisoformat(iso.replace('Z','+00:00'))
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc)-d.astimezone(timezone.utc)).total_seconds()/60
    except Exception:
        return 999999


class handler(BaseHTTPRequestHandler):
    def _reply(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(200, {'ok': True, 'service':'teacher-exam-radar-crawler','batch_size':BATCH_SIZE})

    def do_POST(self):
        started = time.time()
        payload = _read_body(self)
        mode = payload.get('mode','quick')
        if mode not in ('quick','deep'): mode='quick'
        origin = _origin(self)
        auth = _preview_auth(self)
        runtime = _get_json(origin, 'runtime', {'last_runs':{},'deep_cursor':0}, auth)
        sources = SOURCES_CONFIG['sources']
        # quick: explicit batch; deep: rotate through small batches automatically
        if mode == 'deep' and payload.get('batch') in (None, 'next'):
            batch_size = min(int(payload.get('batch_size') or 3), 3)
            start = int(runtime.get('deep_cursor',0) or 0) % max(1,len(sources))
            ids = [sources[(start+i)%len(sources)]['id'] for i in range(batch_size)]
            next_cursor = (start + batch_size) % len(sources)
            run_key = f'deep:{start}'
        else:
            batch_size = min(max(1,int(payload.get('batch_size') or BATCH_SIZE)), BATCH_SIZE)
            batch = max(0,int(payload.get('batch') or 0))
            start = batch * batch_size
            ids = [s['id'] for s in sources[start:start+batch_size]]
            next_cursor = runtime.get('deep_cursor',0)
            run_key = f'{mode}:{batch}'
        if not ids:
            return self._reply(200, {'ok': True, 'skipped': True, 'reason':'empty batch'})
        # Protect quotas from accidental repeated clicks; schedule/manual can retry after 20 min quick, 6h deep.
        wait = 20 if mode == 'quick' else 360
        last = (runtime.get('last_runs') or {}).get(run_key,'')
        if _minutes_since(last) < wait and not bool(payload.get('force')):
            return self._reply(200, {'ok': True, 'skipped': True, 'reason':'recently scanned', 'run_key':run_key, 'source_ids':ids})

        tmp = Path(tempfile.mkdtemp(prefix='radar-'))
        try:
            (tmp/'docs/data').mkdir(parents=True, exist_ok=True)
            items = _get_json(origin,'items',SEED_ITEMS,auth)
            status = _get_json(origin,'status',SEED_STATUS,auth)
            chains = _get_json(origin,'chains',SEED_CHAINS,auth)
            (tmp/'docs/data/items.json').write_text(json.dumps(items,ensure_ascii=False),encoding='utf-8')
            (tmp/'docs/data/source_status.json').write_text(json.dumps(status,ensure_ascii=False),encoding='utf-8')
            (tmp/'docs/data/chains.json').write_text(json.dumps(chains,ensure_ascii=False),encoding='utf-8')
            # Cloud Functions has a 120s ceiling. Quick mode deliberately caps pagination per source.
            cfg = json.loads(json.dumps(SOURCES_CONFIG,ensure_ascii=False))
            if mode == 'quick':
                for s in cfg['sources']:
                    s['quick_pages'] = 1
            radar_engine.configure(tmp, cfg, PROFILE_DATA)
            summary = radar_engine.main(mode, source_ids=ids)
            out_items = json.loads((tmp/'docs/data/items.json').read_text(encoding='utf-8'))
            out_status = json.loads((tmp/'docs/data/source_status.json').read_text(encoding='utf-8'))
            out_chains = json.loads((tmp/'docs/data/chains.json').read_text(encoding='utf-8'))
            _store_json(origin,'items',out_items,auth)
            _store_json(origin,'status',out_status,auth)
            _store_json(origin,'chains',out_chains,auth)
            from datetime import datetime, timezone
            runtime.setdefault('last_runs',{})[run_key] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            runtime['last_mode']=mode; runtime['last_batch_sources']=ids; runtime['last_duration_seconds']=round(time.time()-started,2)
            if mode=='deep': runtime['deep_cursor']=next_cursor
            _store_json(origin,'runtime',runtime,auth)
            summary.update({'ok':True,'run_key':run_key,'source_ids':ids,'duration_seconds':round(time.time()-started,2)})
            self._reply(200, summary)
        except Exception as e:
            self._reply(500, {'ok':False,'error':str(e)[:500],'run_key':run_key,'source_ids':ids,'duration_seconds':round(time.time()-started,2)})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
