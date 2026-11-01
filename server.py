#!/usr/bin/env python3
import json, os, hashlib, secrets, random, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from datetime import datetime

DATA_FILE = 'data.json'
SESSIONS = {}
ADMIN_SESSIONS = set()

def load():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f: return json.load(f)
        except: pass
    return {'users':{}, 'requests':[], 'items':['1','2','3','4','5','6','7','8'],
            'forced':'', 'adminPassword':'anthony1234', 'history':[]}

def save(d):
    with open(DATA_FILE,'w') as f: json.dump(d, f)

def h(pw): return hashlib.sha256(pw.encode()).hexdigest()
def now(): return datetime.now().isoformat(timespec='seconds')

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass

    def _json(self, obj, status=200):
        b = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(b)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers(); self.wfile.write(b)

    def _body(self):
        try:
            n = int(self.headers.get('Content-Length',0))
            return json.loads(self.rfile.read(n)) if n else {}
        except: return {}

    def _tok(self):
        a = self.headers.get('Authorization','')
        return a[7:] if a.startswith('Bearer ') else None

    def _user(self):
        t = self._tok()
        return SESSIONS.get(t) if t else None

    def _admin(self):
        t = self._tok()
        return t in ADMIN_SESSIONS if t else False

    def do_GET(self):
        p = urlparse(self.path).path
        d = load()

        if p in ('/','/index.html'):
            try:
                with open('index.html','rb') as f: c = f.read()
            except:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(c)))
            self.end_headers(); self.wfile.write(c); return

        if p == '/api/items':
            return self._json({'items': d['items'], 'forced': d['forced']})

        if p == '/api/me':
            return self._json({'user': self._user(), 'admin': self._admin()})

        if p == '/api/bets/mine':
            u = self._user()
            if not u: return self._json({'error':'no auth'}, 401)
            mine = [r for r in d['requests'] if r['username']==u]
            return self._json({'bets': mine})

        if p == '/api/history':
            return self._json({'history': d['history']})

        if p == '/api/admin/bets':
            if not self._admin(): return self._json({'error':'no auth'}, 401)
            return self._json({'bets': d['requests']})

        self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path).path
        d = load()
        b = self._body()

        if p == '/api/register':
            u = (b.get('username') or '').strip()
            pw = b.get('password') or ''
            if len(u)<3: return self._json({'error':'Usuario mínimo 3 caracteres'}, 400)
            if len(pw)<4: return self._json({'error':'Contraseña mínimo 4 caracteres'}, 400)
            if u in d['users']: return self._json({'error':'Ese usuario ya existe'}, 400)
            d['users'][u] = {'pass': h(pw), 'createdAt': now()}
            save(d)
            tok = secrets.token_urlsafe(24); SESSIONS[tok]=u
            return self._json({'token':tok,'username':u})

        if p == '/api/login':
            u = b.get('username',''); pw = b.get('password','')
            if u not in d['users']: return self._json({'error':'Usuario no existe'}, 401)
            if d['users'][u]['pass'] != h(pw): return self._json({'error':'Contraseña incorrecta'}, 401)
            tok = secrets.token_urlsafe(24); SESSIONS[tok]=u
            return self._json({'token':tok,'username':u})

        if p == '/api/admin/login':
            if b.get('password') != d['adminPassword']:
                return self._json({'error':'Contraseña incorrecta'}, 401)
            tok = secrets.token_urlsafe(24); ADMIN_SESSIONS.add(tok)
            return self._json({'token':tok})

        if p == '/api/bet':
            u = self._user()
            if not u: return self._json({'error':'no auth'}, 401)
            active = [r for r in d['requests'] if r['username']==u and r['status'] in ('created','pending','approved')]
            if active: return self._json({'error':'Ya tienes una apuesta activa'}, 400)
            bet = {'id': secrets.token_hex(8), 'username': u,
                   'num': str(b.get('num')), 'bet': int(b.get('bet')), 'win': int(b.get('win')),
                   'status':'created', 'result':None, 'createdAt':now(), 'resolvedAt':None}
            d['requests'].insert(0, bet); save(d)
            return self._json({'bet':bet})

        if p == '/api/bet/paid':
            u = self._user()
            if not u: return self._json({'error':'no auth'}, 401)
            for r in d['requests']:
                if r['id']==b.get('id') and r['username']==u and r['status']=='created':
                    r['status']='pending'; save(d)
                    return self._json({'ok':True})
            return self._json({'error':'no encontrada'}, 404)

        if p == '/api/bet/cancel':
            u = self._user()
            if not u: return self._json({'error':'no auth'}, 401)
            d['requests'] = [r for r in d['requests']
                if not (r['id']==b.get('id') and r['username']==u and r['status'] in ('created','pending'))]
            save(d); return self._json({'ok':True})

        if p == '/api/admin/approve':
            if not self._admin(): return self._json({'error':'no auth'}, 401)
            for r in d['requests']:
                if r['id']==b.get('id') and r['status']=='pending':
                    r['status']='approved'; save(d)
                    return self._json({'ok':True})
            return self._json({'error':'no encontrada'}, 404)

        if p == '/api/admin/reject':
            if not self._admin(): return self._json({'error':'no auth'}, 401)
            for r in d['requests']:
                if r['id']==b.get('id') and r['status']=='pending':
                    r['status']='rejected'; save(d)
                    return self._json({'ok':True})
            return self._json({'error':'no encontrada'}, 404)

        if p == '/api/admin/items':
            if not self._admin(): return self._json({'error':'no auth'}, 401)
            its = b.get('items', [])
            if not isinstance(its,list) or len(its)<2:
                return self._json({'error':'Mínimo 2 opciones'}, 400)
            d['items'] = [str(x).strip() for x in its if str(x).strip()]
            f = str(b.get('forced',''))
            d['forced'] = f if f in d['items'] else ''
            save(d); return self._json({'ok':True})

        if p == '/api/spin':
            u = self._user()
            its = d['items']
            if not its: return self._json({'error':'Sin opciones'}, 400)
            result = d['forced'] if d['forced'] in its else random.choice(its)
            d['history'].insert(0, {'v':result, 't':datetime.now().strftime('%H:%M:%S')})
            d['history'] = d['history'][:50]
            resolved = None
            if u:
                for r in d['requests']:
                    if r['username']==u and r['status']=='approved':
                        r['result'] = result
                        r['status'] = 'won' if str(result)==str(r['num']) else 'lost'
                        r['resolvedAt'] = now()
                        resolved = r
                        break
            save(d)
            return self._json({'result': result, 'resolved': resolved})

        self.send_error(404)

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv)>1 else 8080
    print('\n🎡 Servidor en: http://0.0.0.0:%d\n' % port)
    print('   En este movil: http://localhost:%d\n' % port)
    print('   En otro movil (misma WiFi): http://TU_IP:%d\n' % port)
    HTTPServer(('0.0.0.0', port), H).serve_forever()
