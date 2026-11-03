"""Programa los videos de canales/tiktok/cola.json en TikTok (@y.eso.por_que) usando la API gratuita de Buffer.

- Mantiene como máximo `max_pendientes` publicaciones programadas (límite del plan gratis: 10).
- Asigna a cada video el siguiente horario libre (hora CDMX): lun-vie 13/18/21, sáb-dom 11/14/18/21.
- Los videos se sirven públicamente como archivos de un Release de GitHub (Buffer necesita una URL).
- Guarda lo programado en canales/tiktok/programadas.json para no repetir.
Requiere los secretos BUFFER_API_KEY y GITHUB_TOKEN.
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

AQUI = Path(__file__).parent
CDMX = ZoneInfo("America/Mexico_City")
API = "https://api.buffer.com"
TAG = "tiktok-videos"
e = os.environ
KEY, GH, REPO = e.get("BUFFER_API_KEY"), e.get("GITHUB_TOKEN"), e.get("GITHUB_REPOSITORY", "Davidbalont/Cefiro")
SOLO_VER = e.get("SOLO_VER") == "1"


def http(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            cuerpo = r.read()
            return json.loads(cuerpo) if cuerpo else {}
    except urllib.error.HTTPError as err:
        raise SystemExit(f"{method or 'GET'} {url} -> {err.code}: {err.read()[:500].decode(errors='replace')}")


def gql(query, variables=None):
    r = http(API, json.dumps({"query": query, "variables": variables or {}}).encode(),
             {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"}, "POST")
    if r.get("errors"):
        raise SystemExit(f"Buffer respondió con error: {r['errors']}")
    return r["data"]


def gh(path, **kw):
    h = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}
    h.update(kw.pop("headers", {}))
    return http(f"https://api.github.com/repos/{REPO}{path}", headers=h, **kw)


def release():
    try:
        return gh(f"/releases/tags/{TAG}")
    except SystemExit:
        return gh("/releases", method="POST", data=json.dumps({"tag_name": TAG, "name": "Videos para TikTok",
                  "body": "Archivos que Buffer descarga para programar en TikTok.", "prerelease": True}).encode(),
                  headers={"Content-Type": "application/json"})


def url_publica(rel, nombre):
    for a in gh(f"/releases/{rel['id']}/assets?per_page=100"):
        if a["name"] == nombre:
            return a["browser_download_url"]
    datos = (AQUI / "videos" / nombre).read_bytes()
    subida = rel["upload_url"].split("{")[0] + f"?name={nombre}"
    a = http(subida, datos, {"Authorization": f"Bearer {GH}", "Content-Type": "video/mp4"}, "POST")
    return a["browser_download_url"]


def horarios(cfg, desde, especiales=None):
    dia = desde.astimezone(CDMX).date()
    while True:
        lista = (especiales or {}).get(dia.isoformat()) or (cfg["fin_de_semana"] if dia.weekday() >= 5 else cfg["entre_semana"])
        for h in lista:
            hh, mm = map(int, h.split(":"))
            t = datetime(dia.year, dia.month, dia.day, hh, mm, tzinfo=CDMX)
            if t > desde:
                yield t
        dia += timedelta(days=1)


def main():
    if not KEY:
        raise SystemExit("Falta el secreto BUFFER_API_KEY")
    cfg = json.loads((AQUI / "cola.json").read_text())
    reg_path = AQUI / "programadas.json"
    reg = json.loads(reg_path.read_text()) if reg_path.exists() else []

    org = gql("query { account { organizations { id name } } }")["account"]["organizations"][0]["id"]
    canales = gql("query($o: OrganizationId!) { channels(input: {organizationId: $o}) { id name service } }", {"o": org})["channels"]
    print("Canales en Buffer:", [(c["service"], c["name"]) for c in canales])
    tk = [c for c in canales if c["service"].lower() == "tiktok"]
    if not tk:
        raise SystemExit("No hay canal de TikTok conectado en Buffer")
    canal = tk[0]["id"]
    if SOLO_VER:
        return
    if e.get("ESTADO") == "1":
        tipos = gql('{ __type(name: "Post") { fields { name type { kind name ofType { kind name } } } } }')["__type"]["fields"]
        print("Campos de Post:", [f["name"] for f in tipos])
        quiero = [f["name"] for f in tipos if f["name"] in ("id", "status", "dueAt", "sentAt", "externalLink", "error", "isCustomScheduled")]
        sub = {"error": "error { message }"}
        campos = " ".join(sub.get(n, n) for n in quiero)
        ahora = datetime.now(timezone.utc)
        for r in reg:
            due = datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00"))
            if due > ahora - timedelta(hours=8):
                try:
                    d = gql(f'query($i: PostInput!) {{ post(input: $i) {{ {campos} }} }}', {"i": {"id": r["buffer_id"]}})
                except SystemExit as err:
                    d = str(err)
                print(r["video"], r["cdmx"], "→", d)
        return

    ahora = datetime.now(timezone.utc)
    # Reprogramar: si cola.json trae un token nuevo, borra en Buffer lo pendiente y lo vuelve a acomodar.
    token = cfg.get("reprogramar")
    tok_path = AQUI / "reprogramado.txt"
    if token and (not tok_path.exists() or tok_path.read_text().strip() != token):
        quedan = []
        for r in reg:
            if datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00")) > ahora:
                d = gql("mutation($i: DeletePostInput!) { deletePost(input: $i) { __typename } }", {"i": {"id": r["buffer_id"]}})
                print(f"↺ quitado {r['video']} ({r['cdmx']}): {d}")
            else:
                quedan.append(r)
        reg = quedan
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2))
        tok_path.write_text(token)
    reemp = cfg.get("reemplazos", {})
    textos = {c.get("id", c["video"]): c["texto"] for c in cfg["cola"]}
    archivos = {c.get("id", c["video"]): c["video"] for c in cfg["cola"]}
    rel_r = None

    def recrear(r, archivo, due):
        nonlocal rel_r
        rel_r = rel_r or release()
        url = url_publica(rel_r, archivo)
        gql("mutation($i: DeletePostInput!) { deletePost(input: $i) { __typename } }", {"i": {"id": r["buffer_id"]}})
        res = gql("""mutation($i: CreatePostInput!) { createPost(input: $i) {
                 ... on PostActionSuccess { post { id dueAt } } ... on MutationError { message } } }""",
                {"i": {"text": textos.get(r["video"], ""), "channelId": canal, "schedulingType": "automatic", "mode": "customScheduled",
                       "dueAt": due, "assets": [{"video": {"url": url, "metadata": {"thumbnailOffset": 1000}}}]}})["createPost"]
        if "post" not in res:
            print(f"✗ {r['video']}: {res.get('message')}")
            return False
        r["buffer_id"], r["archivo"], r["dueAt"] = res["post"]["id"], archivo, due
        r["cdmx"] = datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(CDMX).strftime("%a %d %b %H:%M")
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2))
        return True

    # Adelantar: publica ya (escalonado cada 5 min) los videos pendientes de esta lista.
    adel = cfg.get("adelantar", {})
    tok_a = AQUI / "adelantado.txt"
    if adel.get("token") and (not tok_a.exists() or tok_a.read_text().strip() != adel["token"]):
        k = 0
        for r in reg:
            due0 = datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00"))
            if r["video"] in adel.get("videos", []) and due0 > ahora + timedelta(minutes=8):
                due = (ahora + timedelta(minutes=6 + 5 * k)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                if recrear(r, r.get("archivo") or reemp.get(r["video"], archivos.get(r["video"], r["video"])), due):
                    print(f"⏩ {r['video']} → {r['cdmx']}")
                    k += 1
        tok_a.write_text(adel["token"])

    # Reemplazos: versión corregida de un video ya programado, en el mismo horario.
    for r in reg:
        nuevo = reemp.get(r["video"])
        due0 = datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00"))
        if not nuevo or r.get("archivo") == nuevo or due0 < ahora + timedelta(minutes=5):
            continue
        if not (AQUI / "videos" / nuevo).exists():
            print(f"… {nuevo} aún no está en videos/")
            continue
        if recrear(r, nuevo, r["dueAt"]):
            print(f"⇄ {r['video']} → {nuevo} ({r['cdmx']})")

    # Quitar: borra de Buffer posts pendientes de esta lista y los regresa a la cola (libera lugar).
    quitar = cfg.get("quitar", {})
    tok_q = AQUI / "quitado.txt"
    if quitar.get("token") and (not tok_q.exists() or tok_q.read_text().strip() != quitar["token"]):
        quedan = []
        for r in reg:
            due0 = datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00"))
            if r["video"] in quitar.get("videos", []) and due0 > ahora + timedelta(minutes=5):
                gql("mutation($i: DeletePostInput!) { deletePost(input: $i) { __typename } }", {"i": {"id": r["buffer_id"]}})
                print(f"⌫ {r['video']} ({r['cdmx']}) vuelve a la cola")
            else:
                quedan.append(r)
        reg[:] = quedan
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2))
        tok_q.write_text(quitar["token"])

    hechos = {r["video"] for r in reg}
    pendientes = [r for r in reg if datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00")) > ahora]
    libres = cfg["max_pendientes"] - len(pendientes)
    ocupados = {r["dueAt"] for r in reg}
    inicio = ahora + timedelta(minutes=5)
    if cfg.get("desde"):
        inicio = max(inicio, datetime.fromisoformat(cfg["desde"]).replace(tzinfo=CDMX))
    gen = horarios(cfg["horarios"], inicio, cfg.get("dias_especiales"))
    clave = lambda c: c.get("id", c["video"])
    por_hacer = [c for c in cfg["cola"] if clave(c) not in hechos]
    por_hacer = sorted(por_hacer, key=lambda c: c.get("cuando") != "ya")[:max(libres, 0)]
    if not por_hacer:
        print(f"Nada que programar (pendientes: {len(pendientes)})")
        return
    rel = release()
    for c in por_hacer:
        if c.get("cuando") == "ya":
            t = (ahora + timedelta(minutes=6)).astimezone(CDMX)
            due = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        else:
            while True:
                t = next(gen)
                due = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                if due not in ocupados:
                    break
        ocupados.add(due)
        url = url_publica(rel, reemp.get(clave(c), c["video"]))
        r = gql("""mutation($i: CreatePostInput!) { createPost(input: $i) {
                 ... on PostActionSuccess { post { id dueAt } } ... on MutationError { message } } }""",
                {"i": {"text": c["texto"], "channelId": canal, "schedulingType": "automatic", "mode": "customScheduled",
                       "dueAt": due, "assets": [{"video": {"url": url, "metadata": {"thumbnailOffset": 1000}}}]}})["createPost"]
        if "post" not in r:
            print(f"✗ {c['video']}: {r.get('message')}")
            break
        reg.append({"video": clave(c), "dueAt": due, "cdmx": t.strftime("%a %d %b %H:%M"), "buffer_id": r["post"]["id"]})
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2))
        print(f"✓ {c['video']} → {t.strftime('%a %d %b %H:%M')} CDMX")


if __name__ == "__main__":
    main()
