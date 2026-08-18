FROM python:3.8-slim
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
USER root
EXPOSE 8000
CMD ["python", "app.py"]
