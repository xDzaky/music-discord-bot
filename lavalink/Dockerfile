FROM eclipse-temurin:24-jre-noble

RUN groupadd -g 322 lavalink && \
    useradd -u 322 -g lavalink -m -d /opt/Lavalink lavalink

WORKDIR /opt/Lavalink

ADD --chown=lavalink:lavalink https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar .

# Copy application.yml config
COPY --chown=lavalink:lavalink application.yml .

# Copy plugins if any
COPY --chown=lavalink:lavalink plugins/ ./plugins/

RUN apt-get update && \
    apt-get install -y --no-install-recommends netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

USER lavalink

EXPOSE 2333

ENTRYPOINT ["java", "-Djdk.tls.client.protocols=TLSv1.1,TLSv1.2", "-jar", "Lavalink.jar"]
