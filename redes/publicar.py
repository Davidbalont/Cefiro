"""Publica en Facebook e Instagram la siguiente publicacion pendiente de calendario.json.

Usa la API Graph de Meta con el token de la pagina (secreto META_PAGE_TOKEN).
Cada publicacion lleva "imagen" (una foto), "imagenes" (carrusel) o "video" (reel).
Publica como maximo una publicacion por corrida: la mas antigua cuya fecha ya llego
y que todavia no aparece en publicadas.json. La hora local es la de Sonora (UTC-7).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://graph.facebook.com/v21.0"
API_VIDEO = "https://graph-video.facebook.com/v21.0"
AQUI = os.path.dirname(os.path.abspath(__file__))
CALENDARIO = os.path.join(AQUI, "calendario.json")
PUBLICADAS = os.path.join(AQUI, "publicadas.json")
SONORA = timezone(timedelta(hours=-7))


class ErrorMeta(SystemExit):
    pass


TOKEN = {"valor": os.environ.get("META_PAGE_TOKEN", "")}


def graph(metodo, ruta, base=API, **params):
    params.setdefault("access_token", TOKEN["valor"])
    datos = urllib.parse.urlencode(params).encode()
    url = f"{base}/{ruta}"
    if metodo == "GET":
        req = urllib.request.Request(f"{url}?{datos.decode()}")
    else:
        req = urllib.request.Request(url, data=datos, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="replace")
        raise ErrorMeta(f"Error de Meta en {ruta}: {e.code} {cuerpo}")


def url_imagen(ruta):
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ.get("GITHUB_SHA", "main")
    return f"https://raw.githubusercontent.com/{repo}/{sha}/redes/{ruta}"


def url_video(ruta):
    # GitHub Pages sirve los mp4 como video/mp4; raw.githubusercontent no.
    dueno, repo = os.environ["GITHUB_REPOSITORY"].split("/")
    return f"https://{dueno.lower()}.github.io/{repo}/redes/{ruta}"


def publicar_facebook(pagina_id, p, texto):
    if "video" in p:
        r = graph("POST", f"{pagina_id}/videos", base=API_VIDEO, file_url=url_video(p["video"]), description=texto)
        return r.get("id")
    if "imagenes" in p:
        fotos = [graph("POST", f"{pagina_id}/photos", url=url_imagen(i), published="false")["id"] for i in p["imagenes"]]
        adjuntos = {f"attached_media[{n}]": json.dumps({"media_fbid": f}) for n, f in enumerate(fotos)}
        return graph("POST", f"{pagina_id}/feed", message=texto, **adjuntos)["id"]
    r = graph("POST", f"{pagina_id}/photos", url=url_imagen(p["imagen"]), message=texto)
    return r.get("post_id") or r.get("id")


def esperar(contenedor, intentos=30):
    for _ in range(intentos):
        estado = graph("GET", contenedor, fields="status_code")["status_code"]
        if estado == "FINISHED":
            return
        if estado == "ERROR":
            raise SystemExit("Instagram no pudo procesar el archivo")
        time.sleep(10)
    raise SystemExit("Instagram tardo demasiado en procesar el archivo")


def publicar_instagram(ig_id, p, texto):
    if "video" in p:
        contenedor = graph("POST", f"{ig_id}/media", media_type="REELS", video_url=url_video(p["video"]),
                           cover_url=url_imagen(p["portada"]), caption=texto, share_to_feed="true")["id"]
        esperar(contenedor, intentos=60)
    elif "imagenes" in p:
        hijos = []
        for i in p["imagenes"]:
            hijo = graph("POST", f"{ig_id}/media", image_url=url_imagen(i), is_carousel_item="true")["id"]
            esperar(hijo)
            hijos.append(hijo)
        contenedor = graph("POST", f"{ig_id}/media", media_type="CAROUSEL", children=",".join(hijos), caption=texto)["id"]
        esperar(contenedor)
    else:
        contenedor = graph("POST", f"{ig_id}/media", image_url=url_imagen(p["imagen"]), caption=texto)["id"]
        esperar(contenedor)
    return graph("POST", f"{ig_id}/media_publish", creation_id=contenedor)["id"]


def archivos(p):
    if "video" in p:
        return f"video {url_video(p['video'])}"
    return "imagenes " + " ".join(url_imagen(i) for i in p.get("imagenes") or [p["imagen"]])


def buscar_pagina():
    """Acepta el token de la pagina o el de un usuario del sistema que la administra."""
    campos = "id,name,instagram_business_account"
    try:
        paginas = graph("GET", "me/accounts", fields=campos + ",access_token").get("data") or []
    except ErrorMeta:
        paginas = []  # el token ya es de la pagina
    if not paginas:
        return graph("GET", "me", fields=campos)
    pagina = next((x for x in paginas if "firo" in x.get("name", "").lower()), paginas[0])
    TOKEN["valor"] = pagina.pop("access_token")
    return pagina


def main():
    prueba = os.environ.get("PRUEBA", "").lower() == "true"
    calendario = json.load(open(CALENDARIO, encoding="utf-8"))["publicaciones"]
    publicadas = json.load(open(PUBLICADAS, encoding="utf-8")) if os.path.exists(PUBLICADAS) else {}
    hoy = datetime.now(SONORA).date().isoformat()

    def completa(pid):
        return all(red in publicadas.get(pid, {}) for red in ("facebook", "instagram"))

    pendientes = [p for p in calendario if p["fecha"] <= hoy and not completa(p["id"])]
    if not pendientes and not prueba:
        print(f"Nada que publicar hoy ({hoy}).")
        return
    # En modo prueba se revisa la conexion aunque hoy no toque publicar.
    siguientes = pendientes or [p for p in calendario if not completa(p["id"])]
    if not siguientes:
        print("No quedan publicaciones en el calendario.")
        return
    p = sorted(siguientes, key=lambda x: x["fecha"])[0]

    pagina = buscar_pagina()
    pagina_id = pagina["id"]
    ig_id = (pagina.get("instagram_business_account") or {}).get("id")
    print(f"Pagina: {pagina.get('name')} | Instagram conectado: {'si' if ig_id else 'NO'}")
    print(f"Siguiente: {p['id']} (fecha {p['fecha']}) {archivos(p)}")
    if prueba:
        print("Modo prueba: no se publico nada.")
        return

    registro = publicadas.setdefault(p["id"], {})

    def guardar():
        registro["fecha_publicacion"] = datetime.now(SONORA).isoformat(timespec="minutes")
        json.dump(publicadas, open(PUBLICADAS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # Se guarda despues de cada red para no repetir Facebook si Instagram falla.
    if "facebook" not in registro:
        registro["facebook"] = publicar_facebook(pagina_id, p, p["texto"])
        print("Facebook:", registro["facebook"])
        guardar()
    if ig_id and "instagram" not in registro:
        registro["instagram"] = publicar_instagram(ig_id, p, p["texto"])
        print("Instagram:", registro["instagram"])
        guardar()
    if not ig_id:
        registro["instagram"] = "no conectado"
        guardar()
        sys.exit("La pagina no tiene Instagram conectado; solo se publico en Facebook.")


if __name__ == "__main__":
    main()
