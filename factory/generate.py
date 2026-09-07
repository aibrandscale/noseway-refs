#!/usr/bin/env python3
"""Дневна фабрика за BOFU статични реклами през kie.ai (nano-banana-pro).
Само изображения. Никакво видео.

  python3 generate.py --dry-run     показва какво би пуснал, без да харчи
  python3 generate.py               генерира дневната партида
"""
import os, sys, json, time, re, urllib.request, urllib.error, datetime, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
CFG  = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
LIB  = json.load(open(os.path.join(HERE, "prompts.json"), encoding="utf-8"))
STATE_PATH = os.path.join(HERE, "state.json")
CREATE = "https://api.kie.ai/api/v1/jobs/createTask"
POLL   = "https://api.kie.ai/api/v1/jobs/recordInfo?taskId="   # НЕ getTask — той е 404
MODELS = {
    "seedream/5-pro-image-to-image": {"images": "image_urls", "max_prompt": 5000,
        "resolution": False, "quality": True,
        "ratios": {"1:1","4:3","3:4","16:9","9:16","2:3","3:2","21:9"}},
    "seedream/5-lite-image-to-image": {"images": "image_urls", "max_prompt": 5000,
        "resolution": False, "quality": True,
        "ratios": {"1:1","4:3","3:4","16:9","9:16","2:3","3:2","21:9"}},
    "google/nano-banana-edit": {"images": "image_urls",  "max_prompt": 5000, "resolution": False},
    "google/nano-banana":      {"images": "image_urls",  "max_prompt": 5000, "resolution": False},
    # Семейството Nano Banana иска image_input (НЕ image_urls) и resolution 1K/2K/4K.
    # Приема и 4:5 — съотношението, което Seedream отказва.
    "nano-banana-pro":         {"images": "image_input", "max_prompt": 5000, "resolution": True,
        "ratios": {"1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9","1:4","4:1","1:8","8:1","Auto"}},
    "nano-banana-2":           {"images": "image_input", "max_prompt": 5000, "resolution": True,
        "ratios": {"1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9","1:4","4:1","1:8","8:1","Auto"}},
    "nano-banana-2-lite":      {"images": "image_input", "max_prompt": 5000, "resolution": True,
        "ratios": {"1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9","1:4","4:1","1:8","8:1","Auto"}},
}
UA     = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def log(m):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {m}"
    print(line, flush=True)
    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
    with open(os.path.join(HERE, "logs", f"{datetime.date.today():%Y-%m}.log"), "a") as f:
        f.write(line + "\n")

def api_key():
    k = os.environ.get("KIE_API_KEY")
    if not k:
        p = os.path.join(HERE, ".kie_key")
        if os.path.exists(p): k = open(p).read().strip()
    if not k:
        sys.exit("Липсва kie.ai ключ. Сложи го в ~/Desktop/noseway-ad-factory/.kie_key "
                 "(chmod 600) или в променливата KIE_API_KEY.")
    return k

def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH, encoding="utf-8"))
    return {"cursor": {k: 0 for k in LIB}, "month": "", "used_this_month": 0}

def save_state(st): json.dump(st, open(STATE_PATH, "w"), ensure_ascii=False, indent=1)

def slug(s, n=40):
    s = re.sub(r'[^\w\s-]', '', s, flags=re.U).strip()
    return re.sub(r'\s+', '-', s)[:n] or "ad"

def post(url, body, key):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())

def get(url, key):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())

def pick(product, count, st):
    items = LIB[product]["prompts"]
    cur = st["cursor"].get(product, 0)
    out = [items[(cur + i) % len(items)] for i in range(count)]
    st["cursor"][product] = (cur + count) % len(items)
    return out

def squeeze(text):
    """Маха само празнина — нито една дума."""
    t = re.sub(r'[ \t]+\n', '\n', text)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t

CYR = re.compile(r'[\u0400-\u04FF]')

def exact_text_block(creative):
    """Вади всеки цитиран български низ и го подава ВТОРИ път като изричен
    списък. Моделът бърка буквите точно когато текстът е разпръснат из описанието."""
    seen, items = set(), []
    for q in re.findall(r'"([^"]+)"', creative):
        for line in q.split("\n"):
            line = line.strip()
            if not line or not CYR.search(line) or line in seen: continue
            seen.add(line); items.append(line)
    if not items: return ""
    body = "\n".join(f'{i}. "{t}"' for i, t in enumerate(items, 1))
    return ("\n\nEXACT TEXT TO RENDER — these are the ONLY words allowed in the image.\n"
            "Copy each line character by character. Do not translate, shorten, correct\n"
            "or add to any of them. Count the letters if you must.\n" + body + "\n")

def build_prompt(base, creative, limit):
    """Креативът и списъкът с текстове са неприкосновени. Свива се САМО базата."""
    creative = squeeze(creative).strip()
    texts = exact_text_block(creative)
    sep = "\n---\n"
    room = limit - len(creative) - len(texts) - len(sep)
    if room < 400:
        return (creative + texts)[:limit]
    b = squeeze(base).strip()
    if len(b) <= room:
        return b + sep + creative + texts
    b = re.sub(r'\n\n', '\n', b)
    if len(b) <= room:
        return b + sep + creative + texts
    # реже се от базата, но по цели редове, за да не се къса ограничение по средата
    lines = b.split("\n"); out = []
    for ln in lines:
        if sum(len(x) + 1 for x in out) + len(ln) + 1 > room: break
        out.append(ln)
    return "\n".join(out) + sep + creative + texts

def generate(product, item, refs, key, outdir, dry):
    prof = MODELS.get(CFG["model"], {"images": "image_urls", "max_prompt": 5000, "resolution": False})
    raw_len = len(LIB[product]["base"]) + len(item["prompt"]) + 5
    prompt = build_prompt(LIB[product]["base"], item["prompt"], prof["max_prompt"])
    if raw_len > prof["max_prompt"]:
        log(f"  (базовият блок свит: {raw_len} → {len(prompt)} знака; креативът е непокътнат)")
    ratio = CFG["aspect_ratio"]
    allowed = prof.get("ratios")
    if allowed and ratio not in allowed:
        fallback = "3:4" if "3:4" in allowed else sorted(allowed)[0]
        log(f"  (моделът не поддържа {ratio}; минавам на {fallback})")
        ratio = fallback
    inp = {"prompt": prompt, prof["images"]: refs,
           "aspect_ratio": ratio, "output_format": CFG["output_format"]}
    if prof.get("resolution"): inp["resolution"] = CFG["resolution"]
    if prof.get("quality"):    inp["quality"]    = CFG.get("quality", "high")
    body = {"model": CFG["model"], "input": inp}
    name = f"{product}_{item['n']:02d}_{slug(item['title'])}"
    if dry:
        log(f"  DRY  {name}  ({len(prompt)} знака промпт, {len(refs)} реф.)")
        return True
    try:
        r = post(CREATE, body, key)
    except urllib.error.HTTPError as e:
        log(f"  ГРЕШКА createTask {name}: HTTP {e.code} {e.read().decode()[:200]}"); return False
    tid = (r.get("data") or {}).get("taskId")
    if not tid:
        log(f"  ГРЕШКА createTask {name}: {json.dumps(r)[:250]}"); return False
    for _ in range(60):                      # до ~5 мин
        time.sleep(5)
        try: pr = get(POLL + tid, key)
        except Exception as e: log(f"  poll retry ({e})"); continue
        d = pr.get("data") or {}
        state = d.get("state")
        if state == "success":
            urls = json.loads(d.get("resultJson") or "{}").get("resultUrls") or []
            if not urls: log(f"  ГРЕШКА {name}: няма resultUrls"); return False
            dest = os.path.join(outdir, name + "." + CFG["output_format"])
            rq = urllib.request.Request(urls[0], headers={"User-Agent": UA})
            open(dest, "wb").write(urllib.request.urlopen(rq, timeout=180).read())
            size = CFG.get("final_size")
            if size:
                try:
                    from PIL import Image
                    im = Image.open(dest)
                    if im.size != (size, size):
                        im.convert("RGB").resize((size, size), Image.LANCZOS).save(dest, quality=95)
                except Exception as e:
                    log(f"  (не успях да смаля: {e})")
            log(f"  ✓ {name}  ({os.path.getsize(dest)/1e6:.1f} MB)")
            return True
        if state in ("fail", "failed", "error"):
            log(f"  ✗ {name}: {d.get('failMsg') or json.dumps(d)[:200]}"); return False
    log(f"  ✗ {name}: таймаут"); return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--product", help="само този продукт: mouth/nose/kids")
    ap.add_argument("--prompt", type=int, help="само този номер промпт")
    a = ap.parse_args()

    st = load_state()
    month = f"{datetime.date.today():%Y-%m}"
    if st.get("month") != month:
        st["month"], st["used_this_month"] = month, 0

    total = a.count or CFG["per_day"]
    remaining = CFG["monthly_cap"] - st["used_this_month"]
    if not a.dry_run and remaining <= 0:
        log(f"СТОП: месечният таван {CFG['monthly_cap']} е достигнат. Нищо не се генерира.")
        return
    if not a.dry_run and total > remaining:
        log(f"Оставащи до тавана: {remaining}. Свивам партидата от {total} на {remaining}.")
        total = remaining

    key = None if a.dry_run else api_key()
    outdir = os.path.join(HERE, "out", f"{datetime.date.today():%Y-%m-%d}")
    os.makedirs(outdir, exist_ok=True)

    if a.product and a.prompt:
        v = CFG["products"][a.product]
        item = next(i for i in LIB[a.product]["prompts"] if i["n"] == a.prompt)
        log(f"=== единична генерация: {a.product} №{a.prompt} — {item['title']}")
        ok = generate(a.product, item, v["refs"], key, outdir, a.dry_run)
        if ok and not a.dry_run:
            st["used_this_month"] += 1; save_state(st)
        log(f"=== {'готово' if ok else 'провал'} → {outdir}")
        return

    active = {k: v for k, v in CFG["products"].items() if v.get("enabled") and k in LIB}
    if not active: sys.exit("Няма активни продукти в config.json")
    shares = sum(v["share"] for v in active.values())
    plan = []
    for k, v in active.items():
        bad = [r for r in v["refs"] if "ЗАМЕНИ" in r]
        if bad and not a.dry_run:
            log(f"ПРОПУСКАМ {k}: референциите не са попълнени в config.json"); continue
        n = max(1, round(total * v["share"] / shares))
        plan += [(k, it, v["refs"]) for it in pick(k, n, st)]
    plan = plan[:total]

    log(f"=== партида {datetime.date.today():%Y-%m-%d} · {len(plan)} реклами"
        f"{' (DRY RUN)' if a.dry_run else ''} · използвани този месец: {st['used_this_month']}/{CFG['monthly_cap']}")
    ok = 0
    for k, it, refs in plan:
        if generate(k, it, refs, key, outdir, a.dry_run): ok += 1
    if not a.dry_run:
        st["used_this_month"] += ok
        save_state(st)
        json.dump([{"product": k, "n": it["n"], "title": it["title"]} for k, it, _ in plan],
                  open(os.path.join(outdir, "manifest.json"), "w"), ensure_ascii=False, indent=1)
    log(f"=== готови {ok}/{len(plan)} → {outdir}")

if __name__ == "__main__":
    main()
