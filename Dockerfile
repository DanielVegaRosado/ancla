# Image for the public demo deployed on Render (see README.md, "Try it
# online"). Builds directly on top of the repository itself: every push to
# `master` redeploys the demo, with Render connected in auto-deploy mode.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# The demo always starts with the example profile. perfil/ does not survive
# a redeploy (see the "Public demo" notice in the interface itself,
# triggered by ANCLA_DEMO) — that's a known, communicated fact, not an
# oversight.
RUN rm -rf perfil && cp -r perfil-ejemplo perfil

ENV ANCLA_DEMO=1

EXPOSE 7860

# A single worker: `create_app()` generates its SECRET_KEY on startup (it is
# not fixed in any file), and with more than one gunicorn worker each
# process would have a different key — a visitor's session cookie (where
# their API key lives in demo mode) would stop decrypting the moment a
# request landed on a different worker.
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "ancla.web:create_app()"]
