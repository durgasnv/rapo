export const apiUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  csrfToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  let response: Response;
  try {
    response = await fetch(`${apiUrl.replace(/\/$/, "")}${path}`, {
      ...options,
      headers,
      credentials: "include",
      cache: "no-store",
      signal: options.signal ?? AbortSignal.timeout(15_000),
    });
  } catch {
    throw new Error("We couldn’t reach rapo. Please try again.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map(
                (item: { msg: string; loc?: string[] }) =>
                  `${item.loc?.slice(1).join(".") || "Form"}: ${item.msg}`,
              )
              .join("; ")
          : "Something went wrong. Please try again.";
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type AccountSession = {
  user: {
    id: string;
    name: string;
    email: string;
    role: "participant" | "organizer";
  };
  csrf_token: string;
};

export type EventData = {
  id: string;
  organizer_id: string;
  title: string;
  description: string;
  location: string;
  timezone: string;
  start_at: string;
  end_at: string;
  registration_opens_at: string;
  registration_closes_at: string;
  grouping_at: string;
  confirmation_deadline: string;
  capacity: number | null;
  min_team_size: number;
  max_team_size: number;
  status: "DRAFT" | "PUBLISHED" | "CANCELLED";
  version: number;
};

export type EventPage = {
  items: EventData[];
  total: number;
  offset: number;
  limit: number;
};

export function formatDate(value: string, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}
