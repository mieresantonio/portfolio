# Portafolio — Antonio Mieres

Portafolio personal de Antonio Mieres, Desarrollador Full Stack con IA.

**En vivo:** https://mieresantonio.github.io/portfolio/

Un solo archivo HTML+CSS (`index.html`), sin dependencias externas, con modo oscuro automático según la preferencia del sistema (`prefers-color-scheme`). Proyecto destacado: Block Ethos (Web3 Space), plataforma de aprendizaje de blockchain en producción. Incluye una sección de código real con fragmentos de Block Ethos y del asistente RAG, copiados de los repositorios y verificados contra GitHub.

Tarjeta de enlace: `og-image.png` (1200×630, generada localmente con PIL, sin recursos externos).

## Antes de publicar: actualizar las cifras

Las cifras del portafolio (commits de Block Ethos, tamaño del índice RAG) se leen de la fuente en cada publicación, para que nunca queden viejas:

```bash
python3 tools/actualizar-datos.py
```

El script consulta la API pública de GitHub (commits del repo original de Block Ethos) y `data/meta.json` del repo rag-demo, y reescribe solo los números en `index.html`. Si alguna fuente falla, no escribe nada. Con `--check` solo informa de los cambios pendientes, sin tocar el archivo. El script corre en build-time: la página publicada sigue siendo un único `index.html` sin dependencias externas.
