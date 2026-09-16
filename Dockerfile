# Image deployed on Render (see README.md, "Try it online"). Builds directly
# on top of the repository itself: every push to `master` redeploys it, with
# Render connected in auto-deploy mode.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 7860

# ANCLA_SECRET_KEY must be set in Render's own environment variables (not
# here — it is a secret, never baked into the image or the repo). Without it
# every gunicorn worker signs session cookies with its own random key, and a
# logged-in visitor bounces between "logged in" and "logged out" depending on
# which worker answers each request; a fixed key is what makes running more
# than one worker safe at all.
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "ancla.web:create_app()"]
