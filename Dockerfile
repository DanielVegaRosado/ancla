# Imagen para la demo pública desplegada en Render (ver README.md, "Try it
# online"). Construye directamente sobre el propio repositorio: cada push a
# `master` redespliega la demo con Render conectado en modo auto-deploy.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# La demo arranca siempre con el perfil de ejemplo. perfil/ no sobrevive a
# un redespliegue (ver el aviso "Demo pública" en la propia interfaz,
# activado por ANCLA_DEMO) — es un dato conocido y comunicado, no un
# descuido.
RUN rm -rf perfil && cp -r perfil-ejemplo perfil

ENV ANCLA_DEMO=1

EXPOSE 7860

# Un único worker: `crear_app()` genera su SECRET_KEY al arrancar (no es fija
# en ningún fichero), y con más de un worker de gunicorn cada proceso tendría
# una clave distinta — la cookie de sesión de un visitante (donde vive su
# clave de API en modo demo) dejaría de descifrarse en cuanto una petición
# cayera en otro worker.
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "ancla.web:crear_app()"]
