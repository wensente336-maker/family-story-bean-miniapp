import { getAccessToken } from "./authStore";

export type ApiMeta = {
  request_id: string;
  timestamp: string;
};

type ApiSuccess<T> = {
  ok: true;
  data: T;
  meta: ApiMeta;
};

type ApiFailure = {
  ok: false;
  error: {
    code: string;
    message: string;
    retryable: boolean;
    details: Record<string, unknown>;
  };
  meta?: ApiMeta;
};

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly retryable: boolean,
    public readonly details: Record<string, unknown>,
    public readonly requestId?: string
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

function createRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function apiRequest<T>(
  baseUrl: string,
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const requestId = createRequestId();
  const accessToken = getAccessToken();
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Request-Id": requestId,
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers
    }
  });

  let body: ApiSuccess<T> | ApiFailure | undefined;
  try {
    body = await response.json() as ApiSuccess<T> | ApiFailure;
  } catch {
    throw new ApiClientError(
      "服务返回了无法识别的内容",
      "INVALID_RESPONSE",
      response.status,
      response.status >= 500,
      {},
      response.headers.get("X-Request-Id") ?? requestId
    );
  }

  if (!response.ok || !body.ok) {
    const failure = body as ApiFailure;
    throw new ApiClientError(
      failure.error?.message ?? "请求失败，请稍后重试",
      failure.error?.code ?? "REQUEST_FAILED",
      response.status,
      failure.error?.retryable ?? response.status >= 500,
      failure.error?.details ?? {},
      failure.meta?.request_id ?? response.headers.get("X-Request-Id") ?? requestId
    );
  }

  return body.data;
}
