# zettaranc-skill 前端看板

React 19 + TypeScript + Vite + Tailwind 4 + ECharts 6 的可选 Web 看板。数据来自本仓库的 FastAPI 后端（`zt-web`）。

## 前置条件

先启动后端（默认 8000 端口）：

```bash
pip install fastapi uvicorn pydantic-settings
zt-web
```

## 启动

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173。`/api` 请求由 Vite 代理到 `http://localhost:8000`（见 `vite.config.ts`），无需额外配置跨域。

## 命令

| 命令 | 说明 |
|---|---|
| `npm run dev` | 启动开发服务器（端口 5173） |
| `npm run build` | 生产构建（`tsc -b && vite build`） |
| `npm run lint` | ESLint 检查 |
| `npm run preview` | 预览构建产物 |

前端无单元测试，质量依靠 `npm run lint` + `npm run build`（含 TypeScript 类型检查）。

## 技术栈

- React 19 + TypeScript
- Vite（开发服务器 / 打包）
- Tailwind CSS 4
- ECharts 6（K 线、资金曲线等图表）
- zustand（状态管理）、@tanstack/react-query（数据请求）、react-router 7（路由）

依赖独立于 Python，`frontend/package.json` 自成一套，不与根 `requirements.txt` 耦合。
