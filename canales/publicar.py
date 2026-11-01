"""Publica los videos de los canales de nicho en YouTube, TikTok, Facebook e Instagram.

Cada 15 minutos GitHub corre este programa. Revisa calendario.json y publica las
entradas aprobadas ("aprobado": true) cuya fecha y hora (centro de México) ya llegaron
y que todavía no aparecen en publicadas.json. Lo publicado se anota por red, así que
si una red falla, en la siguiente corrida solo se reintenta esa red.

Si una red todavía no tiene sus permisos configurados, se salta sin marcar error:
así se puede empezar con Facebook e Instagram y sumar YouTube y TikTok después.

Permisos (secretos de GitHub, ver README.md):
  META_CANALES_TOKEN                      token del usuario del sistema de Meta (todas las páginas)
  YT_CLIENT_ID, YT_CLIENT_SECRET          app de Google
  YT_REFRESH_<CANAL>                      uno por canal de YouTube (YESOPORQUE, BUTWHY, ...)
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET app de TikTok
  TIKTOK_REFRESH_<CANAL>                  uno por cuenta de TikTok
"""
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
CALENDARIO = os.path.join(AQUI, "calendario.json")
CANALES = os.path.join(AQUI, "canales.json")
PUBLICADAS = os.path.join(AQUI, "publicadas.json")
CDMX = timezone(timedelta(hours=-6))  # México centro ya no cambia de horario
REDES = ("youtube", "tiktok", "facebook", "instagram")
GRAPH = "https://graph.facebook.com/v21.0"
# Si una publicación aprobada se quedó atrás más de este tiempo, ya no se publica sola.
MAX_RETRASO = timedelta(days=2)


class SinPermiso(Exception):
    """La red no tiene sus secretos configurados para este canal."""


def secretos():
    datos = {}
    try:
        datos = json.loads(os.environ.get("SECRETOS") or "{}")
    except json.JSONDecodeError:
        pass
    for k, v in os.environ.items():
        datos.setdefault(k, v)
    return datos


SEC = secretos()


def sec(nombre):
    valor = (SEC.get(nombre) or "").strip()
    if not valor:
        raise SinPermiso(nombre)
    return valor


def http(metodo, url, datos=None, json_body=None, headers=None, crudo=None, timeout=600):
    headers = dict(headers or {})
    cuerpo = None
    if json_body is not None:
        cuerpo = json.dumps(json_body).encode()
        headers.setdefault("Content-Type", "application/json; charset=UTF-8")
    elif datos is not None:
        cuerpo = urllib.parse.urlencode(datos).encode()
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif crudo is not None:
        cuerpo = crudo
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            texto = r.read().decode() or "{}"
            try:
                return json.loads(texto), r.headers
            except json.JSONDecodeError:
                return {"texto": texto}, r.headers
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:800]
        raise RuntimeError(f"{metodo} {url.split('?')[0]} -> {e.code} {detalle}")


def normal(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in t if ch.isalnum())


# ---------------------------------------------------------------- YouTube

def youtube_token(canal):
    datos = {
        "client_id": sec("YT_CLIENT_ID"),
        "client_secret": sec("YT_CLIENT_SECRET"),
        "refresh_token": sec(f"YT_REFRESH_{canal.upper()}"),
        "grant_type": "refresh_token",
    }
    r, _ = http("POST", "https://oauth2.googleapis.com/token", datos=datos)
    return r["access_token"]


def youtube_revisar(canal, info):
    token = youtube_token(canal)
    r, _ = http("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                headers={"Authorization": f"Bearer {token}"})
    nombre = ((r.get("items") or [{}])[0].get("snippet") or {}).get("title", "?")
    aviso = "" if normal(nombre) == normal(info["nombre"]) else "  <- NO coincide con el canal esperado"
    return f"canal de YouTube «{nombre}»{aviso}"


def youtube_publicar(canal, info, p, ruta):
    token = youtube_token(canal)
    titulo = p["titulo"][:92] + " #shorts"
    meta = {
        "snippet": {
            "title": titulo,
            "description": p["texto"],
            "categoryId": "27",  # Educación
            "defaultLanguage": info["idioma"],
            "defaultAudioLanguage": info["idioma"],
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(p.get("contenido_sintetico", False)),
        },
    }
    tam = os.path.getsize(ruta)
    _, h = http("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                json_body=meta, headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Type": "video/mp4",
                                         "X-Upload-Content-Length": str(tam)})
    destino = h["Location"]
    with open(ruta, "rb") as f:
        r, _ = http("PUT", destino, crudo=f.read(), headers={"Authorization": f"Bearer {token}",
                                                            "Content-Type": "video/mp4"})
    return r["id"]


# ---------------------------------------------------------------- TikTok

TT = "https://open.tiktokapis.com/v2"


def tiktok_token(canal):
    datos = {
        "client_key": sec("TIKTOK_CLIENT_KEY"),
        "client_secret": sec("TIKTOK_CLIENT_SECRET"),
        "refresh_token": sec(f"TIKTOK_REFRESH_{canal.upper()}"),
        "grant_type": "refresh_token",
    }
    r, _ = http("POST", f"{TT}/oauth/token/", datos=datos)
    if "access_token" not in r:
        raise RuntimeError(f"TikTok no renovó el permiso: {r}")
    if r.get("refresh_token") and r["refresh_token"] != datos["refresh_token"]:
        print(f"  Aviso: TikTok entregó un permiso nuevo para {canal}; el anterior sigue sirviendo hasta que caduque.")
    return r["access_token"]


def tiktok_creador(token):
    r, _ = http("POST", f"{TT}/post/publish/creator_info/query/", json_body={},
                headers={"Authorization": f"Bearer {token}"})
    return r.get("data") or {}


def tiktok_revisar(canal, info):
    datos = tiktok_creador(tiktok_token(canal))
    usuario = datos.get("creator_username", "?")
    aviso = "" if usuario.lower() == info["usuario"].lower() else "  <- NO coincide con la cuenta esperada"
    opciones = ", ".join(datos.get("privacy_level_options") or [])
    return f"cuenta de TikTok @{usuario}{aviso} (privacidad permitida: {opciones})"


def tiktok_publicar(canal, info, p, ruta):
    token = tiktok_token(canal)
    auth = {"Authorization": f"Bearer {token}"}
    creador = tiktok_creador(token)
    opciones = creador.get("privacy_level_options") or ["SELF_ONLY"]
    # Mientras TikTok no apruebe la app, solo deja publicar en privado (SELF_ONLY).
    privacidad = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in opciones else opciones[0]
    tam = os.path.getsize(ruta)
    cuerpo = {
        "post_info": {
            "title": p["texto"][:2200],
            "privacy_level": privacidad,
            "disable_comment": False,
            "disable_duet": False,
            "disable_stitch": False,
            "is_aigc": True,
        },
        "source_info": {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": tam, "total_chunk_count": 1},
    }
    r, _ = http("POST", f"{TT}/post/publish/video/init/", json_body=cuerpo, headers=auth)
    publish_id = r["data"]["publish_id"]
    with open(ruta, "rb") as f:
        http("PUT", r["data"]["upload_url"], crudo=f.read(),
             headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{tam - 1}/{tam}"})
    for _ in range(60):
        s, _ = http("POST", f"{TT}/post/publish/status/fetch/", json_body={"publish_id": publish_id}, headers=auth)
        estado = (s.get("data") or {}).get("status")
        if estado == "PUBLISH_COMPLETE":
            break
        if estado == "FAILED":
            raise RuntimeError(f"TikTok rechazó el video: {s}")
        time.sleep(10)
    if privacidad != "PUBLIC_TO_EVERYONE":
        print(f"  Aviso: TikTok lo publicó como {privacidad} porque la app aún no está aprobada.")
    return publish_id


# ---------------------------------------------------------------- Meta (Facebook e Instagram)

_paginas = {}


def meta_paginas():
    if not _paginas:
        token = sec("META_CANALES_TOKEN")
        url = f"{GRAPH}/me/accounts?fields=id,name,access_token,instagram_business_account{{id,username}}&limit=100&access_token={token}"
        while url:
            r, _ = http("GET", url)
            for pg in r.get("data") or []:
                _paginas[normal(pg["name"])] = pg
            url = (r.get("paging") or {}).get("next")
    return _paginas


def meta_pagina(info):
    pg = meta_paginas().get(normal(info["nombre"]))
    if not pg:
        raise SinPermiso(f"página de Facebook «{info['nombre']}» (no está asignada al usuario del sistema)")
    return pg


def facebook_revisar(canal, info):
    pg = meta_pagina(info)
    return f"página de Facebook «{pg['name']}»"


def instagram_revisar(canal, info):
    pg = meta_pagina(info)
    ig = pg.get("instagram_business_account")
    if not ig:
        raise SinPermiso(f"Instagram ligado a la página «{pg['name']}»")
    aviso = "" if ig.get("username", "").lower() == info["usuario"].lower() else "  <- NO coincide con la cuenta esperada"
    return f"Instagram @{ig.get('username')}{aviso}"


def facebook_publicar(canal, info, p, ruta):
    pg = meta_pagina(info)
    token = pg["access_token"]
    r, _ = http("POST", f"{GRAPH}/{pg['id']}/video_reels", datos={"upload_phase": "start", "access_token": token})
    video_id = r["video_id"]
    tam = os.path.getsize(ruta)
    with open(ruta, "rb") as f:
        http("POST", f"https://rupload.facebook.com/video-upload/v21.0/{video_id}", crudo=f.read(),
             headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(tam)})
    http("POST", f"{GRAPH}/{pg['id']}/video_reels", datos={
        "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
        "description": p["texto"], "access_token": token})
    return video_id


def instagram_publicar(canal, info, p, ruta):
    pg = meta_pagina(info)
    ig = pg.get("instagram_business_account")
    if not ig:
        raise SinPermiso(f"Instagram ligado a la página «{pg['name']}»")
    token = pg["access_token"]
    r, _ = http("POST", f"{GRAPH}/{ig['id']}/media", datos={
        "media_type": "REELS", "upload_type": "resumable", "caption": p["texto"],
        "share_to_feed": "true", "access_token": token})
    contenedor = r["id"]
    tam = os.path.getsize(ruta)
    with open(ruta, "rb") as f:
        http("POST", r.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{contenedor}", crudo=f.read(),
             headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(tam)})
    for _ in range(60):
        s, _ = http("GET", f"{GRAPH}/{contenedor}?fields=status_code,status&access_token={token}")
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram no pudo procesar el video: {s.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram tardó demasiado en procesar el video")
    r, _ = http("POST", f"{GRAPH}/{ig['id']}/media_publish", datos={"creation_id": contenedor, "access_token": token})
    return r["id"]


PUBLICAR = {"youtube": youtube_publicar, "tiktok": tiktok_publicar,
            "facebook": facebook_publicar, "instagram": instagram_publicar}
REVISAR = {"youtube": youtube_revisar, "tiktok": tiktok_revisar,
           "facebook": facebook_revisar, "instagram": instagram_revisar}


# ---------------------------------------------------------------- programa

def hora_de(p):
    return datetime.fromisoformat(f"{p['fecha']}T{p.get('hora', '18:00')}").replace(tzinfo=CDMX)


def revisar_conexiones(canales):
    print("Revisión de permisos (no se publica nada):")
    for clave, info in canales.items():
        print(f"\n{info['nombre']}")
        for red in REDES:
            try:
                print(f"  {red:10s} OK  {REVISAR[red](clave, info)}")
            except SinPermiso as e:
                print(f"  {red:10s} --  falta configurar: {e}")
            except Exception as e:  # noqa: BLE001
                print(f"  {red:10s} ERROR  {e}")


def main():
    prueba = os.environ.get("PRUEBA", "").lower() == "true"
    canales = json.load(open(CANALES, encoding="utf-8"))["canales"]
    calendario = json.load(open(CALENDARIO, encoding="utf-8"))["publicaciones"]
    publicadas = json.load(open(PUBLICADAS, encoding="utf-8")) if os.path.exists(PUBLICADAS) else {}
    ahora = datetime.now(CDMX)

    if prueba:
        revisar_conexiones(canales)
        sig = [p for p in calendario if hora_de(p) > ahora]
        print("\nPróximas publicaciones:")
        for p in sig[:8]:
            print(f"  {p['fecha']} {p.get('hora')}  {canales[p['canal']]['nombre']:18s} "
                  f"{'aprobada' if p.get('aprobado') else 'SIN APROBAR'}  {p['titulo']}")
        return

    tocan = [p for p in calendario
             if p.get("aprobado") and hora_de(p) <= ahora < hora_de(p) + MAX_RETRASO]
    fallas = []

    def guardar():
        json.dump(publicadas, open(PUBLICADAS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    for p in sorted(tocan, key=hora_de):
        info = canales[p["canal"]]
        ruta = os.path.join(AQUI, p["video"])
        registro = publicadas.setdefault(p["id"], {})
        for red in REDES:
            if red in registro:
                continue
            try:
                registro[red] = PUBLICAR[red](p["canal"], info, p, ruta)
                registro[f"{red}_fecha"] = datetime.now(CDMX).isoformat(timespec="minutes")
                print(f"{p['id']} -> {red}: {registro[red]}")
                guardar()
            except SinPermiso as e:
                print(f"{p['id']} -> {red}: se salta, falta configurar {e}")
            except Exception as e:  # noqa: BLE001
                print(f"{p['id']} -> {red}: ERROR {e}")
                fallas.append(f"{p['id']} {red}")
        if not registro:
            publicadas.pop(p["id"], None)
    guardar()
    if not tocan:
        print(f"Nada que publicar a las {ahora:%H:%M} del {ahora:%d/%m}.")
    if fallas:
        sys.exit("Fallaron: " + ", ".join(fallas) + ". Se reintentan en la siguiente corrida.")


if __name__ == "__main__":
    main()
