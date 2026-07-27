FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir .
RUN useradd --create-home lce && mkdir -p /app/data /app/artifacts && chown -R lce:lce /app
USER lce
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/health', timeout=2)" || exit 1
CMD ["lce", "serve", "--host", "0.0.0.0", "--port", "8790"]
