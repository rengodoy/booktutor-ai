FROM ubuntu:noble

# Tesseract
RUN apt-get update && apt-get install -y wget gnupg2 lsb-release wget apt-transport-https curl sudo
RUN echo "deb https://notesalexp.org/tesseract-ocr5/noble/ noble main" \
    | tee /etc/apt/sources.list.d/notesalexp.list
RUN wget -O - https://notesalexp.org/debian/alexp_key.asc | apt-key add - 

RUN apt-get update -oAcquire::AllowInsecureRepositories=true
RUN apt-get install notesalexp-keyring -oAcquire::AllowInsecureRepositories=true

RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-por-best tesseract-ocr-eng-best

# Instale sudo e configure sem senha para o usuário sgc
RUN echo "ubuntu ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    gpasswd -a ubuntu sudo

USER ubuntu

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN echo "source $HOME/.local/bin/env" >> /home/ubuntu/.bashrc
WORKDIR /app

# RUN /home/ubuntu/.local/bin/uv sync

# CMD [""]