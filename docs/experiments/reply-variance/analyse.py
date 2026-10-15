import json, re, statistics as st, itertools, difflib, collections
rows=[json.loads(l) for l in open('results.jsonl')]
g=collections.defaultdict(list)
for r in rows: g[(r['activity'],r['text'])].append(r)
tok=lambda s:set(re.findall(r"\w+",s.lower()))
head=lambda s:[h.strip().lower() for h in re.findall(r"^#{1,4}\s*(.+)$",s,re.M)]
nq=lambda s:len(re.findall(r"^\s*\d+[.)]",s,re.M))
def pair(f,xs): 
    v=[f(a,b) for a,b in itertools.combinations(xs,2)]; return sum(v)/len(v)
out=collections.defaultdict(list)
fails=[r for r in rows if r['err'] or len(r['out'])<80]
for (act,t),rs in g.items():
    o=[r['out'] for r in rs if not r['err']]
    if len(o)<2: continue
    L=[len(x) for x in o]
    jac=pair(lambda a,b:len(tok(a)&tok(b))/len(tok(a)|tok(b)),o)
    seq=pair(lambda a,b:difflib.SequenceMatcher(None,a,b).quick_ratio() if False else difflib.SequenceMatcher(None,a,b,autojunk=False).ratio(),o)
    same_head=len({tuple(head(x)) for x in o})==1
    cv=st.pstdev(L)/st.mean(L)
    qs={nq(x) for x in o}
    out[act].append((t,jac,seq,cv,same_head,qs,min(L),max(L)))
print(f"{'activity':24}{'jaccard':>8}{'seqratio':>9}{'lenCV':>7}{'sameHeadings':>14}  qCounts")
for act,v in out.items():
    print(f"{act:24}{st.mean(x[1] for x in v):8.2f}{st.mean(x[2] for x in v):9.2f}{st.mean(x[3] for x in v):7.2f}"
          f"{sum(x[4] for x in v):>9}/{len(v)}  {[sorted(x[5]) for x in v]}")
print("\nper text/activity:")
for act,v in out.items():
    for x in v: print(f"  {act:22}{x[0]:7} jac={x[1]:.2f} seq={x[2]:.2f} lenCV={x[3]:.2f} len {x[6]}-{x[7]} headings_same={x[4]}")
print("\nfailures/short:",[(r['text'],r['activity'],r['run'],r['err']) for r in fails])
print("secs mean by model:",{m:round(st.mean(r['secs'] for r in rows if r['model']==m and r['secs']),1) for m in {r['model'] for r in rows}})
