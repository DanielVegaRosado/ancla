# CV Adaptativo

**No genera tu CV. Selecciona de hechos que tú has verificado.**

Mantienes una base de datos con tu experiencia y tus skills. Para cada vacante,
la app elige qué mostrar y te dice por qué. Nunca escribe nada que tú no hayas
escrito: si la oferta pide algo que no tienes, te lo señala como hueco en vez de
inventarlo.

Cada adaptación queda guardada. Tu base de hechos crece y tu archivo de
candidaturas crece con ella.

- Corre **en tu ordenador**. Tus datos no salen de ahí: sin cuentas, sin nube.
- Usa **tu propia clave** de IA (Groq tiene nivel gratuito).
- Te da el texto; el diseño sigue siendo tuyo (Canva u otra herramienta). Si no tienes CV
  todavía, hay [dos plantillas de partida](plantillas/README.md).

> 🚧 **En construcción.** Todavía no es usable del todo. Ver el estado abajo.

## Estado

| Pieza | Estado |
|---|---|
| Modelo de datos e interfaces | ✅ |
| Almacén del perfil (YAML) | ✅ |
| Motor de selección | ✅ |
| Interfaz web | ✅ |
| Archivo de CVs | ✅ |
| Importar desde un CV existente (PDF/Word) | ✅ |
| Soporte y plantillas | ✅ |
| Perfil de ejemplo para probar la app | ⬜ |

Probado en local de punta a punta: crear experiencia y skills, definir la plantilla
de «Sobre mí», pegar una vacante y generar la propuesta con una clave de Groq real.
Solo falta rellenar `perfil-ejemplo/` para que alguien que clone el repo pueda
probarlo sin escribir su perfil entero primero.

## Qué criterio usa la IA

Hay dos momentos en los que un modelo de IA toma decisiones, y en los dos aplica el
mismo principio: **la garantía la da el código, no una instrucción que el modelo
podría ignorar.**

### Al adaptar tu perfil a una vacante (`seleccion/`)

El modelo solo devuelve *identificadores* de tu catálogo, nunca texto nuevo — así que
lo que aparece en tu CV siempre es, literalmente, algo que tú escribiste. Reglas:

1. **Nunca propone algo que no esté en tu perfil.** Si un id no existe en tu catálogo,
   el código lo descarta antes de que llegue a la pantalla — no es una petición al
   modelo, es una comprobación después de su respuesta.
2. **Nunca reescribe tus bullets.** Se muestran tal cual los escribiste.
3. **Toda elección lleva un motivo**, para que puedas juzgar la propuesta en vez de
   firmarla a ciegas.
4. **Lo que la vacante pide y no tienes va a «huecos»**, nunca al CV. Inventar es
   exactamente lo que esta herramienta no hace.
5. Ante varias experiencias candidatas, prioriza las que cubran requisitos
   **distintos** entre sí antes que repetir el mismo stack.

### Al importar un CV existente (`perfil/importador.py`)

Aquí el riesgo no es que el modelo invente un hueco: es que, al leer tu CV,
**parafrasee de más** (que tu «colaboré con el equipo» se convierta en «lideré un
equipo de 5»). La garantía aquí es de proceso: nada se guarda en tu perfil sin que
tú lo confirmes, campo a campo.

1. **La extracción del texto es 100% determinista** (una librería, sin IA): el modelo
   nunca "lee" el PDF o el Word directamente, analiza el texto exacto que ya se sacó
   del fichero. Así no puede transcribir mal una palabra sin que se note.
2. **Solo extrae lo que está literalmente en el texto.** No añade responsabilidades,
   logros ni fechas que no aparezcan.
3. **Si un dato falta, el campo se queda vacío** — nunca se completa con un supuesto
   razonable.
4. **Traduce el idioma que falte**, de forma literal, para que no tengas que escribir
   los dos idiomas a mano. *(Mejora prevista para v1.1: apoyar la traducción en
   diccionarios como Oxford o Cambridge, en vez de dejarla enteramente al criterio
   del modelo.)*
5. **Ante la duda entre experiencia o skill suelta, propone skill** — inventar una
   experiencia alrededor de una mención suelta es peor error que perder una real.
6. Nada se guarda hasta que tú revisas, editas y confirmas cada candidata en la
   pantalla de revisión.

## Roadmap

- **v1** — lo de la tabla de arriba, en español.
- **v1.1** — interfaz en inglés, más proveedores de IA.
- **v2** — *Mejoras a realizar*: registras el feedback real de cada empresa
  (en qué fase te descartaron, qué te dijeron) y el sistema te propone mejoras
  concretas sobre tu perfil. Y editar el CV dentro de la app.

## Desarrollo

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python run.py  # sirve la web en http://127.0.0.1:5000
```

## Licencia

MIT
