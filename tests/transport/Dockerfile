FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        apache2 \
        apache2-utils \
        ca-certificates \
        git \
        openssh-server \
        openssl \
    && rm -rf /var/lib/apt/lists/*

RUN a2enmod alias auth_basic cgi env ssl \
    && a2dissite 000-default default-ssl

COPY apache-git.conf /etc/apache2/sites-available/git-ssl.conf
COPY entrypoint.sh /usr/local/bin/redot-git-transport-entrypoint

RUN a2ensite git-ssl \
    && chmod 0755 /usr/local/bin/redot-git-transport-entrypoint

EXPOSE 22 443

ENTRYPOINT ["/usr/local/bin/redot-git-transport-entrypoint"]
