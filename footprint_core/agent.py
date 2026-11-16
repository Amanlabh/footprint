"""footprint ask: a lean agent loop for small local models (the OpenCode harness is built for big ones).

  footprint ask "<question>" [--yes]

Each step the model must return one JSON action (Ollama structured output, so a 1.5B model can't
garble it): {"thought": <reasoning first>, "tool": bash|read|search|fetch|answer, "input": ...}.
Short system prompt, few tools, the real tool output fed back: the model reads instead of guessing.
bash asks before running each command unless --yes.
Browsing, no key needed: search = the whole web via Tavily + Wikipedia + Stack Overflow + GitHub + DuckDuckGo
instant answers. Tavily: your own TAVILY_API_KEY, else footprint's server when logged in (`footprint login`; the
server holds a key, daily limit, queries not stored), else Tavily keyless (rate-limited per user).
fetch = r.jina.ai reads the page as text.
Privacy: queries go to those sites (web queries via footprint's server when logged in), fetched URLs via Jina.
"""
import gzip, html, json, os, re, ssl, subprocess, sys, urllib.parse, urllib.request

from . import ollama, vault

MODEL = os.environ.get("FOOTPRINT_AGENT_MODEL", ollama.NAME)
STEPS = int(os.environ.get("FOOTPRINT_AGENT_STEPS", "6"))
CAP = 2000  # chars of tool output fed back: a small context fills fast
SYSTEM = """You are a coding assistant on the user's machine. Working directory: {cwd}
Reply with ONE JSON action per turn:
{{"thought": "<short reasoning: what you know, what you still need>", "tool": "<tool>", "input": "<input>"}}
Tools:
  bash    run a shell command (input: the command)
  read    read a file (input: its path)
  search  find web pages (input: a short query). Returns titles + URLs + snippets
  fetch   read one web page (input: a URL from search). Use it before answering from the web
  answer  your final answer to the user (input: the answer)
Rules: if the question already contains what you need (e.g. the code), answer directly, no tool.
Never claim a command ran, a file says something, or a fact is true unless a tool result above shows it.
Facts you might not know or that change (versions, prices, news, APIs, docs, people, anything after your training): search
the web first, then fetch the best page, then answer and name the source URL. Never ask the user to look it up.
Unsure? Use a tool. Still unsure after that? Say you don't know. Keep the answer short."""
FINAL = ("Now give your final answer with tool \"answer\". Use only what the question and the results above "
         "show; if they don't contain it, say you don't know.")
TOOLS = ["bash", "read", "search", "fetch", "answer"]


def schema(tools=TOOLS):
    return {"type": "object", "required": ["thought", "tool", "input"],
            "properties": {"thought": {"type": "string"}, "tool": {"enum": tools}, "input": {"type": "string"}}}


def _chat(messages, fmt):
    body = {"model": MODEL, "messages": messages, "stream": False, "format": fmt,
            "keep_alive": ollama.KEEP,
            "options": {"temperature": 0, "num_predict": 1024}}  # small models can loop inside one string forever
    r = urllib.request.urlopen(urllib.request.Request(ollama.URL + "/api/chat", json.dumps(body).encode()), timeout=600)
    return json.load(r)["message"]["content"]


def bash(cmd, yes=False):
    if not yes and input(f"  run `{cmd}`? [y/N] ").strip().lower() != "y":
        return "the user declined to run this command"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return f"exit {r.returncode}\n{r.stdout}{r.stderr}"
    except subprocess.TimeoutExpired:
        return "timed out after 120 s"


def read(path):
    try:
        return open(os.path.expanduser(path), encoding="utf-8", errors="replace").read()
    except OSError as e:
        return f"cannot read: {e}"


try:  # python.org's macOS Python has no system CAs ("unable to get local issuer certificate")
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()


def _get(url, headers=None, timeout=20, body=None):
    h = {"User-Agent": "footprint", **(headers or {}), **({"Content-Type": "application/json"} if body else {})}
    r = urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode() if body else None, h),
                               timeout=timeout, context=CTX)
    b = r.read()
    return (gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" else b).decode("utf-8", "replace")


def _clean(t):
    return html.unescape(re.sub(r"<[^>]+>", "", t or "")).strip()


def _site_key():
    try:
        return open(vault.KEY_FILE, encoding="utf-8").read().strip() or None
    except OSError:
        return None


TAVILY = "https://api.tavily.com/search"


def _sources(q):
    """(name, url, headers, body, parse) per source; body = JSON to POST or None; parse(json) -> [(title, url, snippet)]."""
    e = urllib.parse.quote(q)
    tav = lambda d: [(h["title"], h["url"], h.get("content")) for h in d["results"]]
    if os.environ.get("TAVILY_API_KEY"):  # whole web: own key, else footprint's server (holds a key), else keyless
        yield ("web", TAVILY, {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"}, {"query": q, "max_results": 5}, tav)
    elif _site_key():
        yield ("web", f"{vault.API}/api/search?q={e}", {"Authorization": f"Bearer {_site_key()}"}, None,
               lambda d: [(h["title"], h["url"], h.get("description")) for h in d["results"]])
    else:
        yield ("web", TAVILY, {"X-Tavily-Access-Mode": "keyless"}, {"query": q, "max_results": 5}, tav)
    yield ("wikipedia", f"https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch={e}", {}, None,
           lambda d: [(h["title"], "https://en.wikipedia.org/wiki/" + h["title"].replace(" ", "_"), h["snippet"])
                      for h in d["query"]["search"]])
    yield ("stackoverflow", "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&site=stackoverflow"
           f"&pagesize=3&q={e}", {}, None, lambda d: [(h["title"], h["link"], f"{h['score']} votes") for h in d["items"]])
    yield ("github", f"https://api.github.com/search/repositories?per_page=3&q={e}", {}, None,
           lambda d: [(h["full_name"], h["html_url"], h.get("description")) for h in d["items"]])
    yield ("duckduckgo", f"https://api.duckduckgo.com/?format=json&no_html=1&q={e}", {}, None,
           lambda d: [(d["Heading"], d["AbstractURL"], d["AbstractText"])] if d.get("AbstractText") else [])


def search(query):
    lines = []
    for name, url, h, body, parse in _sources(query):
        try:
            lines += [f"- [{name}] {_clean(t)} ({u}): {_clean(s)[:200]}" for t, u, s in parse(json.loads(_get(url, h, body=body)))]
        except (OSError, ValueError, KeyError) as err:
            lines.append(f"- [{name}] failed: {err}")
    return "\n".join(lines) or "no results"


def fetch(url):
    if not url.startswith(("http://", "https://")):
        return "fetch needs a full http(s) URL, e.g. one from search results"
    try:
        return _get("https://r.jina.ai/" + url, timeout=40)
    except OSError as e:
        return f"cannot fetch: {e}"


def ask(argv=(), chat=_chat, out=print, history=None):
    """-> final answer (or None if out of steps). history: earlier turns (the shell passes one list per chat; answers are appended)."""
    yes = "--yes" in argv
    q = " ".join(a for a in argv if a != "--yes").strip()
    if not q:
        sys.exit('usage: footprint ask "<question>" [--yes]')
    msgs = [{"role": "system", "content": SYSTEM.format(cwd=os.getcwd())}, *(history or []), {"role": "user", "content": q}]
    def done_with(answer):
        if history is not None:
            history.extend([{"role": "user", "content": q}, {"role": "assistant", "content": answer}])
        return answer
    tools = {"bash": lambda x: bash(x, yes), "read": read, "search": search, "fetch": fetch}
    done, last = set(), False
    for step in range(STEPS):
        if step == STEPS - 1 and not last:  # out of steps: answer only, from what it has
            msgs.append({"role": "user", "content": FINAL})
            last = True
        raw = chat(msgs, schema(["answer"] if last else TOOLS))
        try:
            a = json.loads(raw)
            tool, arg = a["tool"], a["input"]
        except (ValueError, KeyError, TypeError):
            out(raw)  # not an action: treat as the answer
            return done_with(raw)
        out(f"· {a.get('thought', '')}")
        if tool == "answer":
            out(arg)
            return done_with(arg)
        out(f"  [{tool}] {arg}")
        if (tool, arg) in done:  # small models loop on one action: stop it and make it answer from what it has
            msgs += [{"role": "assistant", "content": raw}, {"role": "user", "content": FINAL}]
            last = True
            continue
        else:
            done.add((tool, arg))
            res = f"Result of {tool}:\n{tools[tool](arg)[:CAP]}"
        msgs += [{"role": "assistant", "content": raw}, {"role": "user", "content": res}]
    return None  # unreachable: the last step only allows answer


if __name__ == "__main__":  # self-check: scripted model -> tool results reach it, answer ends the loop
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    f.write("secret=42")
    f.close()
    script = iter([{"thought": "check", "tool": "bash", "input": "echo hi"},
                   {"thought": "read it", "tool": "read", "input": f.name},
                   {"thought": "done", "tool": "answer", "input": "42"}])
    seen = []
    def fake(msgs, fmt):
        seen.append(msgs[-1]["content"])
        return json.dumps(next(script))
    assert ask(["what is the secret", "--yes"], fake, out=lambda *_: None) == "42"
    assert "exit 0\nhi" in seen[1] and "secret=42" in seen[2], seen
    os.environ.pop("TAVILY_API_KEY", None)
    canned = {"tavily": {"results": [{"title": "VoIP in India", "url": "https://ex.com/v", "content": "rules"}]},
              "wikipedia": {"query": {"search": [{"title": "Public switched telephone network", "snippet": "the <b>PSTN</b>"}]}},
              "stackexchange": {"items": [{"title": "Count &amp; sort", "link": "https://so/q/1", "score": 5}]},
              "github": {"items": []}, "duckduckgo": {"AbstractText": ""}}
    calls = []
    def fake_get(url, h=None, timeout=20, body=None):  # no network
        calls.append((url, h, body))
        return json.dumps(next(v for k, v in canned.items() if k in url))
    globals()["_get"] = fake_get
    globals()["_site_key"] = lambda: None
    r = search("pstn")
    assert "[wikipedia] Public switched telephone network (https://en.wikipedia.org/wiki/Public_switched_telephone_network): the PSTN" in r, r
    assert "[stackoverflow] Count & sort (https://so/q/1): 5 votes" in r, r
    assert r.startswith("- [web] VoIP in India (https://ex.com/v): rules"), r  # logged out: Tavily keyless
    assert calls[0][1] == {"X-Tavily-Access-Mode": "keyless"} and calls[0][2]["query"] == "pstn", calls[0]
    assert "full http" in fetch("pstn")
    globals()["_site_key"] = lambda: "fp_test"  # logged in, no own Brave key -> web results via footprint's server
    canned["/api/search"] = {"results": [{"title": "Exotel", "url": "https://exotel.com", "description": "cloud telephony"}]}
    canned = dict([("/api/search", canned.pop("/api/search"))] + list(canned.items()))  # match the proxy URL first
    r = search("pstn")
    assert r.startswith("- [web] Exotel (https://exotel.com): cloud telephony"), r
    assert ask(["q"], lambda m, f: "plain text", out=lambda *_: None) == "plain text"
    loop, fmts = [], []  # same command twice -> told to answer; last step may only answer
    def looper(msgs, fmt):
        loop.append(msgs[-1]["content"]); fmts.append(fmt["properties"]["tool"]["enum"])
        return json.dumps({"thought": "", "tool": "answer" if fmts[-1] == ["answer"] else "bash", "input": "echo x"})
    assert ask(["q", "--yes"], looper, out=lambda *_: None) == "echo x"
    assert loop[2] == FINAL and fmts == [TOOLS, TOOLS, ["answer"]], (loop, fmts)  # repeat -> answer next step
    h = []  # chat memory: second turn sees the first
    seen2 = []
    ask(["my name is Ana"], lambda m, f: (seen2.append(m), json.dumps({"thought": "", "tool": "answer", "input": "hi Ana"}))[1], out=lambda *_: None, history=h)
    ask(["what is my name"], lambda m, f: (seen2.append(m), json.dumps({"thought": "", "tool": "answer", "input": "Ana"}))[1], out=lambda *_: None, history=h)
    assert [x["content"] for x in seen2[1][1:]] == ["my name is Ana", "hi Ana", "what is my name"], seen2[1]
    assert len(h) == 4
    os.remove(f.name)
    print("agent self-check ok")
