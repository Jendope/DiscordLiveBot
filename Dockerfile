FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir discord.py requests python-dotenv

COPY . .

CMD ["python", "app.py"]