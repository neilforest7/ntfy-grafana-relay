FROM python:3.12-alpine
COPY app.py /app/relay.py
WORKDIR /app
ENV PORT=8080
CMD ["python", "/app/relay.py"]
