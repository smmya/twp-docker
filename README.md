# TWP Docker（linux/amd64）

## 1. 导入镜像

下载 Release 附件 `twp-amd64.tar.gz` 后运行：

```bash
docker load -i twp-amd64.tar.gz
```

镜像标签为 `twp:latest` 和 `twp:<tproxy短提交ID>-<MTProxy短提交ID>`。

## 2. Docker Compose

创建 `compose.yaml`，将 `proxy.example.com` 改为实际 HTTPS 域名：

```yaml
services:
  twp:
    image: twp:latest
    pull_policy: never
    container_name: twp
    restart: unless-stopped
    ports:
      - "127.0.0.1:18080:8080"
    environment:
      PUBLIC_HOSTNAME: proxy.example.com
    volumes:
      - twp-data:/data
    read_only: true
    tmpfs:
      - /tmp:size=16m,mode=1777
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    logging:
      driver: local
      options:
        max-size: "5m"
        max-file: "2"

volumes:
  twp-data:
```

启动并查看代理路径、客户端密钥及 Nginx 配置：

```bash
docker compose up -d
docker logs twp
```

在现有 Nginx/NPM 的 HTTPS 443 站点中，按日志输出添加随机路径的反代配置；`127.0.0.1:18080` 是本机 HTTP 入口，不需要公开。重启或升级时保留 `twp-data` 卷，凭据不会变化。
