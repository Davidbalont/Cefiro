"""Revisión automática de calidad del sitio, las propuestas y las publicaciones de Céfiro.

Revisa que todo lo publicado cumpla las reglas del negocio:
máximo 4 tintas, pago 50% de anticipo y 50% al recibir, bolsa transparente sellada,
sin mencionar IA, llamadas y visitas fuera del horario de David, precios de la lista oficial
y enlaces que sí abren. Los errores detienen la revisión; los avisos solo se reportan.
"""
import glob, html, json, os, re, subprocess, sys, urllib.parse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RAIZ)

# Lista oficial de aromatizantes (más IVA), por 5,000 / 10,000 / 20,000 piezas
LISTA = {1: (10.40, 9.60, 8.90), 2: (10.90, 10.10, 9.40), 3: (11.40, 10.60, 9.90), 4: (11.90, 11.10, 10.40)}
# Lista anterior (14 y 15 de octubre de 2026): las propuestas ya enviadas conservan su precio
LISTA_ANTERIOR = {2: (10.50, 9.90, 9.40), 3: (10.90, 10.40, 9.90)}

errores, avisos, lista_anterior = [], [], []

def error(archivo, texto): errores.append(f"{archivo}: {texto}")
def aviso(archivo, texto): avisos.append(f"{archivo}: {texto}")

def texto_html(ruta):
    t = open(ruta, encoding="utf8").read()
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))

def texto_pdf(ruta):
    r = subprocess.run(["pdftotext", "-layout", ruta, "-"], capture_output=True, text=True)
    return re.sub(r"\s+", " ", r.stdout)

def cerca(t, m, n=80):
    return t[max(0, m.start() - n):m.end() + n].strip()

def reglas(nombre, t):
    """Reglas que aplican a cualquier texto que ve un cliente."""
    for m in re.finditer(r"\b([5-9]|1\d)\s+tintas\b|m[aá]s de 4 tintas|tintas ilimitadas", t, re.I):
        error(nombre, f"ofrece más de 4 tintas: «{cerca(t, m)}»")
    for m in re.finditer(r"a convenir|contra ?entrega|pago a \d+ d[ií]as|cr[eé]dito de \d+", t, re.I):
        error(nombre, f"forma de pago distinta a 50/50: «{cerca(t, m)}»")
    if re.search(r"\d+ ?% de anticipo|anticipo del \d+|(pago|pagas)[^.]{0,60}anticipo", t, re.I) and not re.search(
            r"50 ?% (al recibir|cuando recib|al cierre|con el reporte|al entregarte|al terminar)|otro 50 ?%|50 ?% restante", t, re.I):
        error(nombre, "menciona el anticipo pero no el otro 50% al recibir")
    for m in re.finditer(r"\bfilm\b|celof[aá]n|termoencogible", t, re.I):
        error(nombre, f"empaque distinto a bolsa transparente sellada: «{cerca(t, m)}»")
    for m in re.finditer(r"\bIA\b|inteligencia artificial|ChatGPT|\bClaude\b|\bGPT\b|\bAI\b", t):
        error(nombre, f"menciona IA: «{cerca(t, m)}»")
    for m in re.finditer(r"(llamada|videollamada|visita|cita con nosotros|paso a)[^.]{0,80}?\b([7-9]|1[0-6])(:\d\d)? ?(a\. ?m\.|am\b|hrs|horas)", t, re.I):
        if re.search(r"s[aá]bado", m.group(0), re.I):
            continue
        error(nombre, f"llamada o visita dentro del horario de trabajo de David (7 a. m. a 5 p. m.): «{cerca(t, m)}»")

def precios_pdf(nombre, t):
    tintas = re.search(r"en (\d) tintas? planas?", t)
    if not tintas:
        return
    n = int(tintas.group(1))
    filas = re.findall(r"(5|10|20),000 piezas.*?\$(\d+\.\d\d)", t)
    vistos = {f"{c},000": float(p) for c, p in filas}
    validos = [x for x in (LISTA.get(n), LISTA_ANTERIOR.get(n)) if x]
    for i, c in enumerate(("5,000", "10,000", "20,000")):
        if c in vistos and all(abs(vistos[c] - v[i]) > 0.001 for v in validos):
            error(nombre, f"precio de {c} piezas a {n} tintas (${vistos[c]:.2f}) no está en la lista oficial")
    if LISTA_ANTERIOR.get(n) and any(abs(vistos.get(c, 0) - LISTA_ANTERIOR[n][i]) < 0.001 and abs(LISTA_ANTERIOR[n][i] - LISTA[n][i]) > 0.001
                                     for i, c in enumerate(("5,000", "10,000", "20,000"))):
        lista_anterior.append(os.path.basename(nombre))

def precios_sitio(t):
    m = re.search(r"1 tinta \$(\d+\.\d\d) / \$(\d+\.\d\d) / \$(\d+\.\d\d); 2 tintas \$(\d+\.\d\d) / \$(\d+\.\d\d) / \$(\d+\.\d\d); "
                  r"3 tintas \$(\d+\.\d\d) / \$(\d+\.\d\d) / \$(\d+\.\d\d); 4 tintas \$(\d+\.\d\d) / \$(\d+\.\d\d) / \$(\d+\.\d\d)", t)
    if not m:
        error("index.html", "no se encontró la tabla de precios en las preguntas frecuentes")
        return
    vals = [float(x) for x in m.groups()]
    esperado = [v for n in (1, 2, 3, 4) for v in LISTA[n]]
    if vals != esperado:
        error("index.html", f"los precios de las preguntas frecuentes no coinciden con la lista oficial: {vals}")

def enlaces(ruta):
    t = open(ruta, encoding="utf8").read()
    ids = set(re.findall(r'id="([^"]+)"', t))
    for u in re.findall(r'(?:href|src)="([^"]+)"', t):
        if u.startswith("#"):
            if len(u) > 1 and u[1:] not in ids:
                error(ruta, f"enlace a una sección que no existe: {u}")
            continue
        if u.startswith("https://davidbalont.github.io/Cefiro/"):
            p = u[len("https://davidbalont.github.io/Cefiro/"):]
        elif re.match(r"[a-z]+:", u) or "${" in u:
            continue
        else:
            p = os.path.normpath(os.path.join(os.path.dirname(ruta), u))
        p = urllib.parse.unquote(p.split("#")[0].split("?")[0])
        if p in ("", "."):
            p = "index.html"
        if os.path.isdir(p):
            p = os.path.join(p, "index.html")
        if not os.path.exists(p):
            error(ruta, f"enlace o imagen que no abre: {u}")

def main():
    paginas = sorted(set(glob.glob("*.html") + glob.glob("**/*.html", recursive=True)))
    for ruta in paginas:
        t = texto_html(ruta)
        reglas(ruta, t)
        enlaces(ruta)
    precios_sitio(texto_html("index.html"))

    for ruta in sorted(glob.glob("propuestas/*.pdf") + glob.glob("aquatunel/*.pdf") + glob.glob("correos/*.pdf")):
        t = texto_pdf(ruta)
        if not t.strip():
            aviso(ruta, "no se pudo leer el texto del PDF")
            continue
        reglas(ruta, t)
        precios_pdf(ruta, t)

    if lista_anterior:
        aviso("propuestas", f"{len(lista_anterior)} propuestas ya enviadas conservan la lista de precios anterior ({', '.join(lista_anterior)}). "
              "Si uno de esos clientes pide precios, se respeta el de su propuesta.")

    try:
        cal = json.load(open("redes/calendario.json", encoding="utf8"))["publicaciones"]
    except Exception as e:
        error("redes/calendario.json", f"el archivo no se puede leer: {e}")
        cal = []
    pagos_digitales = re.search(r"var PAGO = \{(.*?)\};", open("digital.html", encoding="utf8").read(), re.S)
    sin_enlaces = pagos_digitales and not re.search(r'"https?://', pagos_digitales.group(1))
    for p in cal:
        nombre = f"redes/calendario.json ({p.get('fecha')} {p.get('id')})"
        reglas(nombre, p.get("texto", ""))
        if p.get("imagen") and not os.path.exists(os.path.join("redes", p["imagen"])):
            error(nombre, f"falta la imagen {p['imagen']}")
        if sin_enlaces and "enlace de nuestra bio" in p.get("texto", ""):
            aviso(nombre, "manda al enlace de la bio, pero los productos digitales todavía no tienen enlace de pago")

    resumen = ["# Revisión de calidad de Céfiro", ""]
    resumen.append(f"**{len(errores)} errores y {len(avisos)} avisos** en {len(paginas)} páginas, las propuestas en PDF y {len(cal)} publicaciones.")
    if errores:
        resumen += ["", "## Errores (corregir antes de enviar a clientes)"] + [f"- {e}" for e in errores]
    if avisos:
        resumen += ["", "## Avisos"] + [f"- {a}" for a in avisos]
    salida = "\n".join(resumen)
    print(salida)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf8").write(salida + "\n")
    sys.exit(1 if errores else 0)

if __name__ == "__main__":
    main()
