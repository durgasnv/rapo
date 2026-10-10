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
          : typeof detail?.message === "string"
            ? detail.message
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
  status:
    | "DRAFT"
    | "PUBLISHED"
    | "GROUPS_PROPOSED"
    | "GROUPS_FINALIZED"
    | "IN_PROGRESS"
    | "COMPLETED"
    | "CANCELLED";
  version: number;
};

export type EventPage = {
  items: EventData[];
  total: number;
  offset: number;
  limit: number;
};

export type Registration = {
  id: string;
  event_id: string;
  status: "REGISTERED" | "WAITLISTED" | "CANCELLED";
  registered_at: string;
  waitlist_position: number | null;
};

export type RegistrationState = {
  registration: Registration | null;
  registered_count: number;
  waitlisted_count: number;
  capacity: number | null;
  registration_open: boolean;
  withdrawal_open: boolean;
  event_status: EventData["status"];
};

export type RegistrationPage<T> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};

export type MyRegistration = Registration & { event: EventData };
export type RosterRegistration = Registration & {
  user_id: string;
  name: string;
};
export type RosterPage = RegistrationPage<RosterRegistration> & {
  registered_count: number;
  waitlisted_count: number;
};

export function registrationLabel(registration: Registration): string {
  if (registration.status === "WAITLISTED")
    return `Waitlisted · position ${registration.waitlist_position}`;
  return registration.status === "REGISTERED" ? "Registered" : "Withdrawn";
}

export function formatDate(value: string, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}

export type FinalRoster = {
  event_id: string;
  event_status: EventData["status"];
  version: number;
  confirmation_deadline: string;
  confirmation_open: boolean;
  withdrawal_open: boolean;
  own_status: string | null;
  teams: {
    id: string;
    number: number;
    version: number;
    target_size: number;
    status: "READY" | "AWAITING_CONFIRMATIONS" | "NEEDS_ATTENTION";
    reasons: string[];
    members: {
      user_id: string;
      name: string;
      status: string;
      confirmed_at: string | null;
    }[];
  }[];
};
