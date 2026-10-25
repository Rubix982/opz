FROM python:3.12-slim

# Where pip gets packages. In real life this is PyPI; here it's the lab's own
# index, as it looked on a given date. check.sh builds with other dates.
ARG INDEX=index/2026-10-25
COPY ${INDEX}/ /wheels/

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt

COPY app/train.py .
COPY app/data/ data/
CMD ["python", "train.py"]
