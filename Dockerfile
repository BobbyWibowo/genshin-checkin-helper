FROM python:3-alpine

WORKDIR /app
COPY requirements.txt ./
COPY genshincheckinhelper ./genshincheckinhelper

RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python3", "./genshincheckinhelper/main.py" ]
