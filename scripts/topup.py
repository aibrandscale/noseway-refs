#!/usr/bin/env python3
"""Онлайн допълване на BOFU креативи до 10 (GitHub Actions).
Върви на инфраструктурата на GitHub, която стига kie.ai (облачната пясъчница на
Anthropic не стига — egress политика). Ключът идва от GitHub Secret KIE_API_KEY.

Логика:
  1. Брои живите креативи в sheet.json (kind == "creative"). Цел = TARGET (10).
  2. N = TARGET - живи. Ако N <= 0 → нищо, изход 0.
  3. Избира N промпт-номера от factory/prompts.json (nose), които не са живи и
     не са в retired.json.
  4. За всеки: factory/generate.py --product nose --prompt <n> (стига kie.ai).
  5. Слага чистото изображение като ASCII .jpg в creatives-<дата>/ и добавя ред
     kind:"creative" (copy и framework остават празни — попълва ги почасовата
     облачна задача, която има модел; новите са For Review сами в таблицата).

Копитата НЕ се пишат тук нарочно — GitHub runner няма модел. Оставяме copy="" и
framework="", а облачната рутина ги допълва по рамка при следващото си минаване.
"""
import os, sys, json, re, subprocess, datetime, glob

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTORY = os.path.join(ROOT, "factory")
SHEET   = os.path.join(ROOT, "sheet.json")
RETIRED = os.path.join(ROOT, "retired.json")
PROMPTS = os.path.join(FACTORY, "prompts.json")
TARGET  = int(os.environ.get("TARGET", "10"))
RAW     = "https://raw.githubusercontent.com/aibrandscale/noseway-refs/main"

# Кирилица → латиница за ASCII имена на файлове (URL-ите не търпят кирилица).
TR = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ж':'zh','з':'z','и':'i',
    'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s',
    'т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sht',
    'ъ':'a','ь':'y','ю':'yu','я':'ya',
}
def translit(s):
    out = []
    for ch in s.lower():
        out.append(TR.get(ch, ch))
    s = "".join(out)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or "ad"

def first_num(name):
    m = re.match(r'\s*(\d+)', name or "")
    return int(m.group(1)) if m else None

def main():
    sheet = json.load(open(SHEET, encoding="utf-8"))
    rows  = sheet["rows"]
    retired = json.load(open(RETIRED, encoding="utf-8")).get("rows", [])
    lib   = json.load(open(PROMPTS, encoding="utf-8"))
    prompts = lib["nose"]["prompts"]

    live = [r for r in rows if r.get("kind") == "creative"]
    N = TARGET - len(live)
    print(f"живи креативи: {len(live)}  цел: {TARGET}  за генериране: {N}")
    if N <= 0:
        print("нищо за допълване")
        return 0

    used = set()
    for r in live:
        n = first_num(r.get("name"))
        if n is not None: used.add(n)
    for name in retired:
        n = first_num(name)
        if n is not None: used.add(n)

    pool = [p for p in prompts if p["n"] not in used]
    if not pool:
        print("НЯМА свободни промпти — всички са живи или в retired.json")
        return 0
    chosen = pool[:N]
    print("избрани промпти:", [p["n"] for p in chosen])

    today = f"{datetime.date.today():%Y-%m-%d}"
    creatives_dir = os.path.join(ROOT, f"creatives-{today}")
    os.makedirs(creatives_dir, exist_ok=True)

    added = 0
    for p in chosen:
        n = p["n"]; title = p["title"]
        print(f"--- генерирам nose #{n}: {title}")
        rc = subprocess.run(
            [sys.executable, "generate.py", "--product", "nose", "--prompt", str(n)],
            cwd=FACTORY, env=os.environ.copy())
        if rc.returncode != 0:
            print(f"  generate.py излезе с код {rc.returncode} — пропускам #{n}")
            continue
        matches = glob.glob(os.path.join(FACTORY, "out", today, f"nose_{n:02d}_*.png"))
        if not matches:
            print(f"  няма изходен файл за #{n} — пропускам (вероятно грешка/кредити)")
            continue
        src = matches[0]
        slug = translit(title)
        dest = os.path.join(creatives_dir, f"{n}-{slug}.jpg")
        try:
            from PIL import Image
            Image.open(src).convert("RGB").save(dest, "JPEG", quality=92)
        except Exception as e:
            print(f"  PIL не успя ({e}) — копирам суровия файл като .jpg")
            import shutil; shutil.copyfile(src, dest)
        link = f"{RAW}/creatives-{today}/{n}-{slug}.jpg"
        rows.append({
            "key": f"cr-{n}", "name": f"{n} {title}", "link": link,
            "status": "On hold", "cpa": None, "roas": None, "cpc": None,
            "spend": None, "impressions": None, "results": None,
            "kind": "creative", "framework": "", "copy": "", "reworked": False,
        })
        added += 1
        print(f"  ✓ добавен {link}")

    if added:
        sheet["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        json.dump(sheet, open(SHEET, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"=== добавени {added}/{N}")
    # изходен код 0 винаги — липса на кредити не е фатал за workflow-а
    return 0

if __name__ == "__main__":
    sys.exit(main())
