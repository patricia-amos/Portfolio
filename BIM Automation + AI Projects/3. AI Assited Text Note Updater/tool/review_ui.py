"""Local review UI (browser). Standard library only. Blocks until the user clicks 'Save & finish'.

Reads results.json, then writes (next to it): results.json (decisions kept, so you can resume),
approved.json (only approved + actually changed notes -> feed back into Dynamo) and review_decisions.csv.
CLI: python review_ui.py results.json
"""
import csv, json, os, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ollama_client import match_newlines


def _export(items, folder):
    approved = []
    for it in items:
        if it.get("decision") == "approved":
            new = match_newlines(it["old_text"], it["final_text"])
            if new != it["old_text"]:
                approved.append({k: it.get(k) for k in ("unique_id", "element_id", "sheet_number")}
                                | {"old_text": it["old_text"], "new_text": new, "delete": not new.strip()})
    with open(os.path.join(folder, "approved.json"), "w", encoding="utf-8") as f:
        json.dump(approved, f, indent=2, ensure_ascii=False)
    with open(os.path.join(folder, "review_decisions.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["sheet_number", "view_name", "element_id", "unique_id", "old_text", "ai_proposal",
                    "final_text", "decision", "flags", "skip_reason"])
        for it in items:
            w.writerow([it.get("sheet_number"), it.get("view_name"), it.get("element_id"), it.get("unique_id"),
                        it["old_text"], it["new_text"], it["final_text"], it.get("decision") or "undecided",
                        "; ".join(it.get("flags", [])), it.get("skip_reason") or ""])
    return approved


def _open_browser(url, folder):
    """webbrowser.open often does nothing inside Revit/Dynamo, so try Windows' own launcher first."""
    try:
        with open(os.path.join(folder, "review_url.txt"), "w") as f:
            f.write(url)
    except Exception:
        pass
    for attempt in (lambda: os.startfile(url),
                    lambda: subprocess.Popen(["cmd", "/c", "start", "", url], creationflags=0x08000000),
                    lambda: webbrowser.open(url)):
        try:
            attempt()
            return
        except Exception:
            continue


def run(results_path, port=8765, open_browser=True, timeout_min=None):
    """Blocks until you click Save & finish / Cancel (or timeout_min minutes pass). Returns path to approved.json."""
    folder = os.path.dirname(os.path.abspath(results_path))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype="application/json"):
            b = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == "/api/data":
                with open(results_path, encoding="utf-8") as f:
                    self._send(f.read())
            else:
                self._send(PAGE, "text/html")

        def do_POST(self):
            items = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            with open(results_path, encoding="utf-8") as f:
                doc = json.load(f)
            doc["items"] = items
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
            if self.path == "/api/finish":
                _export(items, folder)
            if self.path in ("/api/finish", "/api/cancel"):
                threading.Thread(target=server.shutdown).start()
            self._send('{"ok":true}')

    approved = os.path.join(folder, "approved.json")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), H)
    except OSError:
        raise Exception("Port %d is busy (an earlier review page may still be running). "
                        "Use review_ui.run(path, port=%d) or restart Dynamo." % (port, port + 1))
    if os.path.exists(approved):
        os.remove(approved)  # never reuse an old approval
    timer = None
    if timeout_min:
        timer = threading.Timer(timeout_min * 60, server.shutdown)
        timer.daemon = True
        timer.start()
    if open_browser:
        _open_browser("http://127.0.0.1:%d" % port, folder)
    server.serve_forever()
    server.server_close()
    if timer:
        timer.cancel()
    if not os.path.exists(approved):  # cancelled or timed out: nothing gets applied
        with open(approved, "w", encoding="utf-8") as f:
            f.write("[]")
    return approved


PAGE = r"""<!doctype html><meta charset=utf-8><title>Text note review</title>
<style>
body{font:14px system-ui,sans-serif;margin:0;background:#f4f5f7;color:#1c1e21}
header{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #d8dbe0;padding:10px 20px;display:flex;gap:12px;align-items:center}
h1{font-size:17px;margin:0 auto 0 0}
table{border-collapse:collapse;width:calc(100% - 40px);margin:16px 20px;background:#fff}
th,td{border:1px solid #e1e4e8;padding:8px 10px;vertical-align:top;text-align:left}
th{background:#fafbfc}td:first-child{width:110px}td:last-child{width:150px;white-space:nowrap}
.t{white-space:pre-wrap}.pv{margin-top:4px;color:#555;font-size:13px}
textarea{width:100%;box-sizing:border-box;font:inherit;padding:6px}
del{background:#ffc9c9;text-decoration:line-through}mark{background:#fff0a0;color:inherit}.legend{font-size:12px}
.flag{color:#a15c00;font-size:12px;margin-top:4px}
tr.approved{background:#f1faf3}tr.rejected{background:#fbf1f1;opacity:.7}
button{padding:6px 10px;border:1px solid #bbb;border-radius:6px;background:#fff;cursor:pointer}
button.on{background:#1f7a3a;color:#fff;border-color:#1f7a3a}button[data-d=rejected].on{background:#b33;border-color:#b33}
.primary{background:#0b5fff;color:#fff;border-color:#0b5fff}
</style>
<header><h1>Text note review</h1><span id=count></span><span class=legend><mark>changed</mark> <del>removed</del></span>
<select id=filter><option value=review>To review</option><option value=flagged>Flagged</option>
<option value=approved>Approved</option><option value=rejected>Rejected</option>
<option value=unchanged>Unchanged</option><option value=skipped>Skipped (not applicable)</option><option value=all>All</option></select>
<button id=clean>Approve all clean</button><button id=cancel>Cancel</button><button id=finish class=primary>Save &amp; finish</button></header>
<table><thead><tr><th>Sheet</th><th>Original</th><th>Proposed (editable)</th><th></th></tr></thead><tbody id=rows></tbody></table>
<script>
let items=[];
const $=id=>document.getElementById(id);
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const nl=s=>s.replace(/\r\n|\r/g,'\n');
const ws=x=>/^\s+$/.test(x);
const same=(x,y)=>{x=x.toLowerCase();y=y.toLowerCase();if(x.length<3||y.length<3)return false;let c=0;
 while(c<x.length&&c<y.length&&x[c]===y[c])c++;return c>=Math.max(3,Math.min(x.length,y.length)-2)};
function oldSide(d,s){ /* removed words that were reworded -> yellow, the rest -> red strikethrough */
 const dw=d.filter(x=>!ws(x)),paired=new Set();
 s.filter(x=>!ws(x)).forEach(y=>{const i=dw.findIndex((x,k)=>!paired.has(k)&&same(x,y));if(i>=0)paired.add(i)});
 let wi=0;const cls=d.map(x=>ws(x)?null:(paired.has(wi++)?'mark':'del'));
 for(let k=0;k<cls.length;k++)if(cls[k]===null&&k>0)cls[k]=cls[k-1];
 for(let k=cls.length-1;k>=0;k--)if(cls[k]===null)cls[k]=k+1<cls.length?cls[k+1]:'del';
 let out='',k=0;while(k<d.length){const c=cls[k];let seg='';while(k<d.length&&cls[k]===c)seg+=d[k++];out+='<'+c+'>'+esc(seg)+'</'+c+'>'}
 return out}
function diff(a,b){a=nl(a);b=nl(b);const tk=s=>s.match(/\s+|[\w'’\-\/]+|[^\s\w]/g)||[],A=tk(a),B=tk(b),n=A.length,m=B.length;
 const L=Array.from({length:n+1},()=>new Array(m+1).fill(0));
 for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)L[i][j]=A[i]===B[j]?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
 const ops=[];let i=0,j=0;
 while(i<n&&j<m){if(A[i]===B[j]){ops.push(['eq',A[i]]);i++;j++}
  else if(L[i+1][j]>=L[i][j+1])ops.push(['del',A[i++]]);else ops.push(['ins',B[j++]])}
 while(i<n)ops.push(['del',A[i++]]);while(j<m)ops.push(['ins',B[j++]]);
 let o='',p='',k=0;
 while(k<ops.length){
  if(ops[k][0]=='eq'){o+=esc(ops[k][1]);p+=esc(ops[k][1]);k++;continue}
  const d=[],s=[];
  while(k<ops.length&&ops[k][0]!='eq'){(ops[k][0]=='del'?d:s).push(ops[k][1]);k++}
  if(d.length)o+=s.length?oldSide(d,s):'<del>'+esc(d.join(''))+'</del>';  /* removed: red + strikethrough */
  if(s.length)p+='<mark>'+esc(s.join(''))+'</mark>'}                     /* reworded or added: yellow */
 return[o,p]}
const show={review:i=>!i.decision&&i.status!='unchanged'&&i.status!='skipped',flagged:i=>i.status=='flagged',approved:i=>i.decision=='approved',
 rejected:i=>i.decision=='rejected',unchanged:i=>i.status=='unchanged',skipped:i=>i.status=='skipped',all:()=>true};
function row(it,i){const[o,p]=diff(it.old_text,it.final_text);
 const b=d=>`<button data-d=${d} class="${it.decision==d?'on':''}">${d=='approved'?'Approve':'Reject'}</button> `;
 return `<tr data-i=${i} class="${it.decision||''}"><td><b>${esc(it.sheet_number||'')}</b><br><small>${esc(it.view_name||'')}</small></td>
 <td class=t>${o}</td><td><textarea rows=${Math.max(2,nl(it.final_text).split('\n').length+1)}>${esc(nl(it.final_text))}</textarea>
 <div class="t pv">${p}</div>${it.skip_reason?`<div class=flag>Skipped: ${esc(it.skip_reason)}</div>`:''}${(it.flags||[]).map(f=>`<div class=flag>&#9888; ${esc(f)}</div>`).join('')}</td><td>${b('approved')}${b('rejected')}</td></tr>`}
function render(){const f=show[$('filter').value];
 $('rows').innerHTML=items.map((it,i)=>f(it)?row(it,i):'').join('');
 const c=k=>items.filter(i=>i.decision==k).length;
 $('count').textContent=`${c('approved')} approved · ${c('rejected')} rejected · ${items.filter(show.review).length} to review · ${items.filter(show.skipped).length} skipped`}
let t;const save=()=>{clearTimeout(t);t=setTimeout(()=>fetch('/api/save',{method:'POST',body:JSON.stringify(items)}),300)};
$('rows').onclick=e=>{const d=e.target.dataset.d;if(!d)return;const it=items[e.target.closest('tr').dataset.i];
 it.decision=it.decision==d?null:d;render();save()};
$('rows').oninput=e=>{const tr=e.target.closest('tr'),it=items[tr.dataset.i];it.final_text=e.target.value;it.decision='approved';
 tr.className='approved';tr.querySelector('.pv').innerHTML=diff(it.old_text,it.final_text)[1];
 tr.querySelector('[data-d=approved]').classList.add('on');tr.querySelector('[data-d=rejected]').classList.remove('on');save()};
$('filter').onchange=render;
$('clean').onclick=()=>{items.forEach(i=>{if(!i.decision&&i.status=='pending')i.decision='approved'});render();save()};
$('finish').onclick=async()=>{const left=items.filter(show.review).length;
 if(left&&!confirm(left+' notes are undecided and will NOT be applied. Finish?'))return;
 await fetch('/api/finish',{method:'POST',body:JSON.stringify(items)});
 document.body.innerHTML='<h2 style="padding:20px">Done. Close this tab and return to Dynamo.</h2>'};
$('cancel').onclick=async()=>{if(!confirm('Cancel? Nothing will be applied to the model.'))return;
 await fetch('/api/cancel',{method:'POST',body:JSON.stringify(items)});
 document.body.innerHTML='<h2 style="padding:20px">Cancelled. Nothing was applied. You can close this tab.</h2>'};
fetch('/api/data').then(r=>r.json()).then(d=>{items=d.items;render()});
</script>"""

if __name__ == "__main__":
    run(sys.argv[1])
