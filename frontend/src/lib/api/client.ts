import axios, {
  type AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

/** 后端统一错误响应体：{ detail, errorCode } —— RESTful 原生状态码，无 code 包裹 */
export interface ApiErrorBody {
  detail: string
  errorCode: string
  [key: string]: unknown
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public errorCode: string,
    message: string,
    public body?: ApiErrorBody,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 后端分页出参统一结构 */
export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

const BASE_URL = '/api/v1'
const REFRESH_TOKEN_KEY = 'trendradar.refreshToken'

export const http = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

/** 不带拦截器的裸实例，专用于 refresh，避免递归 */
const bare = axios.create({ baseURL: BASE_URL, timeout: 15_000 })

// ---------------------------------------------------------------- token 状态

let accessToken: string | null = null

export const setAccessToken = (t: string | null) => {
  accessToken = t
}
export const getAccessToken = () => accessToken

export const getRefreshToken = () => localStorage.getItem(REFRESH_TOKEN_KEY)
export const setRefreshToken = (t: string) => localStorage.setItem(REFRESH_TOKEN_KEY, t)
export const clearRefreshToken = () => localStorage.removeItem(REFRESH_TOKEN_KEY)

// ---------------------------------------------------------------- 会话失效广播
//
// client 不 import authStore（避免循环依赖），改为发布订阅。

type Listener = () => void
const sessionExpiredListeners = new Set<Listener>()

export function onSessionExpired(listener: Listener): () => void {
  sessionExpiredListeners.add(listener)
  return () => sessionExpiredListeners.delete(listener)
}

function notifySessionExpired() {
  accessToken = null
  clearRefreshToken()
  sessionExpiredListeners.forEach((fn) => fn())
}

// ---------------------------------------------------------------- refresh（并发去重）

interface RefreshResult {
  accessToken: string
  refreshToken: string
}

/** 同一时刻只允许一个 refresh 在飞；其余请求复用这个 Promise */
let refreshPromise: Promise<RefreshResult> | null = null

export async function refreshSession(): Promise<RefreshResult> {
  if (refreshPromise) return refreshPromise

  const token = getRefreshToken()
  if (!token) {
    notifySessionExpired()
    throw new ApiError(401, 'NO_REFRESH_TOKEN', '登录已失效，请重新登录')
  }

  refreshPromise = bare
    .post<RefreshResult>('/auth/refresh', { refreshToken: token })
    .then((res) => {
      setAccessToken(res.data.accessToken)
      setRefreshToken(res.data.refreshToken)
      return res.data
    })
    .catch((err: AxiosError<ApiErrorBody>) => {
      notifySessionExpired()
      throw new ApiError(
        err.response?.status ?? 401,
        err.response?.data?.errorCode ?? 'INVALID_REFRESH_TOKEN',
        err.response?.data?.detail ?? '登录已失效，请重新登录',
      )
    })
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}

// ---------------------------------------------------------------- 拦截器

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

interface RetriableConfig extends AxiosRequestConfig {
  _retried?: boolean
}

http.interceptors.response.use(
  (res) => res,
  async (error: AxiosError<ApiErrorBody>) => {
    const status = error.response?.status ?? 0
    const body = error.response?.data
    const config = error.config as RetriableConfig | undefined
    const url = config?.url ?? ''

    // 401 且不是 auth 自身接口 → 尝试刷新一次后重试
    const isAuthEndpoint = url.includes('/auth/refresh') || url.includes('/auth/login')
    if (status === 401 && config && !config._retried && !isAuthEndpoint && getRefreshToken()) {
      config._retried = true
      try {
        await refreshSession()
        return http.request(config)
      } catch {
        // refreshSession 内部已广播会话失效
      }
    }

    throw new ApiError(
      status,
      body?.errorCode ?? (status === 0 ? 'NETWORK_ERROR' : 'UNKNOWN_ERROR'),
      body?.detail ?? error.message,
      body,
    )
  },
)
