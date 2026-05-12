FROM python:3.13.9-slim-trixie
LABEL authors="RadLab"

COPY . /srv/llm-router-web

WORKDIR /srv/llm-router-web

RUN cp docker/entrypoint.sh entrypoint.sh && chmod +x entrypoint.sh
RUN pip3 install -r requirements.txt

ARG USER_ID=5000
ARG GROUP_ID=5000
RUN groupadd -g ${GROUP_ID} llm-router && \
    useradd -m -u ${USER_ID} -g llm-router -d /home/llm-router llm-router && \
    chown -R llm-router:llm-router /srv

USER llm-router



ENTRYPOINT ["/srv/llm-router-web/entrypoint.sh"]