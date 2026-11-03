import base64, json, multiprocessing, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from scripts.threads_remote_claim import GitHubClaims, ClaimError

SLOT='2026-10-29T12:00:00+09:00'
class Handler(BaseHTTPRequestHandler):
 data=None; lock=threading.Lock()
 def log_message(self,*args): pass
 def do_PUT(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  with self.lock:
   if Handler.data is not None and 'sha' not in body:
    self.send_response(422);self.end_headers();return
   if 'sha' in body and (Handler.data is None or body['sha'] != Handler.data['sha']):
    self.send_response(409);self.end_headers();return
   sha='v1' if Handler.data is None else 'v2'
   Handler.data={'sha':sha,'content':body['content']}
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'content':{'sha':sha}}).encode())
 def do_GET(self):
  if Handler.data is None:self.send_response(404);self.end_headers();return
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps(Handler.data).encode())

def client(port):
 def opener(req, timeout):
  redirect=Request('http://127.0.0.1:'+str(port)+req.full_url.split('api.github.com',1)[1],data=req.data,method=req.get_method(),headers={'Content-Type':'application/json'})
  return urlopen(redirect,timeout=timeout)
 return GitHubClaims('a/b','claims','fake',opener)

def worker(port,q):
 try:
  claim=client(port);sha=claim.begin(SLOT,'99');q.put(('send',sha))
 except ClaimError:q.put(('hold',None))

class RemoteTests(unittest.TestCase):
 def setUp(self):
  Handler.data=None;self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown);self.port=self.server.server_port
 def test_parallel_processes_and_restart(self):
  q=multiprocessing.Queue();p=[multiprocessing.Process(target=worker,args=(self.port,q)) for _ in range(6)]
  for x in p:x.start()
  for x in p:x.join(5);self.assertEqual(x.exitcode,0)
  results=[q.get(timeout=2) for _ in p];self.assertEqual(sum(x[0]=='send' for x in results),1)
  claim=client(self.port);self.assertEqual(claim.read(SLOT)['state'],'sending')
  with self.assertRaises(ClaimError):claim.begin(SLOT,'101')
  claim.accept(SLOT,'99','v1','123');self.assertEqual(client(self.port).read(SLOT)['post_id'],'123')
  with self.assertRaises(ClaimError):claim.begin(SLOT,'102')
 def test_missing_remote_no_send(self):
  c=GitHubClaims('a/b','claims','fake',lambda *a,**k: (_ for _ in ()).throw(TimeoutError()))
  with self.assertRaises(ClaimError):c.begin(SLOT,'2')
 def test_stale_receipt_does_not_overwrite(self):
  c=client(self.port);c.begin(SLOT,'99')
  with self.assertRaises(ClaimError):c.accept(SLOT,'99','old','123')
  self.assertEqual(c.read(SLOT)['state'],'sending')
if __name__=='__main__':unittest.main()
