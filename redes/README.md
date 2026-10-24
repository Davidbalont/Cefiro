# Publicaciones automáticas en Facebook e Instagram

Todos los días a las 7:00 pm (hora de Sonora) GitHub revisa `calendario.json` y publica
en Facebook e Instagram la siguiente publicación cuya fecha ya llegó. Publica una por día
como máximo y anota lo publicado en `publicadas.json`, así nunca repite.

- `calendario.json`: fecha, imagen y texto de cada publicación.
- `imagenes/`: las imágenes en JPG cuadrado (Instagram solo acepta JPG).
- `publicar.py`: el programa que publica con la API de Meta.

Para agregar publicaciones, suma entradas a `calendario.json` con un `id` nuevo.

## Paso único: el permiso de Meta

1. En developers.facebook.com → Mis apps → Crear app. Elige "Otro" y luego "Empresa".
   Nómbrala "Publicador Céfiro".
2. Abre el Explorador de la API Graph (developers.facebook.com/tools/explorer), elige
   esa app y pulsa "Generate Access Token" con estos permisos:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`, `business_management`. Acepta la página Céfiro y @cefiromx.
3. Pulsa el ícono (i) junto al token → "Abrir en la herramienta de token de acceso" →
   "Ampliar token de acceso" y copia el token largo.
4. En el Explorador pega ese token largo, escribe `me/accounts` y pulsa Enviar. Copia el
   `access_token` que aparece junto a la página Céfiro (ese no caduca).
5. En GitHub → Cefiro → Settings → Secrets and variables → Actions → New repository
   secret, nombre `META_PAGE_TOKEN`, y pega el token.

Para probar sin publicar: Actions → "Publicar en redes" → Run workflow con "prueba" marcada.
