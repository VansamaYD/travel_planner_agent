# Travel Planner Agent

面向个人和家庭的自托管智能旅游规划系统。项目当前进入实现阶段，采用 React PWA、FastAPI 模块化单体、SQLite WAL 和可替换 Provider。

## 当前实现

Slice 0 已提供：

- FastAPI 应用工厂、显式组合根和健康检查；
- SQLite 异步连接、WAL 参数和 Unit of Work；
- Alembic 迁移基线；
- React 19 + Vite 8 PWA 移动端骨架；
- Python/TypeScript 架构边界检查；
- Docker Compose 的 Web + 单 Worker API 拓扑；
- GitHub Actions 的后端、前端和文档验证。

完整需求和设计见 [docs/design/README.md](./docs/design/README.md)。

## 本地开发

要求：Python 3.12/3.13、uv、Node.js 22.12+、npm。

```bash
make install
make migrate
make dev-api
```

另一个终端：

```bash
make dev-web
```

打开 `http://localhost:5173`，API 文档在开发环境的 `http://localhost:8000/api/docs`。

## 验证

```bash
make check
```

## Docker

生产模式必须提供 `APP_MASTER_KEY`。建议使用至少 32 字节随机值并通过 Docker Secret 或受保护的 `.env` 提供。

```bash
docker compose -f deploy/compose.yaml up --build
```

默认只暴露 Web 端口 `8080`；API 和 SQLite 不直接暴露。

仅用于本机临时预览、尚未配置主密钥时，可运行：

```bash
TRAVEL_RUNTIME_ENV=development docker compose -f deploy/compose.yaml up --build -d
```

## 安全

- `.env`、运行数据、附件、导出和备份均被 Git 忽略；
- 服务端 Key 不得使用 `VITE_` 前缀；
- 不要提交真实 API Key、Cookie、票据或用户数据；
- 当前仓库不包含自动下单、支付或非公开平台写操作。

## 许可证

项目当前按照 [Apache License 2.0](./LICENSE) 开放源代码；引入第三方抓取工具或内容数据前，仍需分别复核其许可证、平台条款与内容版权。
