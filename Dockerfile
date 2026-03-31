FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py
COPY static /app/static

ENV HOST=0.0.0.0
ENV PORT=10000

EXPOSE 10000

CMD ["python", "server.py"]
