const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const baseUrl = configuredBaseUrl.replace(/\/+$/, "");

type RequestOptions = Omit<RequestInit, "body"> & {
  token?: string | null;
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { token, body, headers, ...init } = options;
  const url = `${baseUrl}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`Could not reach the API at ${baseUrl}. Check that the backend is running and CORS allows this frontend.`);
    }
    throw error;
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(formatErrorMessage(errorBody));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  baseUrl,
  request,
};

function formatErrorMessage(errorBody: unknown) {
  if (!errorBody || typeof errorBody !== "object") {
    return "Request failed";
  }

  const detail = "detail" in errorBody ? errorBody.detail : undefined;
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const location = "loc" in item && Array.isArray(item.loc) ? item.loc.join(".") : null;
        const message = "msg" in item && typeof item.msg === "string" ? item.msg : null;
        if (location && message) return `${location}: ${message}`;
        return message;
      })
      .filter(Boolean);
    return messages.length > 0 ? messages.join("; ") : "Request validation failed";
  }

  return "Request failed";
}
