"""Repeat-run variance experiment. Read-only wrt the app; writes results.jsonl here."""
import json, sys, time, itertools
from concurrent.futures import ThreadPoolExecutor
APP = "/var/www/academic-reading/academic-reading/academic_reading_django"
sys.path.insert(0, APP)
import os; os.chdir(APP)
from reading.logic.corpus import load_library
from reading.logic.settings import load_config
from reading.logic.prompts import load_prompts, available_templates, build_messages
from reading.logic.llm import stream_reply, LLMError

TEXTS = ["de-01", "fr-01", "it-01", "zh-01"]
RUNS = 3
cfg, prompts = load_config(), load_prompts()
lib = {t.id: t for t in load_library()[1]}
level = cfg.level("intermediate")
acts = [a for a in cfg.activities if "user" in available_templates(a.id, prompts)]
opts = cfg.models.get("options", {})

def job(args):
    tid, act, run = args
    t = lib[tid]
    reply = "English" if act.response_language == "en" else t.language_name
    system, user = build_messages(act, t, level, reply, prompts, turn="user")
    model = cfg.model_for(t.lang)
    for attempt in range(3):
        t0 = time.time()
        try:
            out = "".join(stream_reply(model, system, user, opts))
            return dict(text=tid, activity=act.id, run=run, model=model, secs=round(time.time()-t0,1), out=out, err=None)
        except LLMError as e:
            err = str(e); time.sleep(5)
    return dict(text=tid, activity=act.id, run=run, model=model, secs=None, out="", err=err)

jobs = [(t, a, r) for t in TEXTS for a in acts for r in range(RUNS)]
print(len(jobs), "calls", flush=True)
with ThreadPoolExecutor(6) as ex, open("/tmp/claude-1000/-var-www-academic-reading/a49aaff5-5792-4367-b91c-86be26a3065f/scratchpad/exp/results.jsonl", "w") as f:
    for i, res in enumerate(ex.map(job, jobs), 1):
        f.write(json.dumps(res, ensure_ascii=False) + "\n"); f.flush()
        print(i, res["text"], res["activity"], res["run"], res["secs"], res["err"] or "", flush=True)
