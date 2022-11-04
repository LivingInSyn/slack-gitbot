FROM python:3.9-bullseye
RUN mkdir /app
# copy required files
COPY main.py /app
COPY conf.py /app
COPY git_manager.py /app
COPY auth_manager.py /app
COPY blocks.json /app
COPY pyproject.toml /app 
# change to workdir and setup python and poetry
WORKDIR /app
ENV PYTHONPATH=${PYTHONPATH}:${PWD} 
RUN pip3 install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev
# start the application
CMD ["python3", "main.py"]