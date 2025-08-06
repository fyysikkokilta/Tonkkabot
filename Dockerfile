ARG PYTHON_VERSION=3.13-slim
FROM python:${PYTHON_VERSION}

WORKDIR /bot
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY *.py ./

CMD ["python3", "tonkkabot.py"]