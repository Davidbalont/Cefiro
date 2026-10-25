"""Publica en Facebook e Instagram la siguiente publicacion pendiente de calendario.json.

Usa la API Graph de Meta con el token de la pagina (secreto META_PAGE_TOKEN).
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
AQUI = os.path.dirname(os.path.abspath(__file__))
CALENDARIO = os.path.join(AQUI, "calendario.json")
PUBLICADAS = os.path.join(AQUI, "publicadas.json")
SONORA = timezone(timedelta(hours=-7))


class ErrorMeta(SystemExit):
    pass


TOKEN = {"valor": os.environ.get("META_PAGE_TOKEN", "")}


def graph(metodo, ruta, **params):
    params.setdefault("access_token", TOKEN["valor"])
    datos = urllib.parse.urlencode(params).encode()
    url = f"{API}/{ruta}"
    if metodo == "GET":
        req = urllib.request.Request(f"{url}?{datos.decode()}")
    else:
        req = urllib.request.Request(url, data=datos, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="replace")
        raise ErrorMeta(f"Error de Meta en {ruta}: {e.code} {cuerpo}")


def url_imagen(ruta):
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ.get("GITHUB_SHA", "main")
    return f"https://raw.githubusercontent.com/{repo}/{sha}/redes/{ruta}"


def publicar_facebook(pagina_id, imagen, texto):
    r = graph("POST", f"{pagina_id}/photos", url=imagen, message=texto)
    return r.get("post_id") or r.get("id")


def publicar_instagram(ig_id, imagen, texto):
    contenedor = graph("POST", f"{ig_id}/media", image_url=imagen, caption=texto)["id"]
    for _ in range(30):
        estado = graph("GET", contenedor, fields="status_code")["status_code"]
        if estado == "FINISHED":
            break
        if estado == "ERROR":
            raise SystemExit("Instagram no pudo procesar la imagen")
        time.sleep(5)
    return graph("POST", f"{ig_id}/media_publish", creation_id=contenedor)["id"]


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
    imagen = url_imagen(p["imagen"])
    print(f"Siguiente: {p['id']} (fecha {p['fecha']}) imagen {imagen}")
    if prueba:
        print("Modo prueba: no se publico nada.")
        return

    registro = publicadas.setdefault(p["id"], {})

    def guardar():
        registro["fecha_publicacion"] = datetime.now(SONORA).isoformat(timespec="minutes")
        json.dump(publicadas, open(PUBLICADAS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # Se guarda despues de cada red para no repetir Facebook si Instagram falla.
    if "facebook" not in registro:
        registro["facebook"] = publicar_facebook(pagina_id, imagen, p["texto"])
        print("Facebook:", registro["facebook"])
        guardar()
    if ig_id and "instagram" not in registro:
        registro["instagram"] = publicar_instagram(ig_id, imagen, p["texto"])
        print("Instagram:", registro["instagram"])
        guardar()
    if not ig_id:
        registro["instagram"] = "no conectado"
        guardar()
        sys.exit("La pagina no tiene Instagram conectado; solo se publico en Facebook.")


if __name__ == "__main__":
    main()
