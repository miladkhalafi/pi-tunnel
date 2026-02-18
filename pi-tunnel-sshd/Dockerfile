# pi-tunnel-sshd/Dockerfile
# Accepts reverse SSH tunnels from Raspberry Pis (behind NAT)
# Keys: mount authorized_keys at runtime (no keys in image)
# Ports: SSH 22 for Pi connections; 10022-10031 for up to 10 tunnels

FROM alpine:3.19
RUN apk add --no-cache openssh-server && \
    adduser -D -s /sbin/nologin pitunnel && \
    mkdir -p /home/pitunnel/.ssh && chmod 700 /home/pitunnel/.ssh && \
    chown -R pitunnel:pitunnel /home/pitunnel/.ssh && \
    ssh-keygen -A
COPY sshd_config /etc/ssh/sshd_config
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
# authorized_keys provided at runtime via volume
EXPOSE 22 10022 10023 10024 10025 10026 10027 10028 10029 10030 10031
ENTRYPOINT ["/entrypoint.sh"]
