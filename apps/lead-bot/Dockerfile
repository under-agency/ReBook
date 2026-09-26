FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir "pyTelegramBotAPI>=4.25"
COPY leads.py bot.py ./
USER nobody
CMD ["python", "bot.py"]
