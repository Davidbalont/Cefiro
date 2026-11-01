# Publicador de los canales de nicho

Publica solos los videos de ¿Y Eso Por Qué?, But Why?, Cofre Abierto, La Lana Detrás y
Mapeando México en YouTube, TikTok, Facebook e Instagram.

## Cómo funciona

- Cada 15 minutos GitHub corre `publicar.py` (Actions → "Publicar canales de nicho").
- Revisa `calendario.json` y publica cada entrada con `"aprobado": true` cuya fecha y hora
  (centro de México) ya llegó. Nada sin aprobar se publica.
- Anota en `publicadas.json` lo que ya salió en cada red, así nunca repite. Si una red falla,
  en la siguiente corrida solo se reintenta esa red. Si una publicación aprobada se quedó
  atrás más de 2 días, ya no sale sola.
- Si una red todavía no tiene sus permisos, se salta sin error: se puede empezar con
  Facebook e Instagram y sumar YouTube y TikTok después.

Archivos:

- `calendario.json`: una entrada por video y canal (`fecha`, `hora`, `canal`, `video`,
  `titulo` para YouTube, `texto` para la descripción, `aprobado`).
- `canales.json`: nombre exacto, idioma y usuario de cada canal. El nombre debe ser igual al
  de la página de Facebook.
- `videos/`: los MP4 verticales.
- `tiktok.html`: página para autorizar cada cuenta de TikTok; `privacidad.html` y
  `terminos.html` son las páginas que piden las apps de Google y TikTok.

## Secretos de GitHub

Settings → Secrets and variables → Actions → New repository secret.

| Secreto | Para qué |
|-|-|
| `META_CANALES_TOKEN` | Token del usuario del sistema de Meta con las 5 páginas y los 5 Instagram asignados |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET` | App de Google (YouTube Data API v3) |
| `YT_REFRESH_YESOPORQUE`, `YT_REFRESH_BUTWHY`, `YT_REFRESH_COFRE`, `YT_REFRESH_LANA`, `YT_REFRESH_MAPEANDO` | Permiso de cada canal de YouTube |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | App de TikTok (Content Posting API) |
| `GH_ADMIN_TOKEN` | Token de GitHub que deja al flujo "Conectar TikTok" guardar los permisos de TikTok |
| `TIKTOK_REFRESH_<CANAL>` | Los crea solo el flujo "Conectar TikTok" |

Los pasos con clics exactos para sacar cada permiso están en la guía de configuración que
se entregó en el hilo del proyecto.

## Límites de cada red

- **YouTube:** mientras Google no audite la app, los videos subidos por la API quedan
  privados. Se pide la auditoría con el formulario "YouTube API Services - Audit and Quota
  Extension Form". La cuota normal alcanza para 6 videos al día.
- **TikTok:** mientras TikTok no apruebe la app, solo deja publicar en privado
  ("solo yo"). El programa lo detecta solo y avisa en el registro.
- **Facebook e Instagram:** funcionan desde el primer día con el usuario del sistema.

## Probar sin publicar

Actions → "Publicar canales de nicho" → Run workflow con "prueba" marcada. Muestra, por
canal y por red, si el permiso funciona y a qué cuenta apunta, y las próximas publicaciones.
