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
    hechos = {r["video"] for r in reg}
    pendientes = [r for r in reg if datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00")) > ahora]
    libres = cfg["max_pendientes"] - len(pendientes)
    ocupados = {r["dueAt"] for r in reg}
    ultimo = max([datetime.fromisoformat(r["dueAt"].replace("Z", "+00:00")) for r in pendientes], default=ahora + timedelta(minutes=5))
    gen = horarios(cfg["horarios"], max(ultimo, ahora + timedelta(minutes=5)), cfg.get("dias_especiales"))
    clave = lambda c: c.get("id", c["video"])
    por_hacer = [c for c in cfg["cola"] if clave(c) not in hechos]
    por_hacer = sorted(por_hacer, key=lambda c: c.get("cuando") != "ya")[:max(libres, 0)]
    if not por_hacer:
        print(f"Nada que programar (pendientes: {len(pendientes)})")
        return
    rel = release()
    for c in por_hacer:
        t = (ahora + timedelta(minutes=6)).astimezone(CDMX) if c.get("cuando") == "ya" else next(gen)
        due = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if due in ocupados:
            t = next(gen); due = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        url = url_publica(rel, c["video"])
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
