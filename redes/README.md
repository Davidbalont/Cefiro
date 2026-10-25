# Publicaciones automáticas en Facebook e Instagram

Todos los días cerca de las 11:00 am (hora de Sonora) GitHub revisa `calendario.json` y publica
en Facebook e Instagram la siguiente publicación cuya fecha ya llegó. Publica una por día
como máximo y anota lo publicado en `publicadas.json`, así nunca repite.

- `calendario.json`: fecha, imagen y texto de cada publicación.
- `imagenes/`: las imágenes en JPG cuadrado (Instagram solo acepta JPG).
- `publicar.py`: el programa que publica con la API de Meta.

Para agregar publicaciones, suma entradas a `calendario.json` con un `id` nuevo.

## Paso único: el permiso de Meta (token que no caduca)

1. En developers.facebook.com → Mis apps → Crear app. Elige "Otro", luego "Empresa",
   nómbrala "Publicador Céfiro" y elige el portafolio Cefiromx.
2. En business.facebook.com → Ajustes → Cuentas → Cuentas de Instagram → Agregar, y
   conecta @cefiromx si no aparece.
3. Ajustes → Usuarios → Usuarios del sistema → Agregar. Nombre "publicador", rol
   Administrador.
4. Con "publicador" seleccionado → Asignar activos: la página Céfiro, la cuenta @cefiromx
   y la app Publicador Céfiro, todas con control total.
5. Generar token → app Publicador Céfiro → caducidad "Nunca" → permisos
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`, `business_management` → Generar. Cópialo.
6. En GitHub → Cefiro → Settings → Secrets and variables → Actions → New repository
   secret, nombre `META_PAGE_TOKEN`, y pega el token.

También sirve un token de la página sacado del Explorador de la API Graph.

Para probar sin publicar: Actions → "Publicar en redes" → Run workflow con "prueba" marcada.
