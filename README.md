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
- Te da el texto; el diseño sigue siendo tuyo (Canva u otra herramienta).

> 🚧 **En construcción.** Todavía no es usable. Ver el estado abajo.

## Estado

| Pieza | Estado |
|---|---|
| Modelo de datos e interfaces | ✅ |
| Almacén del perfil (YAML) | ⬜ |
| Motor de selección | ⬜ |
| Interfaz web | ⬜ |
| Archivo de CVs | ⬜ |
| Importar desde un CV existente | ⬜ |
| Soporte y plantillas | ⬜ |

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
```

## Licencia

MIT
